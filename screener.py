"""
screener.py - 20-day z-score screener (Nubra Python SDK 0.5.x)

Run (screen only, never trades):   python screener.py
Run (may place ONE UAT order):     python screener.py --trade

Seven checkpoints, in order:
  1. Log in (PROD for market data; UAT only with --trade)
  2. Fetch 60 daily candles per stock (paise -> rupees)
  3. 20-day mean, standard deviation and z-score of the close
  4. Loop the watchlist in batches of 5 (1 s pause) and print a table sorted by z
  5. Live stream: replace today's close with the live price, reprint every 2 s
  6. Risk rules: max 1 order per run, quantity 1, only if z < -2, never a stretched high
  7. With --trade: on a downward cross through -2, one LIMIT BUY in UAT, then read the status back
"""

import argparse
import statistics
import threading
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo  # Python 3.9+

from nubra_python_sdk.start_sdk import InitNubraSdk, NubraEnv
from nubra_python_sdk.marketdata.market_data import MarketData
from nubra_python_sdk.refdata.instruments import InstrumentData
from nubra_python_sdk.trading.trading_data import NubraTrader
from nubra_python_sdk.ticker import websocketdata

# ---------------------------------------------------------------------------
# Settings (everything tunable lives here)
# ---------------------------------------------------------------------------
# Top 16 NIFTY 50 stocks by index weight, from the 19-Aug-2026 constituent file
# (HDFC Bank 10.01% ... Sun Pharma 1.83%). The next one, HUL, is 1.63%.
# Symbols are checked against the PROD instruments master at start-up; any that
# are not found are dropped with a printed reason (nothing is guessed).
WATCHLIST = [
    "HDFCBANK", "ICICIBANK", "RELIANCE", "BHARTIARTL", "LT", "SBIN", "INFY", "AXISBANK",
    "M&M", "BAJFINANCE", "KOTAKBANK", "ITC", "TCS", "ETERNAL", "TITAN", "SUNPHARMA",
]
EXCHANGE = "NSE"
CANDLES = 60               # daily candles to keep per stock
LOOKBACK_DAYS = 120        # calendar days requested so that >= 60 trading days come back
WINDOW = 20                # z-score window (includes today's close)
BATCH_SIZE = 5             # SDK allows at most 5 symbols per historical request
BATCH_PAUSE = 1.0          # seconds between batches
MAX_CALLS_PER_MIN = 60     # historical data limit
REFRESH_SECONDS = 2.0      # table reprint interval in the live loop
Z_BUY = -2.0               # buy only below this
Z_HIGH = 2.0               # above this is a "stretched high": never buy
ORDER_QTY = 1              # fixed quantity
DELIVERY_TYPE = "IDAY"     # intraday product for the UAT order
STRAT_TAG = "screener-z-cross"  # one tag, hyphens only (SDK rule)

IST = ZoneInfo("Asia/Kolkata")


