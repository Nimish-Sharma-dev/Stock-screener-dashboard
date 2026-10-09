"""
NIFTY 1-min candle colour strategy (Nubra Python SDK 0.5.x, V3 trading flow)

Rules implemented:
  - Track NIFTY 1-minute candles via the realtime OHLCV stream.
  - When a candle CLOSES:
        green (close > open) -> want to hold ATM CE (nearest expiry)
        red   (close < open) -> want to hold ATM PE (nearest expiry)
  - Entry happens at the start of the next candle (i.e. right after the previous one closes).
  - If already holding the wanted side -> hold.
  - If colour flipped -> SELL the current option, then immediately BUY the opposite ATM option.
  - Orders: MARKET + IOC. Quantity: LOTS x lot_size. No stop-loss, no target.

Items below marked "CONFIG" are NOT specified in the strategy brief, so they are
explicit settings you should confirm rather than hidden assumptions.
"""

import queue
import threading
import time
from datetime import datetime
from zoneinfo import ZoneInfo  # Python 3.9+

from nubra_python_sdk.start_sdk import InitNubraSdk, NubraEnv
from nubra_python_sdk.marketdata.market_data import MarketData
from nubra_python_sdk.trading.trading_data import NubraTrader
from nubra_python_sdk.ticker import websocketdata

# --------------------------------------------------------------------------
# CONFIG
# --------------------------------------------------------------------------
ENV = NubraEnv.UAT          # CONFIG: UAT (sandbox) by default. Change to NubraEnv.PROD for live.
UNDERLYING = "NIFTY"
EXCHANGE = "NSE"
CANDLE_INTERVAL = "1m"
LOTS = 10                   # from your brief
DELIVERY_TYPE = "IDAY"      # CONFIG: "IDAY" (intraday) or "CNC"
SQUARE_OFF_TIME = None      # CONFIG: e.g. "15:15" (IST) to exit and stop trading; None = disabled
STRAT_TAG = "nifty-candle-colour"  # one tag, hyphens only (SDK rule)

IST = ZoneInfo("Asia/Kolkata")
FINAL_STATUSES = ("EXECUTED", "REJECTED", "CANCELLED", "EXPIRED")


def log(msg):
    print(f"[{datetime.now(IST).strftime('%H:%M:%S')}] {msg}", flush=True)


# --------------------------------------------------------------------------
# SDK setup
# --------------------------------------------------------------------------
nubra = InitNubraSdk(ENV, env_creds=True)
market_data = MarketData(nubra)
trader = NubraTrader(nubra)


# --------------------------------------------------------------------------
# Candle tracking (runs in the websocket thread, only pushes finished candles)
# --------------------------------------------------------------------------
class CandleTracker:
    """
    The OHLCV stream sends the *current* candle bucket on every update.
    A candle is considered finished when an update arrives with a newer
    bucket_timestamp; the last values seen for the old bucket are its OHLC.
    """

    def __init__(self, out_queue):
        self.out = out_queue
        self.bucket = None
        self.open = None
        self.close = None

    def on_ohlcv(self, msg):
        if getattr(msg, "indexname", None) != UNDERLYING:
            return
        bucket = msg.bucket_timestamp

        if self.bucket is None:
            self.bucket = bucket
        elif bucket < self.bucket:
            return  # stale/out-of-order update
        elif bucket > self.bucket:
            # previous candle just closed
            self.out.put(("CANDLE", self.open, self.close))
            self.bucket = bucket

        self.open = msg.open
        self.close = msg.close


