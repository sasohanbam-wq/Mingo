import json
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import exchange_calendars as xcals
import pandas as pd
import yfinance as yf

ROOT = os.path.dirname(os.path.dirname(__file__))
CFG = os.path.join(ROOT, "data", "stocks.json")
OUT = os.path.join(ROOT, "data", "live_scores.json")
KST = ZoneInfo("Asia/Seoul")
CAL = xcals.get_calendar("XKRX")
SOURCE = "Yahoo Finance daily OHLCV via yfinance (completed regular session only)"


def clamp(x, lo=0.0, hi=100.0):
    return max(lo, min(hi, x))


def wilder_rsi(series, period=14):
    s = pd.Series(series, dtype=float).dropna()
    if len(s) < period + 1:
        return None
    delta = s.diff()
    gain = delta.clip(lower=0)
    loss = (-delta.clip(upper=0))
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    g = avg_gain.iloc[-1]
    l = avg_loss.iloc[-1]
    if pd.isna(g) or pd.isna(l):
        return None
    if g == 0 and l == 0:
        return 50.0
    if l == 0:
        return 100.0
    if g == 0:
        return 0.0
    rs = g / l
    return float(100 - (100 / (1 + rs)))


def market_context(now=None):
    now = now or datetime.now(KST)
    if now.tzinfo is None:
        now = now.replace(tzinfo=KST)
    else:
        now = now.astimezone(KST)
    today = pd.Timestamp(now.date())

    if CAL.is_session(today):
        open_dt = CAL.session_open(today).tz_convert("Asia/Seoul").to_pydatetime()
        close_dt = CAL.session_close(today).tz_convert("Asia/Seoul").to_pydatetime()
        if now < open_dt:
            state = "preopen"
            expected = CAL.previous_session(today)
        elif now <= close_dt + timedelta(minutes=10):
            state = "open" if now <= close_dt else "closing_grace"
            expected = CAL.previous_session(today)
        else:
            state = "closed"
            expected = today
    else:
        state = "holiday_or_weekend"
        expected = CAL.date_to_session(today, direction="previous")

    return {
        "market_state": state,
        "expected_completed_session": pd.Timestamp(expected).strftime("%Y-%m-%d"),
        "calculated_at": now.isoformat(timespec="seconds"),
    }


def _session_dates(index):
    idx = pd.DatetimeIndex(index)
    if idx.tz is not None:
        idx = idx.tz_convert("Asia/Seoul")
    return [pd.Timestamp(x).date().isoformat() for x in idx]


def prepare_history(df):
    if df is None or df.empty:
        raise RuntimeError("empty history")
    out = df.copy().sort_index()
    out = out.dropna(subset=["Close", "High", "Low"])
    out["_session_date"] = _session_dates(out.index)
    out = out.drop_duplicates(subset=["_session_date"], keep="last")
    return out


def load_history(symbol):
    df = yf.Ticker(symbol).history(period="2y", interval="1d", auto_adjust=False)
    return prepare_history(df)


def select_completed(df, expected_session):
    eligible = df[df["_session_date"] <= expected_session].copy()
    if eligible.empty:
        raise RuntimeError("no completed session data")
    latest = eligible["_session_date"].iloc[-1]
    return eligible, latest, (latest == expected_session)


def trailing_return(series, n):
    s = pd.Series(series, dtype=float).dropna()
    if len(s) <= n:
        return None
    base = float(s.iloc[-n - 1])
    if base == 0:
        return None
    return float(s.iloc[-1] / base - 1)


def excess_returns(stock_df, bench_df):
    a = stock_df.set_index("_session_date")["Close"].astype(float)
    b = bench_df.set_index("_session_date")["Close"].astype(float)
    j = pd.concat([a.rename("s"), b.rename("b")], axis=1, join="inner").dropna()
    out = {}
    for n in (20, 60):
        sr = trailing_return(j["s"], n)
        br = trailing_return(j["b"], n)
        out[n] = None if sr is None or br is None else (sr - br) * 100
    return out


def _volume_ratio_at(df, i):
    if "Volume" not in df.columns or i <= 0:
        return None
    start = max(0, i - 20)
    prior = df["Volume"].astype(float).iloc[start:i]
    mean = float(prior.mean()) if len(prior) else 0.0
    if mean <= 0:
        return None
    return float(df["Volume"].astype(float).iloc[i] / mean)