def fmt_utc(dt):
    """UTC datetime -> the 'YYYY-MM-DDTHH:MM:SS.000Z' string the API expects."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


# ===========================================================================
# CHECKPOINT 1 - Log in
# PROD is used for all market data. UAT (sandbox trading) is only logged in
# when you pass --trade, so a plain run can never touch a trading session.
# ===========================================================================
parser = argparse.ArgumentParser(description="20-day z-score screener")
parser.add_argument("--trade", action="store_true",
                    help="enable the single guarded UAT order (login to UAT)")
args = parser.parse_args()

print("[1] Logging in to PROD for market data ...")
prod = InitNubraSdk(NubraEnv.PROD, env_creds=True)
market_data = MarketData(prod)
prod_instruments = InstrumentData(prod)

uat = uat_instruments = uat_trader = None
if args.trade:
    print("[1] --trade given: logging in to UAT for the one allowed order ...")
    uat = InitNubraSdk(NubraEnv.UAT, env_creds=True)
    uat_instruments = InstrumentData(uat)
    uat_trader = NubraTrader(uat)
else:
    print("[1] No --trade flag: UAT is NOT logged in, no orders can be placed.")


# ===========================================================================
# CHECKPOINT 2 - Fetch 60 daily candles and convert paise to rupees
# One request carries at most 5 symbols. Dates are sent in UTC, intraDay is
# False (so past days are included), and prices come back as integer paise.
# A small limiter keeps us under 60 requests per minute.
# ===========================================================================
_call_times = []


def respect_rate_limit():
    """Sleep if 60 historical calls were already made in the last 60 seconds."""
    now = time.time()
    while _call_times and now - _call_times[0] > 60:
        _call_times.pop(0)
    if len(_call_times) >= MAX_CALLS_PER_MIN:
        wait = 60 - (now - _call_times[0]) + 0.1
        print(f"[2] Rate limit reached, sleeping {wait:.1f}s")
        time.sleep(wait)
    _call_times.append(time.time())


def fetch_closes(symbols):
    """Return {symbol: [(ist_date, close_in_rupees), ...]} with the last 60 candles."""
    if not 1 <= len(symbols) <= BATCH_SIZE:
        raise ValueError("historical_data takes 1 to 5 symbols per request")
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=LOOKBACK_DAYS)
    respect_rate_limit()
    resp = market_data.historical_data({
        "exchange": EXCHANGE,
        "type": "STOCK",
        "values": symbols,
        "fields": ["close"],
        "startDate": fmt_utc(start),
        "endDate": fmt_utc(end),
        "interval": "1d",
        "intraDay": False,
        "realTime": False,
    })
    out = {}
    for chart in resp.result or []:
        for per_symbol in chart.values or []:
            for sym, series in per_symbol.items():
                points = (series.close or [])[-CANDLES:]
                # timestamps are nanoseconds; values are paise -> divide by 100
                out[sym] = [
                    (datetime.fromtimestamp(p.timestamp / 1e9, IST).date(), p.value / 100.0)
                    for p in points
                ]
    return out


def validate_watchlist(symbols):
    """Keep only symbols that exist in the PROD instruments master (no guessing)."""
    df = prod_instruments.get_instruments_dataframe(exchange=EXCHANGE)
    if "stock_name" not in df.columns:
        print("[2] WARNING: 'stock_name' column missing; skipping symbol validation "
              "(missing symbols will still be reported after the fetch).")
        return list(symbols)
    known = set(df["stock_name"])
    good = []
    for s in symbols:
        if s in known:
            good.append(s)
        else:
            print(f"[2] Dropping {s}: not found in the {EXCHANGE} instruments master.")
    return good


# ===========================================================================
# CHECKPOINT 3 - 20-day mean, standard deviation and z-score
# Uses the last 20 closes (today included). Sample standard deviation (n-1).
# z = (latest close - mean) / std. If std is 0, z is undefined, so we say why.
# ===========================================================================
def compute_stats(closes):
    """Return a dict with close/mean/std/z, or z=None plus a reason."""
    if len(closes) < WINDOW:
        return {"close": closes[-1] if closes else None, "mean": None, "std": None,
                "z": None, "reason": f"only {len(closes)} closes, need {WINDOW}"}
    window = closes[-WINDOW:]
    mean = statistics.mean(window)
    std = statistics.stdev(window)
    close = window[-1]
    if std == 0:
        return {"close": close, "mean": mean, "std": std, "z": None, "reason": "std is 0"}
    return {"close": close, "mean": mean, "std": std, "z": (close - mean) / std, "reason": ""}


# ===========================================================================
# CHECKPOINT 4 - Batch loop and sorted table
# 16 symbols -> 4 requests of up to 5, with a 1 second pause between batches.
# The table is sorted by z, most oversold (lowest z) first.
# ===========================================================================
def print_table(rows, title):
    print(f"\n=== {title}  ({datetime.now(IST):%H:%M:%S} IST) ===")
    print(f"{'SYMBOL':<12}{'CLOSE':>10}{'MEAN20':>10}{'STD20':>9}{'Z':>8}  SRC   NOTE")
    ordered = sorted(rows, key=lambda r: (r["z"] is None, r["z"] if r["z"] is not None else 0))
    for r in ordered:
        def f(v, w, d=2):
            return f"{v:>{w}.{d}f}" if v is not None else f"{'n/a':>{w}}"
        print(f"{r['symbol']:<12}{f(r['close'], 10)}{f(r['mean'], 10)}{f(r['std'], 9)}"
              f"{f(r['z'], 8)}  {r['src']:<5} {r['reason']}")


def load_history(symbols):
    """Fetch every symbol in batches of 5 and return {symbol: info}."""
    base = {}
    today = datetime.now(IST).date()
    for i in range(0, len(symbols), BATCH_SIZE):
        batch = symbols[i:i + BATCH_SIZE]
        print(f"[4] Fetching batch {i // BATCH_SIZE + 1}: {batch}")
        try:
            got = fetch_closes(batch)
        except Exception as exc:
            print(f"[4] Batch failed ({exc!r}); skipping {batch}")
            got = {}
        for sym in batch:
            rows = got.get(sym)
            if not rows:
                print(f"[4] {sym}: no candles returned, skipped.")
                continue
            last_date = rows[-1][0]
            # Does the history already contain a (partial) candle for today?
            last_is_today = (last_date == today)
            base[sym] = {"closes": [c for _, c in rows],
                         "last_date": last_date, "last_is_today": last_is_today}
            print(f"[4] {sym}: {len(rows)} candles, last candle {last_date}, today {today} "
                  f"-> live price will {'REPLACE' if last_is_today else 'be APPENDED to'} the series")
        if i + BATCH_SIZE < len(symbols):
            time.sleep(BATCH_PAUSE)
    return base


# ===========================================================================
# CHECKPOINT 6 - Risk rules (hard-coded, every refusal says why)
#   * at most one order per run          * quantity is always 1
#   * only if z < -2                      * never buy a stretched high (z > +2)
# ===========================================================================
order_placed = False          # flipped to True *before* the order is sent
_refusals_seen = set()        # so the same refusal is not printed every 2 seconds


def refuse(sym, reason):
    key = (sym, reason)
    if key not in _refusals_seen:
        _refusals_seen.add(key)
        print(f"[6] REFUSED {sym}: {reason}")


def risk_check(sym, z):
    """Return True if an order is allowed; otherwise print why not and return False."""
    if not args.trade:
        refuse(sym, "trading is disabled (run with --trade to allow one UAT order)")
        return False
    if order_placed:
        refuse(sym, "one order per run already used")
        return False
    if z is None:
        refuse(sym, "z-score is undefined")
        return False
    if z > Z_HIGH:
        refuse(sym, f"z={z:.2f} is a stretched high (> {Z_HIGH}); never buy highs")
        return False
    if not z < Z_BUY:
        refuse(sym, f"z={z:.2f} is not below {Z_BUY}")
        return False
    return True  # quantity is fixed at ORDER_QTY (1), so there is nothing else to check


# ===========================================================================
# CHECKPOINT 7 - The guarded UAT order
# LIMIT BUY, quantity 1, at the last live price (paise) rounded to the UAT tick
# size using integer math. ref_id and tick_size are resolved in UAT, because
# UAT and PROD ref_ids differ. The order status is then read back.
# ===========================================================================
def place_uat_order(sym, live_paise):
    global order_placed
    order_placed = True  # set first so a crash mid-call can never lead to a second order
    inst = uat_instruments.get_instrument_by_symbol(sym, exchange=EXCHANGE)
    if inst is None:
        print(f"[7] {sym} not found in UAT instruments; no order sent.")
        return
    tick = int(inst.tick_size)
    price = max(((int(live_paise) + tick // 2) // tick) * tick, tick)  # nearest multiple of tick
    print(f"[7] BUY {ORDER_QTY} {sym} (UAT ref_id={inst.ref_id}) LIMIT @ {price} paise "
          f"(= Rs {price / 100:.2f}, tick {tick}, live was {live_paise})")
    result = uat_trader.create_order({
        "refId": inst.ref_id,
        "qty": ORDER_QTY,
        "side": "BUY",
        "deliveryType": DELIVERY_TYPE,
        "priceType": "LIMIT",
        "validityType": "DAY",
        "isMultiLeg": False,
        "executionMode": "ENTRY",
        "entryPrice": price,
        "stratTags": [STRAT_TAG],
    })
    order = result.orders[0]
    order_id = order.intentOrderId
    print(f"[7] Order accepted by API, intentOrderId={order_id}, initial status={order.status}")

    latest = order
    for _ in range(5):  # read the status back for up to ~5 seconds
        time.sleep(1)
        found = uat_trader.get_order(order_id)
        if found:
            latest = found[0]
            if any(s in str(latest.status).upper()
                   for s in ("EXECUTED", "REJECTED", "CANCELLED", "EXPIRED")):
                break
    print(f"[7] Status read back: {latest.status} | filled {latest.filledQty}/{latest.orderQty}"
          f" | rejection: {getattr(latest, 'rejectionMsg', None) or '-'}")


# ===========================================================================
# CHECKPOINT 5 - Live stream and 2-second refresh
# The websocket callback only stores the latest price (index_value is PAISE).
# The main loop wakes every 2 s, swaps today's close for the live price,
# recomputes z, reprints the table and checks for a downward cross of -2.
# ===========================================================================
live_paise = {}
live_lock = threading.Lock()
_unknown_names = set()


def on_index_data(msg):
    name = getattr(msg, "indexname", None)
    if name not in WATCH_SET:
        if name not in _unknown_names:
            _unknown_names.add(name)
            print(f"[5] ignoring update for unexpected name: {name!r}")
        return
    with live_lock:
        live_paise[name] = msg.index_value  # integer paise


def build_series(info, paise):
    """History + live price, with today's close replaced (or appended if absent)."""
    if paise is None:
        return info["closes"], "hist"
    live_rupees = paise / 100.0
    if info["last_is_today"]:
        return info["closes"][:-1] + [live_rupees], "live"
    return info["closes"] + [live_rupees], "live"


