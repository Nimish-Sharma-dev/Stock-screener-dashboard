from screener.risk import RiskGate


def make(trade):
    events = []
    return RiskGate(trade, lambda kind, text: events.append((kind, text))), events


def test_refused_when_trading_disabled():
    gate, events = make(False)
    assert gate.approve("TCS", -2.5) is False
    assert "disabled" in events[0][1]


def test_one_order_per_run():
    gate, events = make(True)
    assert gate.approve("TCS", -2.5) is True
    assert gate.approve("INFY", -2.6) is False
    assert "one order per run" in events[-1][1]


def test_not_below_threshold():
    gate, _ = make(True)
    assert gate.approve("TCS", -1.0) is False
    assert gate.order_placed is False


def test_stretched_high_never_buys():
    gate, events = make(True)
    assert gate.approve("TCS", 2.5) is False
    assert "stretched high" in events[0][1]


def test_undefined_z():
    gate, _ = make(True)
    assert gate.approve("TCS", None) is False


def test_refusal_printed_once():
    gate, events = make(True)
    gate.refuse("TCS", "z=-3.00 is below -2.0 but did not cross", key="no-cross")
    gate.refuse("TCS", "z=-3.10 is below -2.0 but did not cross", key="no-cross")
    assert len(events) == 1