def breakout_confirmation(df, trigger):
    if not trigger or len(df) < 2:
        return {"passed": False, "volume_ratio": None, "cross_date": None}
    close = df["Close"].astype(float)
    for i in range(max(1, len(df) - 3), len(df)):
        if float(close.iloc[i - 1]) < trigger <= float(close.iloc[i]):
            vr = _volume_ratio_at(df, i)
            current = float(close.iloc[-1])
            passed = (vr is not None and vr >= 1.2 and current >= trigger and current <= trigger * 1.08)
            return {
                "passed": passed,
                "volume_ratio": None if vr is None else round(vr, 2),
                "cross_date": df["_session_date"].iloc[i],
            }
    return {"passed": False, "volume_ratio": None, "cross_date": None}


def technical_metrics(df, bench_df):
    c = df["Close"].astype(float)
    h = df["High"].astype(float)
    l = df["Low"].astype(float)
    v = df["Volume"].astype(float) if "Volume" in df else pd.Series(index=df.index, dtype=float)

    p = float(c.iloc[-1])
    prev = float(c.iloc[-2]) if len(c) > 1 else p
    ma20 = float(c.rolling(20).mean().iloc[-1]) if len(c) >= 20 else None
    ma50 = float(c.rolling(50).mean().iloc[-1]) if len(c) >= 50 else None
    ma200 = float(c.rolling(200).mean().iloc[-1]) if len(c) >= 200 else None
    high20 = float(h.tail(20).max()) if len(h) >= 20 else float(h.max())
    low20 = float(l.tail(20).min()) if len(l) >= 20 else float(l.min())
    rsi = wilder_rsi(c)
    ex = excess_returns(df, bench_df)

    prior_vol = v.iloc[-21:-1] if len(v) >= 21 else v.iloc[:-1]
    vol_mean = float(prior_vol.mean()) if len(prior_vol) and prior_vol.mean() > 0 else 0.0
    volume_ratio = float(v.iloc[-1] / vol_mean) if vol_mean > 0 else None

    trend = 50.0
    if ma20 is not None:
        trend += 15 if p >= ma20 else -18
    if ma20 is not None and ma50 is not None:
        trend += 10 if ma20 >= ma50 else -10
    if ma200 is not None:
        trend += 8 if p >= ma200 else -8
        if ma50 is not None:
            trend += 7 if ma50 >= ma200 else -7
    dist_high = (p / high20 - 1) * 100 if high20 else 0
    trend += 6 if dist_high >= -5 else 2 if dist_high >= -10 else -4
    trend = clamp(trend)

    rel20 = ex[20]
    rel60 = ex[60]
    rel_score = 50.0
    if rel20 is not None:
        rel_score += rel20 * 2.0
    if rel60 is not None:
        rel_score += rel60 * 0.7
    rel_score = clamp(rel_score)

    if rsi is None:
        momentum_score = 50.0
    elif 48 <= rsi <= 68:
        momentum_score = 75.0
    elif 42 <= rsi < 48 or 68 < rsi <= 75:
        momentum_score = 60.0
    elif 35 <= rsi < 42 or 75 < rsi <= 82:
        momentum_score = 42.0
    else:
        momentum_score = 25.0

    if volume_ratio is None:
        volume_score = 50.0
    elif 0.7 <= volume_ratio <= 2.5:
        volume_score = clamp(50 + (volume_ratio - 1) * 18)
    elif volume_ratio > 2.5:
        volume_score = 65.0
    else:
        volume_score = 40.0

    technical_score = round(
        0.45 * trend + 0.30 * rel_score + 0.15 * momentum_score + 0.10 * volume_score,
        1,
    )
    extension = None if ma20 is None else (p / ma20 - 1) * 100

    return {
        "price": round(p, 2),
        "change_pct": round((p / prev - 1) * 100, 2) if prev else 0.0,
        "ma20": None if ma20 is None else round(ma20, 2),
        "ma50": None if ma50 is None else round(ma50, 2),
        "ma200": None if ma200 is None else round(ma200, 2),
        "high20_actual": round(high20, 2),
        "low20_actual": round(low20, 2),
        "rsi14_wilder": None if rsi is None else round(rsi, 1),
        "excess_return_20d_pct": None if rel20 is None else round(rel20, 1),
        "excess_return_60d_pct": None if rel60 is None else round(rel60, 1),
        "volume_ratio": None if volume_ratio is None else round(volume_ratio, 2),
        "extension_ma20_pct": None if extension is None else round(extension, 1),
        "technical_score": technical_score,
        "trend_score": round(trend, 1),
        "relative_return_score": round(rel_score, 1),
    }


