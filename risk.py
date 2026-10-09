"""Hard risk rules. No SDK imports. Every refusal says why (once, to avoid spam)."""
import threading

from .settings import Z_BUY, Z_HIGH


class RiskGate:
    """Rules: trading must be enabled, at most one order per run, quantity is fixed at 1
    (see orders.py), only if z < Z_BUY, never a stretched high (z > Z_HIGH)."""

    def __init__(self, trade_enabled, emit):
        self.trade_enabled = trade_enabled
        self.emit = emit                  # emit(kind, text)
        self.order_placed = False
        self._lock = threading.Lock()
        self._seen = set()

    def refuse(self, symbol, reason, key=None):
        """Print/log a refusal once per (symbol, key)."""
        k = (symbol, key or reason)
        with self._lock:
            if k in self._seen:
                return
            self._seen.add(k)
        self.emit("refused", f"{symbol}: {reason}")

    def _blocking_reason(self, z):
        if not self.trade_enabled:
            return "trading is disabled (start with --trade to allow one UAT order)"
        if self.order_placed:
            return "one order per run already used"
        if z is None:
            return "z-score is undefined"
        if z > Z_HIGH:
            return f"z={z:.2f} is a stretched high (> {Z_HIGH}); never buy highs"
        if not z < Z_BUY:
            return f"z={z:.2f} is not below {Z_BUY}"
        return None

    def approve(self, symbol, z):
        """Atomically check the rules and, if they pass, use up the single order."""
        with self._lock:
            reason = self._blocking_reason(z)
            if reason is None:
                self.order_placed = True
                return True
        self.refuse(symbol, reason)
        return False
