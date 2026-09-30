import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import update_market as m


def frame(closes, highs=None, lows=None, volumes=None):
    n = len(closes)
    idx = pd.date_range("2026-01-02", periods=n, freq="B")
    c = np.array(closes, dtype=float)
    h = np.array(highs if highs is not None else c + 1, dtype=float)
    l = np.array(lows if lows is not None else c - 1, dtype=float)
    v = np.array(volumes if volumes is not None else np.full(n, 100.0), dtype=float)
    o = c - 0.2
    return m.prepare_history(pd.DataFrame(
        {"Open": o, "High": h, "Low": l, "Close": c, "Volume": v},
        index=idx,
    ))


def test_wilder_rsi_monotonic_and_flat():
    assert m.wilder_rsi(pd.Series(range(1, 40))) == 100.0
    assert m.wilder_rsi(pd.Series(range(40, 1, -1))) == 0.0
    assert m.wilder_rsi(pd.Series([10.0] * 40)) == 50.0


def test_high20_uses_actual_high_not_close():
    closes = np.linspace(80, 100, 80)
    highs = closes + 1
    highs[-5] = 110
    d = frame(closes, highs=highs)
    b = frame(np.linspace(90, 105, 80))
    t = m.technical_metrics(d, b)
    assert t["high20_actual"] == 110.0
    assert max(closes[-20:]) < t["high20_actual"]


def test_ma200_is_na_when_history_short():
    d = frame(np.linspace(80, 100, 100))
    b = frame(np.linspace(90, 105, 100))
    t = m.technical_metrics(d, b)
    assert t["ma200"] is None


def test_stale_data_can_never_be_green():
    gate = {
        "invalidated": False,
        "overheated": False,
        "setup_pass": True,
        "setup_type": "trend",
    }
    state, _ = m.classify(False, gate, "verified", 95)
    assert state == "gray"


def test_first_failure_or_unverified_cannot_create_definitive_green():
    gate = {
        "invalidated": False,
        "overheated": False,
        "setup_pass": True,
        "setup_type": "trend",
    }
    state, _ = m.classify(True, gate, "legacy_unverified", 95)
    assert state == "blue"


def test_trend_setup_below_ma20_fails_even_with_good_other_scores():
    closes = list(np.linspace(80, 105, 79)) + [90]
    d = frame(closes)
    b = frame(np.linspace(90, 105, 80))
    t = m.technical_metrics(d, b)
    gate = m.setup_gate(d, t, {
        "type": "trend", "buy": [89, 92], "trigger": 110, "stop": 85
    })
    assert t["price"] < t["ma20"]
    assert gate["setup_pass"] is False
    assert "MA20" in gate["setup_reason"]


def test_pullback_needs_zone_trend_and_reversal():
    closes = list(np.linspace(80, 100, 79)) + [99.8]
    lows = np.array(closes) - 0.5
    lows[-2] = 99.1
    d = frame(closes, lows=lows)
    b = frame(np.linspace(90, 105, 80))
    t = m.technical_metrics(d, b)
    gate = m.setup_gate(d, t, {
        "type": "trend", "buy": [99, 101], "trigger": 105, "stop": 95
    })
    assert gate["in_buy_zone"] is True
    assert gate["above_ma20"] is True
    assert gate["setup_pass"] is True


def test_breakout_requires_actual_cross_and_volume():
    closes = [90.0] * 27 + [98.0, 99.0, 101.0]
    volumes = [100.0] * 29 + [180.0]
    highs = [91.0] * 27 + [99.0, 99.5, 102.0]
    d = frame(closes, highs=highs, volumes=volumes)
    result = m.breakout_confirmation(d, 100.0)
    assert result["passed"] is True
    assert result["volume_ratio"] >= 1.2


def test_outside_buy_zone_and_below_trigger_is_not_pass():
    closes = list(np.linspace(80, 100, 80))
    d = frame(closes)
    b = frame(np.linspace(90, 105, 80))
    t = m.technical_metrics(d, b)
    gate = m.setup_gate(d, t, {
        "type": "trend", "buy": [92, 95], "trigger": 105, "stop": 88
    })
    assert gate["in_buy_zone"] is False
    assert t["price"] < 105
    assert gate["setup_pass"] is False


def test_select_completed_marks_one_day_late_as_stale():
    d = frame(np.linspace(80, 100, 10))
    latest = d["_session_date"].iloc[-1]
    expected = (pd.Timestamp(latest) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    _, asof, valid = m.select_completed(d, expected)
    assert asof == latest
    assert valid is False