def setup_gate(df, metrics, setup):
    p = metrics["price"]
    ma20 = metrics["ma20"]
    ma50 = metrics["ma50"]
    rsi = metrics["rsi14_wilder"]
    ext = metrics["extension_ma20_pct"]

    buy_lo, buy_hi = setup["buy"]
    trigger = setup.get("trigger")
    stop = setup.get("stop")
    stype = setup["type"]

    latest = df.iloc[-1]
    prev_close = float(df["Close"].astype(float).iloc[-2]) if len(df) > 1 else p
    reversal = (float(latest["Close"]) >= float(latest["Open"])) or (p >= prev_close)
    low3 = float(df["Low"].astype(float).tail(3).min())
    in_zone = buy_lo <= p <= buy_hi
    touched_zone = low3 <= buy_hi and p >= buy_lo
    above_ma20 = ma20 is not None and p >= ma20
    trend_valid = (
        ma20 is not None
        and ma50 is not None
        and p >= ma20
        and ma20 >= ma50
    )
    breakout = breakout_confirmation(df, trigger)

    invalidated = stop is not None and p < stop
    overheated = (
        (rsi is not None and rsi > 84)
        or (ext is not None and ext > 20)
    )

    pullback_pass = (
        stype == "trend"
        and trend_valid
        and in_zone
        and touched_zone
        and above_ma20
        and reversal
    )
    breakout_pass = stype in {"trend", "event"} and breakout["passed"]

    recovery_pass = (
        stype == "recovery"
        and trigger is not None
        and p >= trigger
        and above_ma20
        and reversal
        and (metrics["volume_ratio"] is None or metrics["volume_ratio"] >= 0.8)
    )

    value_swing_pass = (
        stype == "value_swing"
        and in_zone
        and touched_zone
        and reversal
        and ma20 is not None
        and p >= ma20 * 0.97
    )

    passed = pullback_pass or breakout_pass or recovery_pass or value_swing_pass
    if invalidated or overheated:
        passed = False

    if invalidated:
        reason = "무효화 가격 이탈"
    elif overheated:
        reason = "과열/이격 과다 — 신규 추격 금지"
    elif pullback_pass:
        reason = "눌림구간 + 상승추세 + 지지/반전 확인"
    elif breakout_pass:
        reason = "실제 돌파가격 종가 돌파 + 거래량 1.2× 이상"
    elif recovery_pass:
        reason = "회복 트리거 + MA20 회복 + 반전 확인"
    elif value_swing_pass:
        reason = "가치스윙 구간 + 반전 확인 (추세매수와 별도)"
    elif stype == "trend" and not above_ma20:
        reason = "추세형이지만 MA20 아래 — 매수 Gate 실패"
    elif stype == "trend" and not in_zone and (trigger is None or p < trigger):
        reason = "매수구간 밖이며 돌파트리거 미통과"
    elif stype == "recovery" and trigger is not None and p < trigger:
        reason = "회복 트리거 미통과"
    elif stype == "value_swing":
        reason = "가치스윙 반전조건 미충족"
    elif stype == "event":
        reason = "이벤트형 — 거래량 동반 돌파 전 대기"
    else:
        reason = "셋업 조건 미충족"

    return {
        "setup_type": stype,
        "buy_zone": [buy_lo, buy_hi],
        "trigger": trigger,
        "invalidation": stop,
        "in_buy_zone": in_zone,
        "above_ma20": above_ma20,
        "trend_valid": trend_valid,
        "support_or_reversal_confirmed": bool(touched_zone and reversal),
        "breakout_confirmed": breakout["passed"],
        "breakout_volume_ratio": breakout["volume_ratio"],
        "breakout_cross_date": breakout["cross_date"],
        "setup_pass": bool(passed),
        "invalidated": bool(invalidated),
        "overheated": bool(overheated),
        "setup_reason": reason,
    }


def classify(data_valid, gate, evidence_status, technical_score):
    if not data_valid:
        return "gray", "⚪ 데이터 확인 필요"
    if gate["invalidated"] or gate["overheated"]:
        return "red", "🔴 보류"
    if gate["setup_pass"]:
        if evidence_status == "verified":
            if gate["setup_type"] == "value_swing":
                return "blue", "🟦 가치스윙 조건충족"
            return "green", "🟢 매수 Gate 통과"
        if gate["setup_type"] == "value_swing":
            return "blue", "🟦 가치스윙 조건충족·근거 검증중"
        return "blue", "🔵 셋업 통과·근거 검증중"
    if technical_score < 30:
        return "red", "🔴 기술 약세"
    return "yellow", "🟡 조건부/대기"


