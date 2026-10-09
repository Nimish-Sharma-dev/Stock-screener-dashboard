"""All tunable settings in one place. No SDK imports, so tests can import this freely."""
from zoneinfo import ZoneInfo

# Top 16 NIFTY 50 stocks by index weight (19-Aug-2026 constituent file; next is HUL at 1.63%).
# Symbols are checked against the PROD instruments master at start-up; unknown ones are dropped.
WATCHLIST = [
    "HDFCBANK", "ICICIBANK", "RELIANCE", "BHARTIARTL", "LT", "SBIN", "INFY", "AXISBANK",
    "M&M", "BAJFINANCE", "KOTAKBANK", "ITC", "TCS", "ETERNAL", "TITAN", "SUNPHARMA",
]
EXCHANGE = "NSE"

CANDLES = 60              # daily candles kept per stock
LOOKBACK_DAYS = 120       # calendar days requested so >= 60 trading days come back
WINDOW = 20               # z-score window (includes today's close)
BATCH_SIZE = 5            # SDK allows at most 5 symbols per historical request
BATCH_PAUSE = 1.0         # seconds between history batches
MAX_CALLS_PER_MIN = 60    # historical data limit
REFRESH_SECONDS = 2.0     # engine recompute interval

Z_BUY = -2.0              # buy only below this
Z_HIGH = 2.0              # above this is a stretched high: never buy
ORDER_QTY = 1
DELIVERY_TYPE = "IDAY"
STRAT_TAG = "screener-z-cross"   # one tag, hyphens only (SDK rule)

HOST = "127.0.0.1"
PORT = 8000

IST = ZoneInfo("Asia/Kolkata")
