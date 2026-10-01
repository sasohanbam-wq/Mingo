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
    state, _ = m.classify(False, gate, "verified", 80, 95)
    assert state == "gray"


def test_first_failure_or_unverified_cannot_create_definitive_green():
    gate = {
        "invalidated": False,
        "overheated": False,
        "setup_pass": True,
        "setup_type": "trend",
    }
    state, _ = m.classify(True, gate, "legacy_unverified", None, 95)
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
    # This test isolates the pullback gate; overheat behavior is tested separately.
    t["rsi14_wilder"] = 60.0
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


def test_benchmark_mismatch_withholds_relative_metric_not_price_tech():
    d = frame(np.linspace(80, 100, 80))
    b = frame(np.linspace(90, 105, 80))
    t = m.technical_metrics(d, b, relative_valid=False)
    assert t["relative_return_score"] is None
    assert t["relative_return_status"].startswith("N/A")
    assert isinstance(t["technical_score"], float)


def test_research_score_requires_all_three_verified():
    r={"F":{"score":80,"status":"verified"},"E":{"score":70,"status":"verified"},"V":{"score":60,"status":"verified"}}
    score,status=m.compute_research_score(r)
    assert score == 71.2
    assert status == "verified"
    r["E"]={"score":None,"status":"N/A"}
    score,status=m.compute_research_score(r)
    assert score is None
    assert status.startswith("N/A")


def test_setup_pass_with_verified_research_below_70_is_not_green():
    gate={"invalidated":False,"overheated":False,"setup_pass":True,"setup_type":"trend"}
    state,label=m.classify(True,gate,"verified",61.0,90)
    assert state == "blue"
    assert "61.0" in label


def test_setup_pass_with_verified_research_at_70_can_be_green():
    gate={"invalidated":False,"overheated":False,"setup_pass":True,"setup_type":"trend"}
    state,label=m.classify(True,gate,"verified",70.0,90)
    assert state == "green"


def test_manual_snapshot_reprices_without_replacing_completed_indicators():
    row = {
        "quote_as_of": "2026-09-30", "execution_score": 70,
        "ma20": 95, "state": "yellow", "label": "대기",
        "evidence_status": "legacy_unverified", "research_score": None,
    }
    context = {"calculated_at": "2026-10-01T12:00:00+09:00"}
    result = m.apply_manual_snapshot(
        row, 105, "2026-10-01T11:59:00+09:00",
        {"buy": [100, 110], "trigger": 120, "stop": 90}, context
    )
    assert result["price"] == 105
    assert result["state"] == "blue"
    assert result["execution_score"] == 78
    assert result["quote_as_of"] == "2026-09-30"
    assert result["price_mode"] == "manual_snapshot"


def test_manual_snapshot_cannot_lift_overheated_red():
    row = {
        "quote_as_of": "2026-09-30", "execution_score": 60,
        "ma20": 95, "state": "red", "label": "🔴 보류",
        "evidence_status": "legacy_unverified", "research_score": None,
        "overheated": True, "invalidated": False,
    }
    context = {"calculated_at": "2026-10-01T12:00:00+09:00"}
    result = m.apply_manual_snapshot(
        row, 105, "2026-10-01T11:59:00+09:00",
        {"buy": [100, 110], "trigger": 120, "stop": 90}, context
    )
    assert result["price"] == 105
    assert result["state"] == "red"


def test_manual_snapshot_cannot_lift_invalidated_red():
    row = {
        "quote_as_of": "2026-09-30", "execution_score": 40,
        "ma20": 95, "state": "red", "label": "🔴 보류",
        "evidence_status": "legacy_unverified", "research_score": None,
        "overheated": False, "invalidated": True,
    }
    context = {"calculated_at": "2026-10-01T12:00:00+09:00"}
    result = m.apply_manual_snapshot(
        row, 105, "2026-10-01T11:59:00+09:00",
        {"buy": [100, 110], "trigger": 120, "stop": 90}, context
    )
    assert result["state"] == "red"


def test_manual_snapshot_trigger_beyond_8pct_is_not_a_pass():
    row = {
        "quote_as_of": "2026-09-30", "execution_score": 70,
        "ma20": 95, "state": "yellow", "label": "대기",
        "evidence_status": "legacy_unverified", "research_score": None,
        "overheated": False, "invalidated": False,
    }
    context = {"calculated_at": "2026-10-01T12:00:00+09:00"}
    result = m.apply_manual_snapshot(
        row, 131, "2026-10-01T11:59:00+09:00",
        {"buy": [100, 110], "trigger": 120, "stop": 90}, context
    )
    assert result["state"] == "yellow"
    assert result["live_triggered"] is False