def process_stock(stock, bench_df, context):
    symbol = stock["code"] + (".KS" if stock["exchange"] == "KS" else ".KQ")
    raw = load_history(symbol)
    hist, quote_as_of, quote_ok = select_completed(raw, context["expected_completed_session"])
    bench_hist, bench_as_of, bench_ok = select_completed(
        bench_df, context["expected_completed_session"]
    )
    aligned = quote_ok and bench_ok and quote_as_of == bench_as_of

    metrics = technical_metrics(hist, bench_hist)
    gate = setup_gate(hist, metrics, stock["setup"])
    evidence_status = stock.get("evidence", {}).get("status", "legacy_unverified")

    data_valid = bool(aligned)
    state, label = classify(
        data_valid, gate, evidence_status, metrics["technical_score"]
    )

    legacy = stock.get("legacy_scores", {})
    research_score = None
    research_score_status = "N/A — F/E/V evidence re-verification required"
    execution_score = round(
        clamp(metrics["technical_score"] + (10 if gate["setup_pass"] else -10)), 1
    )

    return {
        "name": stock["name"],
        "code": stock["code"],
        "exchange": stock["exchange"],
        "page": stock["page"],
        "theme": stock["theme"],
        "source": SOURCE,
        "quote_as_of": quote_as_of,
        "benchmark_as_of": bench_as_of,
        "expected_completed_session": context["expected_completed_session"],
        "session": context["market_state"],
        "calculated_at": context["calculated_at"],
        "data_status": "valid" if data_valid else "stale",
        "quote_valid": data_valid,
        "evidence_status": evidence_status,
        "evidence_notes": stock.get("evidence", {}).get("notes", []),
        "evidence_sources": stock.get("evidence", {}).get("sources", []),
        "legacy_F": legacy.get("F"),
        "legacy_E": legacy.get("E"),
        "legacy_V": legacy.get("V"),
        "legacy_PR": legacy.get("PR"),
        "research_score": research_score,
        "research_score_status": research_score_status,
        "execution_score": execution_score,
        **metrics,
        **gate,
        "state": state,
        "label": label,
    }


def main(now=None):
    with open(CFG, encoding="utf-8") as f:
        cfg = json.load(f)

    context = market_context(now)
    bench = {}
    errors = []
    old = {}
    if os.path.exists(OUT):
        try:
            with open(OUT, encoding="utf-8") as f:
                old = {x["code"]: x for x in json.load(f).get("stocks", [])}
        except Exception:
            old = {}

    for ex, symbol in (("KS", "^KS11"), ("KQ", "^KQ11")):
        try:
            bench[ex] = load_history(symbol)
        except Exception as exc:
            bench[ex] = None
            errors.append(f"benchmark {ex}: {exc}")

    rows = []
    for stock in cfg["stocks"]:
        try:
            b = bench.get(stock["exchange"])
            if b is None:
                raise RuntimeError("benchmark unavailable")
            row = process_stock(stock, b, context)
        except Exception as exc:
            errors.append(f'{stock["code"]}: {exc}')
            prev = old.get(stock["code"], {})
            row = {
                **stock,
                **{k: prev.get(k) for k in (
                    "price", "change_pct", "ma20", "ma50", "ma200",
                    "high20_actual", "low20_actual", "rsi14_wilder",
                    "technical_score", "execution_score", "quote_as_of"
                )},
                "source": SOURCE,
                "benchmark_as_of": None,
                "expected_completed_session": context["expected_completed_session"],
                "session": context["market_state"],
                "calculated_at": context["calculated_at"],
                "data_status": "error",
                "quote_valid": False,
                "research_score": None,
                "research_score_status": "N/A — data/evidence unavailable",
                "setup_pass": False,
                "state": "gray",
                "label": "⚪ 평가 보류",
                "setup_reason": f"data error: {exc}",
                "error": str(exc),
            }
        rows.append(row)

    priority = {"green": 0, "blue": 1, "yellow": 2, "red": 3, "gray": 4}
    rows.sort(
        key=lambda x: (
            priority.get(x.get("state"), 9),
            -(x.get("execution_score") or -1),
        )
    )

    out = {
        "version": 2,
        "model": "MINGO v2 gate-first",
        "calculated_at": context["calculated_at"],
        "calculated_at_label": datetime.fromisoformat(
            context["calculated_at"]
        ).strftime("%Y-%m-%d %H:%M KST"),
        "market_state": context["market_state"],
        "expected_completed_session": context["expected_completed_session"],
        "source": SOURCE,
        "notes": [
            "completed regular-session daily data only",
            "stale/error/fallback can never produce green",
            "legacy F/E/V are audit-only until structured evidence is re-verified",
            "price decline alone does not increase valuation score",
        ],
        "errors": errors,
        "stocks": rows,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"updated {len(rows)} stocks; errors={len(errors)}")


if __name__ == "__main__":
    main()
