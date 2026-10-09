import math

import pytest

from screener.stats import compute_stats


def test_known_values():
    closes = list(range(1, 21))                # 1..20: mean 10.5, sample variance 35
    st = compute_stats(closes)
    assert st["mean"] == pytest.approx(10.5)
    assert st["std"] == pytest.approx(math.sqrt(35))
    assert st["z"] == pytest.approx((20 - 10.5) / math.sqrt(35))
    assert st["close"] == 20


def test_only_last_20_count():
    closes = [1000.0] * 40 + list(range(1, 21))
    assert compute_stats(closes)["mean"] == pytest.approx(10.5)


def test_std_zero_gives_no_z():
    st = compute_stats([5.0] * 20)
    assert st["z"] is None and st["reason"] == "std is 0"


def test_too_few_closes():
    st = compute_stats(list(range(19)))
    assert st["z"] is None and "need 20" in st["reason"]
