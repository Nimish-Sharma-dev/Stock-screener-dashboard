"""Thread-safe store shared by the stream callback, the engine and the web server."""
import threading
from collections import deque
from datetime import datetime

from .settings import IST


class State:
    def __init__(self, trade_enabled):
        self._lock = threading.Lock()
        self.trade_enabled = trade_enabled
        self.base = {}              # symbol -> {"closes": [...rupees], "last_date", "last_is_today"}
        self._live_paise = {}       # symbol -> latest price in integer paise
        self._rows = []
        self._title = "STARTING"
        self._order_placed = False
        self._socket = "not connected"
        self._events = deque(maxlen=200)
        self._version = 0

    # ---- written by history / stream ----
    def set_base(self, base):
        with self._lock:
            self.base = base

    def set_live(self, symbol, paise):
        with self._lock:
            self._live_paise[symbol] = paise

    def set_socket(self, text):
        with self._lock:
            self._socket = text
            self._version += 1

    # ---- written by engine / risk / orders ----
    def add_event(self, kind, text):
        stamp = datetime.now(IST).strftime("%H:%M:%S")
        print(f"[{stamp}] [{kind}] {text}", flush=True)
        with self._lock:
            self._events.append({"ts": stamp, "kind": kind, "text": text})
            self._version += 1

    def publish(self, rows, title, order_placed):
        with self._lock:
            self._rows, self._title, self._order_placed = rows, title, order_placed
            self._version += 1

    # ---- read by engine / server ----
    def snapshot_live(self):
        with self._lock:
            return dict(self._live_paise)

    @property
    def version(self):
        with self._lock:
            return self._version

    def view(self):
        with self._lock:
            return {
                "version": self._version,
                "time": datetime.now(IST).strftime("%H:%M:%S"),
                "title": self._title,
                "live": bool(self._live_paise),
                "trade_enabled": self.trade_enabled,
                "order_placed": self._order_placed,
                "socket": self._socket,
                "rows": list(self._rows),
                "events": list(self._events),
            }
