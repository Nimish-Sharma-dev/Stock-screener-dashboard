"""Daily history: batches of 5, UTC dates, rate limiter, symbol validation, paise -> rupees."""
import time
from datetime import datetime, timedelta, timezone

from .settings import (BATCH_PAUSE, BATCH_SIZE, CANDLES, EXCHANGE, IST, LOOKBACK_DAYS,
                       MAX_CALLS_PER_MIN)


def fmt_utc(dt):
    """UTC datetime -> 'YYYY-MM-DDTHH:MM:SS.000Z' as the API expects."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


class RateLimiter:
    """Never more than `limit` calls in any rolling 60 seconds."""

    def __init__(self, limit=MAX_CALLS_PER_MIN):
        self.limit = limit
        self.times = []

    def wait(self):
        now = time.time()
        self.times = [t for t in self.times if now - t <= 60]
        if len(self.times) >= self.limit:
            time.sleep(60 - (now - self.times[0]) + 0.1)
        self.times.append(time.time())


_limiter = RateLimiter()


def fetch_closes(market_data, symbols):
    """{symbol: [(ist_date, close_rupees), ...]} for 1-5 symbols (last 60 candles)."""
    if not 1 <= len(symbols) <= BATCH_SIZE:
        raise ValueError("historical_data takes 1 to 5 symbols per request")
    end = datetime.now(timezone.utc)
    _limiter.wait()
    resp = market_data.historical_data({
        "exchange": EXCHANGE,
        "type": "STOCK",
        "values": symbols,
        "fields": ["close"],
        "startDate": fmt_utc(end - timedelta(days=LOOKBACK_DAYS)),
        "endDate": fmt_utc(end),
        "interval": "1d",
        "intraDay": False,
        "realTime": False,
    })
    out = {}
    for chart in resp.result or []:
        for per_symbol in chart.values or []:
            for sym, series in per_symbol.items():
                pts = (series.close or [])[-CANDLES:]
                # timestamps are nanoseconds; values are integer paise
                out[sym] = [(datetime.fromtimestamp(p.timestamp / 1e9, IST).date(), p.value / 100.0)
                            for p in pts]
    return out


def validate_watchlist(instruments, symbols, emit):
    """Keep only symbols present in the instruments master (no guessing)."""
    df = instruments.get_instruments_dataframe(exchange=EXCHANGE)
    if "stock_name" not in df.columns:
        emit("history", "'stock_name' column missing; skipping symbol validation")
        return list(symbols)
    known = set(df["stock_name"])
    good = []
    for s in symbols:
        if s in known:
            good.append(s)
        else:
            emit("history", f"dropping {s}: not found in the {EXCHANGE} instruments master")
    return good


def load_history(market_data, symbols, emit):
    """Fetch all symbols in batches of 5 with a pause; returns {symbol: info}."""
    base = {}
    today = datetime.now(IST).date()
    for i in range(0, len(symbols), BATCH_SIZE):
        batch = symbols[i:i + BATCH_SIZE]
        emit("history", f"fetching batch {i // BATCH_SIZE + 1}: {batch}")
        try:
            got = fetch_closes(market_data, batch)
        except Exception as exc:
            emit("history", f"batch failed ({exc!r}); skipping {batch}")
            got = {}
        for sym in batch:
            rows = got.get(sym)
            if not rows:
                emit("history", f"{sym}: no candles returned, skipped")
                continue
            last_date = rows[-1][0]
            last_is_today = last_date == today
            base[sym] = {"closes": [c for _, c in rows], "last_date": last_date,
                         "last_is_today": last_is_today}
            emit("history", f"{sym}: {len(rows)} candles, last {last_date}, today {today} -> live price "
                            f"will {'REPLACE' if last_is_today else 'be APPENDED to'} the series")
        if i + BATCH_SIZE < len(symbols):
            time.sleep(BATCH_PAUSE)
    return base