def main():
    global WATCH_SET

    symbols = validate_watchlist(WATCHLIST)
    if not symbols:
        print("No valid symbols; exiting.")
        return
    WATCH_SET = set(symbols)

    # --- checkpoints 2-4: history, stats, first table ---
    base = load_history(symbols)
    if not base:
        print("No history could be loaded; exiting.")
        return
    first_rows = []
    for sym, info in base.items():
        st = compute_stats(info["closes"])
        first_rows.append({"symbol": sym, "src": "hist", **st})
    print_table(first_rows, "Daily closes only (checkpoint 4)")

    # --- checkpoint 5: live stream ---
    def on_connect(msg):
        print(f"[5] socket: {msg}")

    def on_close(reason):
        print(f"[5] socket closed: {reason}")

    def on_error(err):
        print(f"[5] socket error: {err}")

    socket = websocketdata.NubraDataSocket(
        client=prod,
        on_index_data=on_index_data,
        on_connect=on_connect,
        on_close=on_close,
        on_error=on_error,
    )
    socket.connect()
    socket.subscribe(list(base.keys()), data_type="index", exchange=EXCHANGE)
    threading.Thread(target=socket.keep_running, daemon=True).start()
    print(f"[5] Subscribed to {len(base)} symbols. Refreshing every {REFRESH_SECONDS}s. Ctrl+C to stop.")

    prev_z = {}
    try:
        while True:
            time.sleep(REFRESH_SECONDS)
            with live_lock:
                snap = dict(live_paise)

            rows = []
            for sym, info in base.items():
                series, src = build_series(info, snap.get(sym))
                st = compute_stats(series)
                rows.append({"symbol": sym, "src": src, **st})

                if src != "live":
                    continue  # only act on live data
                z = st["z"]
                before = prev_z.get(sym)
                if z is not None:
                    prev_z[sym] = z
                if z is None or before is None:
                    continue  # first live reading just seeds the comparison

                crossed_down = before >= Z_BUY and z < Z_BUY
                if crossed_down:
                    print(f"[5] {sym}: z crossed down through {Z_BUY} ({before:.2f} -> {z:.2f})")
                    if risk_check(sym, z):
                        try:
                            place_uat_order(sym, snap[sym])
                        except Exception as exc:
                            print(f"[7] Order step failed: {exc!r} (no further orders this run)")
                elif z < Z_BUY:
                    refuse(sym, f"z={z:.2f} is below {Z_BUY} but did not cross down through it "
                                f"during this run")
                elif z > Z_HIGH:
                    refuse(sym, f"z={z:.2f} is a stretched high (> {Z_HIGH}); never buy highs")

            title = "LIVE" if snap else "WAITING FOR LIVE PRICES (market closed?) - showing daily closes"
            print_table(rows, title)
    except KeyboardInterrupt:
        print("\nStopped by user.")


if __name__ == "__main__":
    main()