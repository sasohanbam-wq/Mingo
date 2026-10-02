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
    # Production shape: the completed-session gate already passed, so classify
    # made the row blue; the snapshot only confirms it with the live price.
    row = {
        "quote_as_of": "2026-09-30", "execution_score": 70,
        "ma20": 95, "state": "blue", "label": "🔵 셋업 통과 · F/E/V 검증중",
        "evidence_status": "legacy_unverified", "research_score": None,
        "setup_pass": True, "quote_valid": True,
        "overheated": False, "invalidated": False,
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


def _bench(closes_by_ex):
    return {ex: frame(c) for ex, c in closes_by_ex.items()}


def test_regime_attack_from_rising_indices():
    up = list(np.linspace(100, 200, 200))
    bench = _bench({"KS": up, "KQ": up})
    expected = bench["KS"]["_session_date"].iloc[-1]
    r = m.market_regime(bench, expected)
    assert r["level"] == "attack"
    assert r["execution_adjustment"] == 10.0
    assert r["index_extension_ma20_pct"] > 0


def test_regime_defense_from_falling_indices():
    down = list(np.linspace(200, 100, 200))
    bench = _bench({"KS": down, "KQ": down})
    expected = bench["KS"]["_session_date"].iloc[-1]
    r = m.market_regime(bench, expected)
    assert r["level"] == "defense"
    assert r["execution_adjustment"] == -10.0


def test_regime_unknown_without_benchmarks():
    r = m.market_regime({}, "2026-09-30")
    assert r["level"] == "unknown"
    assert r["execution_adjustment"] == 0.0


def test_overheat_extension_is_relative_to_market():
    d = frame([100.0] * 80)
    metrics = {
        "price": 122.0, "ma20": 100.0, "ma50": 95.0,
        "rsi14_wilder": 60.0, "extension_ma20_pct": 22.0, "volume_ratio": 1.0,
    }
    setup = {"type": "trend", "buy": [130, 140], "trigger": 150, "stop": 90}
    absolute = m.setup_gate(d, metrics, setup)
    assert absolute["overheated"] is True
    hot_market = m.setup_gate(d, metrics, setup, regime={
        "level": "attack", "index_extension_ma20_pct": 15.0, "execution_adjustment": 10.0,
    })
    assert hot_market["overheated"] is False
    assert hot_market["excess_extension_ma20_pct"] == 7.0
    cool_market = m.setup_gate(d, metrics, setup, regime={
        "level": "defense", "index_extension_ma20_pct": 5.0, "execution_adjustment": -10.0,
    })
    assert cool_market["overheated"] is True


def test_defense_regime_blocks_breakout():
    closes = [90.0] * 27 + [98.0, 99.0, 101.0]
    volumes = [100.0] * 29 + [180.0]
    highs = [91.0] * 27 + [99.0, 99.5, 102.0]
    d = frame(closes, highs=highs, volumes=volumes)
    b = frame(np.linspace(90, 105, 80))
    t = m.technical_metrics(d, b)
    t["rsi14_wilder"] = 60.0  # isolate the regime block; the RSI gate is tested separately
    setup = {"type": "trend", "buy": [80, 85], "trigger": 100, "stop": 85}
    neutral = m.setup_gate(d, t, setup)
    assert neutral["setup_pass"] is True
    defense = m.setup_gate(d, t, setup, regime={
        "level": "defense", "index_extension_ma20_pct": 0.0, "execution_adjustment": -10.0,
    })
    assert defense["setup_pass"] is False
    assert defense["regime_blocked"] == "breakout"
    assert "방어" in defense["setup_reason"]


def test_defense_regime_pullback_only_in_lower_half():
    closes = list(np.linspace(80, 100, 79)) + [100.6]
    lows = np.array(closes) - 0.5
    lows[-2] = 99.1
    d = frame(closes, lows=lows)
    b = frame(np.linspace(90, 105, 80))
    t = m.technical_metrics(d, b)
    t["rsi14_wilder"] = 60.0
    setup = {"type": "trend", "buy": [99, 101], "trigger": 105, "stop": 95}
    neutral = m.setup_gate(d, t, setup)
    assert neutral["setup_pass"] is True
    defense = m.setup_gate(d, t, setup, regime={
        "level": "defense", "index_extension_ma20_pct": 0.0, "execution_adjustment": -10.0,
    })
    assert defense["setup_pass"] is False
    assert defense["regime_blocked"] == "pullback_upper_half"


def _snap_row(**over):
    row = {
        "quote_as_of": "2026-09-30", "execution_score": 70, "price": 100.0,
        "ma20": 95, "state": "yellow", "label": "🟡 조건부/대기",
        "evidence_status": "legacy_unverified", "research_score": None,
        "setup_pass": False, "quote_valid": True,
        "overheated": False, "invalidated": False,
    }
    row.update(over)
    return row


_SNAP_CTX = {
    "calculated_at": "2026-10-01T12:00:00+09:00",
    "expected_completed_session": "2026-09-30",
}
_SNAP_SETUP = {"buy": [100, 110], "trigger": 120, "stop": 90}


def test_manual_snapshot_does_not_promote_gate_failed_stock_in_zone():
    result = m.apply_manual_snapshot(
        _snap_row(), 105, "2026-10-01T11:59:00+09:00", _SNAP_SETUP, _SNAP_CTX
    )
    assert result["price"] == 105
    assert result["state"] == "yellow"
    assert result["live_in_buy_zone"] is True
    assert result["execution_score"] == 70  # no intraday zone-touch bonus
    assert "승격 안 함" in result["setup_reason"]


def test_manual_snapshot_trigger_touch_is_not_a_promotion():
    result = m.apply_manual_snapshot(
        _snap_row(), 121, "2026-10-01T11:59:00+09:00", _SNAP_SETUP, _SNAP_CTX
    )
    assert result["state"] == "yellow"
    assert result["live_triggered"] is True
    assert "승격 안 함" in result["setup_reason"]


def test_manual_snapshot_downgrades_gate_passed_stock_below_ma20():
    row = _snap_row(state="blue", label="🔵 셋업 통과 · F/E/V 검증중", setup_pass=True)
    result = m.apply_manual_snapshot(
        row, 94, "2026-10-01T11:59:00+09:00", _SNAP_SETUP, _SNAP_CTX
    )
    assert result["state"] == "yellow"
    assert result["execution_score"] == 60


def test_manual_snapshot_never_promotes_stale_data():
    row = _snap_row(state="gray", label="⚪ 데이터 확인 필요", setup_pass=True, quote_valid=False)
    result = m.apply_manual_snapshot(
        row, 105, "2026-10-01T11:59:00+09:00", _SNAP_SETUP, _SNAP_CTX
    )
    assert result["state"] == "gray"


def test_manual_snapshot_rejects_implausible_price():
    row = _snap_row()
    result = m.apply_manual_snapshot(
        row, 200, "2026-10-01T11:59:00+09:00", _SNAP_SETUP, _SNAP_CTX
    )
    assert result["price"] == 100.0
    assert result["state"] == "yellow"
    assert result["snapshot_status"].startswith("rejected")


def test_manual_snapshot_rejects_stale_timestamp():
    row = _snap_row()
    result = m.apply_manual_snapshot(
        row, 105, "2026-09-29T15:30:00+09:00", _SNAP_SETUP, _SNAP_CTX
    )
    assert result["price"] == 100.0
    assert result.get("price_mode") != "manual_snapshot"
    assert result["snapshot_status"].startswith("rejected")


def test_auto_snapshot_market_hours_matrix():
    from datetime import datetime
    from zoneinfo import ZoneInfo
    kst = ZoneInfo("Asia/Seoul")
    at = lambda day, hm: datetime(2026, 10, day, hm // 100, hm % 100, tzinfo=kst)
    # 2026-10-01 is a Thursday; 2026-10-03 is a Saturday
    assert m.should_auto_snapshot(at(1, 1000)) is True
    assert m.should_auto_snapshot(at(1, 900)) is True
    assert m.should_auto_snapshot(at(1, 1540)) is True
    assert m.should_auto_snapshot(at(1, 859)) is False
    assert m.should_auto_snapshot(at(1, 1541)) is False
    assert m.should_auto_snapshot(at(1, 1610)) is False
    assert m.should_auto_snapshot(at(3, 1000)) is False  # weekend
    # explicit flags always win
    assert m.should_auto_snapshot(at(3, 1000), explicit_snapshot=True) is True
    assert m.should_auto_snapshot(at(1, 1000), completed_only=True) is False


def test_parse_stockeasy_rs_extracts_score_and_basis():
    html = (
        '<dl><div><dt class="text-xs text-fg-subtle">종합 RS</dt>'
        '<dd class="mt-1 text-sm font-semibold tabular-nums text-fg">95</dd></div></dl>'
        '<p>심텍은 KOSDAQ 반도체소재 업종 종목으로 시가총액 5.9조 원, '
        '26.10.01 종가 154,500원(+2.79%)입니다.</p>'
    )
    parsed = m.parse_stockeasy_rs(html)
    assert parsed == {"score": 95, "basis_date": "26.10.01", "basis_price": 154500}


def test_parse_stockeasy_rs_missing_or_empty_returns_none():
    assert m.parse_stockeasy_rs("") is None
    assert m.parse_stockeasy_rs("<html>no rs here</html>") is None
    assert m.parse_stockeasy_rs(None) is None


def test_parse_stockeasy_summary_extracts_display_fields():
    html = (
        '<dl><div><dt class="text-xs">시가총액</dt><dd>5.9조 원</dd></div>'
        '<div><dt>52주 고가</dt><dd>164,200원</dd></div>'
        '<div><dt>52주 저가</dt><dd>32,000원</dd></div>'
        '<div><dt>52주 구간 내 위치</dt><dd>96%</dd></div></dl>'
        '<section aria-labelledby="kr-summary-quarterly"><table><tbody>'
        '<tr><th scope="row">26.2Q</th><td>5,146</td><td>629</td><td>-1,168</td></tr>'
        '</tbody></table></section>'
        '<section aria-labelledby="kr-summary-disclosures"><ul>'
        '<li><p class="text-sm text-fg">신규시설투자등</p>'
        '<time dateTime="2026-08-25">26.08.25</time></li></ul></section>'
        '<section aria-labelledby="kr-summary-sector"><ul><li>반도체</li><li>반도체소재</li></ul></section>'
    )
    parsed = m.parse_stockeasy_summary(html)
    assert parsed["market_cap"] == "5.9조 원"
    assert parsed["high52"] == 164200 and parsed["low52"] == 32000
    assert parsed["pos52"] == 96
    assert parsed["quarterly"] == [
        {"q": "26.2Q", "revenue": 5146, "op": 629, "net": -1168}
    ]
    assert parsed["disclosures"] == [{"title": "신규시설투자등", "date": "2026-08-25"}]
    assert parsed["sectors"] == ["반도체", "반도체소재"]
    assert m.parse_stockeasy_summary("") is None
    assert m.parse_stockeasy_summary("<html>nothing</html>") is None
    assert m.parse_stockeasy_summary(None) is None


def test_parse_stockeasy_market_extracts_investor_flows():
    html = (
        '<span class="text-fg-muted whitespace-nowrap">외국인</span>'
        '<div class="bar"></div>'
        '<span class="font-semibold tabular-nums text-right whitespace-nowrap text-stock-down">-23<!-- -->억</span>'
        '<span class="text-fg-muted whitespace-nowrap">기관</span>'
        '<div class="bar"></div>'
        '<span class="font-semibold tabular-nums text-right whitespace-nowrap text-stock-up">+10,001<!-- -->억</span>'
        '<span class="text-fg-muted whitespace-nowrap">개인</span>'
        '<div class="bar"></div>'
        '<span class="font-semibold tabular-nums text-right whitespace-nowrap text-stock-down">-26,124<!-- -->억</span>'
    )
    parsed = m.parse_stockeasy_market(html)
    assert parsed == {"foreign": -23, "institution": 10001, "individual": -26124}
    assert m.parse_stockeasy_market("") is None
    assert m.parse_stockeasy_market(None) is None


def test_build_index_series_shape_and_change():
    import pandas as pd
    df = pd.DataFrame({
        "Close": [100.0, 101.0, 103.0],
        "_session_date": ["2026-09-28", "2026-09-29", "2026-09-30"],
    })
    out = m.build_index_series({"KS": df, "KQ": None})
    assert set(out) == {"KOSPI"}
    assert out["KOSPI"]["close"] == 103.0
    assert out["KOSPI"]["change_pct"] == round((103.0 / 101.0 - 1) * 100, 2)
    assert out["KOSPI"]["series"][-1] == {"d": "09-30", "c": 103.0}
    assert m.build_index_series({}) == {}
    assert m.build_index_series({"KS": None}) == {}


def test_build_index_series_excludes_partial_bar():
    import pandas as pd
    df = pd.DataFrame({
        "Close": [100.0, 101.0, 999.0],
        "_session_date": ["2026-09-28", "2026-09-29", "2026-10-01"],
    })
    out = m.build_index_series({"KS": df}, completed_session="2026-09-29")
    assert out["KOSPI"]["close"] == 101.0
    assert out["KOSPI"]["series"][-1]["d"] == "09-29"


def test_high52_metrics_flag_new_high_close():
    closes = np.linspace(80, 100, 80)
    d = frame(closes)
    b = frame(np.linspace(90, 105, 80))
    t = m.technical_metrics(d, b)
    assert t["new_high_close"] is True
    assert t["new_high_touch"] is True
    assert t["high52_actual"] == 101.0
    assert t["high52_date"] is not None
    assert t["days_since_high52"] == 0
    assert t["dist_high52_pct"] == round((100 / 101 - 1) * 100, 2)


def test_high52_metrics_below_high():
    closes = np.full(80, 90.0)
    closes[70] = 100.0
    closes[-1] = 95.0
    d = frame(closes)
    b = frame(np.linspace(90, 105, 80))
    t = m.technical_metrics(d, b)
    assert t["new_high_close"] is False
    assert t["high52_actual"] == 101.0
    assert t["dist_high52_pct"] == round((95 / 101 - 1) * 100, 2)
    assert t["days_since_high52"] == 9


def _sig_row(code, **kw):
    row = {
        "code": code, "name": code, "page": code + ".html",
        "price": 100.0, "change_pct": 1.0, "rs_score": 50,
        "volume_ratio": 1.0, "state": "yellow", "execution_score": 50.0,
        "high52_actual": 101.0, "high52_date": "2026-09-30",
        "dist_high52_pct": -1.0, "days_since_high52": 3,
        "new_high_close": False, "new_high_touch": False,
        "se_pos52": 90, "data_status": "valid",
    }
    row.update(kw)
    return row


def test_build_signals_groups_and_thresholds():
    rows = [
        _sig_row("AAA", new_high_close=True, new_high_touch=True,
                 dist_high52_pct=-0.5, change_pct=3.0),
        _sig_row("BBB", dist_high52_pct=-2.0),
        _sig_row("CCC", dist_high52_pct=-7.0),
        _sig_row("DDD", volume_ratio=2.5, dist_high52_pct=-30.0),
        _sig_row("EEE", volume_ratio=3.0, data_status="stale"),
    ]
    sig = m.build_signals(rows, "2026-10-01")
    assert sig["as_of"] == "2026-10-01"
    assert [x["code"] for x in sig["new_high"]] == ["AAA"]
    assert [x["code"] for x in sig["near_high"]] == ["BBB"]
    assert [x["code"] for x in sig["volume_surge"]] == ["DDD"]


def test_stockeasy_app_token_matches_js_reference():
    # Reference value produced by the site's JS bundle logic for a fixed
    # timestamp: bucket = floor(1790000000000 / 30000) = 59666666.
    import base64
    tok = m.stockeasy_app_token(now_ms=1790000000000)
    decoded = base64.b64decode(tok).decode()
    bucket, _, h36 = decoded.partition(".")
    assert bucket == "59666666"
    x = ((0x45D9F3B * 59666666) % (1 << 32)) ^ 0xDEADBEEF
    chars = "0123456789abcdefghijklmnopqrstuvwxyz"
    exp = ""
    v = x
    while v:
        v, r = divmod(v, 36)
        exp = chars[r] + exp
    assert h36 == exp


def test_parse_stockeasy_sector_flow_slims_payload():
    payload = {
        "success": True,
        "data": {
            "major_timeline": [
                {"date": "2026-09-30", "_total": 5, "반도체": 5},
                {"date": "2026-10-01", "_total": 13, "반도체": 8, "바이오": 2},
            ],
            "major_percentage": [
                {"date": "2026-09-30", "반도체": 100.0},
                {"date": "2026-10-01", "반도체": 61.5, "바이오": 15.4},
            ],
            "mid_timeline": [
                {"date": "2026-10-01", "_total": 13, "반도체장비": 4, "의료기기": 1},
            ],
            "major_totals": [
                {"name": "반도체", "weighted_count": 57.0, "distinct_count": 12},
            ],
            "date_range": {"start": "2026-08-31", "end": "2026-10-01"},
            "trading_days": 21,
            "sector_flow": {
                "inflow_sectors": [{"sector": "반도체", "change": 43.8}],
                "outflow_sectors": [{"sector": "금융", "change": -14.6}],
            },
        },
    }
    out = m.parse_stockeasy_sector_flow(payload)
    assert out["as_of"] == "2026-10-01"
    assert out["today_total"] == 13
    assert out["today_major"][0] == {"name": "반도체", "count": 8, "pct": 61.5}
    assert out["today_mid_top"][0] == {"name": "반도체장비", "count": 4}
    assert out["inflow"] == [{"sector": "반도체", "change": 43.8}]
    assert m.parse_stockeasy_sector_flow({"success": False}) is None
    assert m.parse_stockeasy_sector_flow(None) is None

# retrigger 2026-10-01: signals rollout regeneration
# retrigger 2026-10-02 09:06 KST: user-requested morning refresh at market open