# --------------------------------------------------------------------------
# Strategy
# --------------------------------------------------------------------------
class Strategy:
    def __init__(self):
        self.position = None  # {"side": "CE"/"PE", "ref_id": int, "qty": int}
        self.finished = False

    # ---- instrument resolution -------------------------------------------
    def resolve_atm_contracts(self):
        """Return {"CE": OptionData, "PE": OptionData} for nearest expiry, ATM strike."""
        first = market_data.option_chain(UNDERLYING, exchange=EXCHANGE).chain
        expiries = sorted(first.all_expiries or [])
        if not expiries:
            raise RuntimeError("No expiries returned in option chain")
        nearest = expiries[0]

        if str(first.expiry) == str(nearest):
            chain = first
        else:
            chain = market_data.option_chain(UNDERLYING, expiry=nearest, exchange=EXCHANGE).chain

        atm = chain.at_the_money_strike
        ce = next((o for o in chain.ce if o.strike_price == atm), None)
        pe = next((o for o in chain.pe if o.strike_price == atm), None)
        if ce is None or pe is None:
            raise RuntimeError(f"ATM strike {atm} missing CE/PE in expiry {nearest}")
        log(f"Resolved expiry={nearest} ATM strike={atm} CE ref_id={ce.ref_id} PE ref_id={pe.ref_id}")
        return {"CE": ce, "PE": pe}

    # ---- order helpers -----------------------------------------------------
    def place_market(self, ref_id, qty, side):
        result = trader.create_order({
            "refId": ref_id,
            "qty": qty,
            "side": side,
            "deliveryType": DELIVERY_TYPE,
            "priceType": "MARKET",
            "validityType": "IOC",
            "isMultiLeg": False,
            "executionMode": "ENTRY",
            "stratTags": [STRAT_TAG],
        })
        order = result.orders[0]
        if getattr(order, "rejectionMsg", None):
            log(f"Order {order.intentOrderId} rejection: {order.rejectionMsg}")
        return order.intentOrderId

    def confirm_fill(self, order_id, tries=8, delay=0.5):
        """Poll the order until it reaches a final status; return filled quantity."""
        filled = 0
        for _ in range(tries):
            time.sleep(delay)
            found = trader.get_order(order_id)
            if not found:
                continue
            order = found[0]
            filled = int(order.filledQty or 0)
            status = str(order.status).upper()
            if any(s in status for s in FINAL_STATUSES):
                if getattr(order, "rejectionMsg", None):
                    log(f"Order {order_id} {status}: {order.rejectionMsg}")
                return filled
        log(f"Order {order_id} not final after polling; filled so far = {filled}")
        return filled

    # ---- actions -------------------------------------------------------------
    def enter(self, side, contract):
        qty = LOTS * int(contract.lot_size)
        log(f"BUY {side} ref_id={contract.ref_id} qty={qty} ({LOTS} lots x {contract.lot_size})")
        order_id = self.place_market(contract.ref_id, qty, "BUY")
        filled = self.confirm_fill(order_id)
        if filled > 0:
            self.position = {"side": side, "ref_id": contract.ref_id, "qty": filled}
            if filled < qty:
                log(f"WARNING: partial entry fill {filled}/{qty}")
            log(f"Position open: {self.position}")
        else:
            log("Entry not filled; no position opened.")

    def exit_position(self, max_attempts=3):
        """Sell the whole open position. Returns True when fully closed."""
        pos = self.position
        remaining = pos["qty"]
        for attempt in range(1, max_attempts + 1):
            log(f"SELL {pos['side']} ref_id={pos['ref_id']} qty={remaining} (attempt {attempt})")
            order_id = self.place_market(pos["ref_id"], remaining, "SELL")
            filled = self.confirm_fill(order_id)
            remaining -= filled
            pos["qty"] = remaining
            if remaining <= 0:
                self.position = None
                log("Position closed.")
                return True
        log(f"WARNING: could not fully exit; {remaining} qty still open in {pos}")
        return False

    # ---- signal handling -------------------------------------------------------
    def on_candle(self, o, c):
        if self.finished:
            return
        if o is None or c is None:
            return

        if c > o:
            colour, want = "GREEN", "CE"
        elif c < o:
            colour, want = "RED", "PE"
        else:
            log("Candle is a doji (open == close): no action, holding current position.")
            return

        log(f"Closed candle {colour} (open={o}, close={c}) -> want {want}")

        if self.position and self.position["side"] == want:
            log(f"Already holding {want}; hold.")
            return

        try:
            # resolve the new contract first so exit -> entry gap is minimal
            target = self.resolve_atm_contracts()[want]
            if self.position:
                if not self.exit_position():
                    return  # do not open a new leg while the old one is still open
            self.enter(want, target)
        except Exception as exc:  # keep the strategy loop alive
            log(f"ERROR handling candle: {exc!r}")

    def square_off_due(self):
        if not SQUARE_OFF_TIME or self.finished:
            return False
        return datetime.now(IST).strftime("%H:%M") >= SQUARE_OFF_TIME

    def square_off(self):
        log(f"Square-off time {SQUARE_OFF_TIME} reached.")
        if self.position:
            self.exit_position()
        self.finished = True
        log("Trading stopped for the day.")

    # ---- worker loop -------------------------------------------------------------
    def run(self, q):
        while True:
            if self.square_off_due():
                self.square_off()
            try:
                kind, o, c = q.get(timeout=1)
            except queue.Empty:
                continue
            if kind == "CANDLE":
                self.on_candle(o, c)


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def main():
    q = queue.Queue()
    tracker = CandleTracker(q)
    strategy = Strategy()

    threading.Thread(target=strategy.run, args=(q,), daemon=True).start()

    def on_connect(msg):
        log(f"[socket] {msg}")

    def on_close(reason):
        log(f"[socket closed] {reason}  (no auto-reconnect; check open positions!)")

    def on_error(err):
        log(f"[socket error] {err}")

    socket = websocketdata.NubraDataSocket(
        client=nubra,
        on_ohlcv_data=tracker.on_ohlcv,
        on_connect=on_connect,
        on_close=on_close,
        on_error=on_error,
    )

    socket.connect()
    socket.subscribe([UNDERLYING], data_type="ohlcv", interval=CANDLE_INTERVAL, exchange=EXCHANGE)
    log(f"Subscribed to {UNDERLYING} {CANDLE_INTERVAL} candles on {EXCHANGE} ({ENV}). Waiting for first candle close...")

    try:
        socket.keep_running()
    except KeyboardInterrupt:
        if strategy.position:
            log(f"Stopped by user. OPEN POSITION NOT CLOSED: {strategy.position}")
        else:
            log("Stopped by user. No open position.")


if __name__ == "__main__":
    main()
