"""Pure maths. No SDK, no I/O: easy to test."""
import statistics

from .settings import WINDOW


def build_series(closes, last_is_today, live_rupees):
    """Daily closes plus the live price.
    If history already holds today's (partial) candle, replace it; otherwise append.
    With no live price the closes are returned unchanged."""
    if live_rupees is None:
        return list(closes)
    if last_is_today:
        return list(closes[:-1]) + [live_rupees]
    return list(closes) + [live_rupees]


def compute_stats(closes, window=WINDOW):
    """Mean, sample std (n-1) and z of the last close over the last `window` closes.
    z is None, with a reason, when it cannot be computed."""
    if len(closes) < window:
        return {"close": closes[-1] if closes else None, "mean": None, "std": None,
                "z": None, "reason": f"only {len(closes)} closes, need {window}"}
    win = closes[-window:]
    mean = statistics.mean(win)
    std = statistics.stdev(win)
    close = win[-1]
    if std == 0:
        return {"close": close, "mean": mean, "std": std, "z": None, "reason": "std is 0"}
    return {"close": close, "mean": mean, "std": std, "z": (close - mean) / std, "reason": ""}
