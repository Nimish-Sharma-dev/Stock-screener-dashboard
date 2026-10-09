"""The recompute loop. Reads state, reruns the maths, detects -2 crosses, publishes rows.
This is the ONLY place that can reach the order placer."""
import threading

from .settings import REFRESH_SECONDS, Z_BUY, Z_HIGH
from .stats import build_series, compute_stats


class Engine:
    def __init__(self, state, risk, placer=None):
        self.state = state
        self.risk = risk
        self.placer = placer
        self.prev_z = {}        # last live z per symbol
        self.crossed = set()    # symbols that crossed down through Z_BUY during this run

    def step(self):
        """One recompute. Returns (rows, title)."""
        snap = self.state.snapshot_live()
        rows = []
        for sym, info in self.state.base.items():
            paise = snap.get(sym)
            live = None if paise is None else paise / 100.0       # paise -> rupees
            series = build_series(info["closes"], info["last_is_today"], live)
            st = compute_stats(series)
            rows.append({"symbol": sym, "src": "live" if paise is not None else "hist", **st})
            if paise is not None:
                self._check_cross(sym, st["z"], paise)
        rows.sort(key=lambda r: (r["z"] is None, r["z"] if r["z"] is not None else 0))
        title = "LIVE" if snap else "WAITING FOR LIVE PRICES (market closed?) - showing daily closes"
        self.state.publish(rows, title, self.risk.order_placed)
        return rows, title

    def _check_cross(self, sym, z, paise):
        before = self.prev_z.get(sym)
        if z is not None:
            self.prev_z[sym] = z
        if z is None or before is None:
            return                      # first live reading only seeds the comparison
        if before >= Z_BUY and z < Z_BUY:
            self.crossed.add(sym)
            self.state.add_event("cross", f"{sym}: z crossed down through {Z_BUY} "
                                          f"({before:.2f} -> {z:.2f})")
            if self.risk.approve(sym, z):
                threading.Thread(target=self._place, args=(sym, paise), daemon=True).start()
        elif z < Z_BUY and sym not in self.crossed:
            self.risk.refuse(sym, f"z={z:.2f} is below {Z_BUY} but did not cross down through it "
                                  f"during this run", key="no-cross")
        elif z > Z_HIGH:
            self.risk.refuse(sym, f"z={z:.2f} is a stretched high (> {Z_HIGH}); never buy highs",
                             key="stretched-high")

    def _place(self, sym, paise):
        try:
            self.placer.place_limit_buy(sym, paise)
        except Exception as exc:
            self.state.add_event("order", f"{sym}: order step failed: {exc!r} (no further orders this run)")

    def run_forever(self, stop, on_update=None):
        while not stop.is_set():
            try:
                rows, title = self.step()
                if on_update:
                    on_update(rows, title)
            except Exception as exc:    # keep the loop alive
                self.state.add_event("engine", f"step failed: {exc!r}")
            stop.wait(REFRESH_SECONDS)
