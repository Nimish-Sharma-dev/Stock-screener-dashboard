from screener.stats import build_series


def test_replace_when_history_has_today():
    assert build_series([1, 2, 3], True, 9.0) == [1, 2, 9.0]


def test_append_when_history_lacks_today():
    assert build_series([1, 2, 3], False, 9.0) == [1, 2, 3, 9.0]


def test_no_live_price_leaves_closes_unchanged():
    assert build_series([1, 2, 3], True, None) == [1, 2, 3]
    assert build_series([1, 2, 3], False, None) == [1, 2, 3]
