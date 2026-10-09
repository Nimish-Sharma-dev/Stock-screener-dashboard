"""Start-up wiring shared by cli.py and app/server.py (so neither duplicates it)."""
import threading

from .engine import Engine
from .history import load_history, validate_watchlist
from .orders import UatOrderPlacer
from .risk import RiskGate
from .session import login_prod, login_uat
from .settings import WATCHLIST
from .state import State
from .stream import start_stream


class Runtime:
    def __init__(self, trade=False):
        self.trade = trade
        self.state = State(trade_enabled=trade)
        self.stop = threading.Event()
        self.engine = None

    def start(self):
        emit = self.state.add_event
        emit("login", "logging in to PROD for market data ...")
        prod_client, market_data, prod_instruments = login_prod()

        placer = None
        if self.trade:
            emit("login", "--trade given: logging in to UAT for the one allowed order ...")
            _, uat_instruments, uat_trader = login_uat()
            placer = UatOrderPlacer(uat_instruments, uat_trader, emit)
        else:
            emit("login", "no --trade flag: UAT is NOT logged in, no orders can be placed")

        symbols = validate_watchlist(prod_instruments, WATCHLIST, emit)
        if not symbols:
            raise RuntimeError("no valid symbols in the watchlist")
        base = load_history(market_data, symbols, emit)
        if not base:
            raise RuntimeError("no history could be loaded")
        self.state.set_base(base)

        risk = RiskGate(self.trade, emit)
        self.engine = Engine(self.state, risk, placer)
        self.engine.step()                      # first table from daily closes only
        start_stream(prod_client, list(base.keys()), self.state)
        return self
