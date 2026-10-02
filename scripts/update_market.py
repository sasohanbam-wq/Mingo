import json
import os
import re
import argparse
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import exchange_calendars as xcals
import pandas as pd
import yfinance as yf

ROOT = os.path.dirname(os.path.dirname(__file__))
CFG = os.path.join(ROOT, "data", "stocks.json")
OUT = os.path.join(ROOT, "data", "live_scores.json")
EVIDENCE = os.path.join(ROOT, "data", "research_evidence.json")
KST = ZoneInfo("Asia/Seoul")
CAL = xcals.get_calendar("XKRX")
SOURCE = "Yahoo Finance daily OHLCV via yfinance (completed regular session only)"
STOCKEASY_RS_URL = "https://stockeasy.intellio.kr/stock-analysis/stock-info/{code}"
STOCKEASY_RS_SOURCE = "StockEasy (stockeasy.intellio.kr) 종합 RS"


def parse_stockeasy_rs(html):
    """Extract the 종합 RS score and its basis close from a StockEasy summary page."""
    if not html:
        return None
    m = re.search(r"종합 RS</dt><dd[^>]*>(\d+)</dd>", html)
    if not m:
        return None
    basis = re.search(r"(\d{2}\.\d{2}\.\d{2}) 종가 ([\d,]+)원", html)
    return {
        "score": int(m.group(1)),
        "basis_date": basis.group(1) if basis else None,
        "basis_price": int(basis.group(2).replace(",", "")) if basis else None,
    }


def fetch_stockeasy_page(code, timeout=10):
    """Fetch a StockEasy summary page once; returns HTML text or None (never raises)."""
    try:
        req = urllib.request.Request(
            STOCKEASY_RS_URL.format(code=code),
            headers={"User-Agent": "Mozilla/5.0 (Mingo dashboard RS sync)"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", "ignore")
    except Exception:
        return None


def fetch_stockeasy_rs(code, timeout=10):
    """Best-effort RS fetch; returns None on any failure (never raises)."""
    html = fetch_stockeasy_page(code, timeout=timeout)
    return parse_stockeasy_rs(html) if html else None


def _se_int(text):
    if text is None:
        return None
    text = text.replace(",", "").replace("+", "").strip()
    if text in ("", "-", "—"):
        return None
    try:
        return int(text)
    except ValueError:
        try:
            return int(float(text))
        except ValueError:
            return None


def parse_stockeasy_summary(html):
    """Extract display-only extras from a StockEasy summary page.

    Pulls the 주요 지표 block (market cap, 52w high/low, position within the
    52w range), the last four reported quarters, the latest disclosures and
    the sector tags. Everything here is context/display only, mirroring the
    RS treatment: it never feeds execution or research scores.
    """
    if not html:
        return None
    out = {}
    metrics = dict(
        re.findall(
            r"<dt[^>]*>([^<]+)</dt><dd[^>]*>([^<]+)</dd>", html
        )
    )
    if metrics.get("시가총액"):
        out["market_cap"] = metrics["시가총액"].strip()
    hi = _se_int((metrics.get("52주 고가") or "").replace("원", ""))
    lo = _se_int((metrics.get("52주 저가") or "").replace("원", ""))
    if hi is not None:
        out["high52"] = hi
    if lo is not None:
        out["low52"] = lo
    pos = _se_int((metrics.get("52주 구간 내 위치") or "").replace("%", ""))
    if pos is not None:
        out["pos52"] = pos
    qm = re.search(
        r'aria-labelledby="kr-summary-quarterly".*?<tbody>(.*?)</tbody>',
        html,
        re.S,
    )
    if qm:
        quarters = []
        for row_html in re.findall(r"<tr[^>]*>(.*?)</tr>", qm.group(1), re.S):
            cells = re.findall(r"<t[hd][^>]*>([^<]*)</t[hd]>", row_html)
            if len(cells) >= 4:
                quarters.append(
                    {
                        "q": cells[0].strip(),
                        "revenue": _se_int(cells[1]),
                        "op": _se_int(cells[2]),
                        "net": _se_int(cells[3]),
                    }
                )
        if quarters:
            out["quarterly"] = quarters[:4]
    dm = re.search(
        r'aria-labelledby="kr-summary-disclosures".*?</section>', html, re.S
    )
    if dm:
        discs = []
        for title, date in re.findall(
            r'<p class="text-sm text-fg">([^<]+)</p><time[^>]*dateTime="([\d-]+)"',
            dm.group(0),
        ):
            discs.append({"title": title.strip(), "date": date})
        if discs:
            out["disclosures"] = discs[:3]
    sm = re.search(
        r'aria-labelledby="kr-summary-sector".*?</section>', html, re.S
    )
    if sm:
        tags = [
            t.strip()
            for t in re.findall(r"<li[^>]*>([^<]+)</li>", sm.group(0))
            if t.strip()
        ]
        if tags:
            out["sectors"] = tags
    return out or None


STOCKEASY_MAIN_URL = "https://stockeasy.intellio.kr/"
STOCKEASY_FLOW_SOURCE = "StockEasy (stockeasy.intellio.kr) 메인 투자자별 순매수"


def parse_stockeasy_market(html):
    """Investor net buying (억원) from the StockEasy main page header block."""
    if not html:
        return None
    flows = {}
    for name, key in (("외국인", "foreign"), ("기관", "institution"), ("개인", "individual")):
        m = re.search(
            r">" + name + r"</span>(?:(?!</span>).){0,2000}?>([+-]?[\d,]+)<!-- -->억</span>",
            html,
            re.S,
        )
        if m:
            flows[key] = _se_int(m.group(1))
    return flows or None


def fetch_stockeasy_market(timeout=10):
    """Best-effort market flow fetch; returns None on any failure (never raises)."""
    try:
        req = urllib.request.Request(
            STOCKEASY_MAIN_URL,
            headers={"User-Agent": "Mozilla/5.0 (Mingo dashboard RS sync)"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            html = resp.read().decode("utf-8", "ignore")
        return parse_stockeasy_market(html)
    except Exception:
        return None


STOCKEASY_SECTOR_FLOW_URL = (
    "https://stockeasy.intellio.kr/stockdata/api/v1/high52/sector-flow"
)
STOCKEASY_SECTOR_FLOW_SOURCE = (
    "StockEasy (stockeasy.intellio.kr) 52주 신고가 섹터 흐름"
)


def stockeasy_app_token(now_ms=None):
    """Time-bucketed app token the StockEasy web client sends as X-App-Token
    (recovered from the site's public JS bundle): base64 of
    "<bucket>.<hash36>" where bucket = floor(now_ms / 30000) and the hash is
    ((0x45d9f3b * bucket) ^ 0xdeadbeef) as an unsigned 32-bit value in base 36.
    Used only for the public sector-flow endpoint; the per-stock dashboard
    endpoint additionally requires a login session and is not collected.
    """
    import base64
    import time

    if now_ms is None:
        now_ms = int(time.time() * 1000)
    bucket = now_ms // 30000
    x = ((0x45D9F3B * bucket) % (1 << 32)) ^ 0xDEADBEEF
    chars = "0123456789abcdefghijklmnopqrstuvwxyz"
    if x == 0:
        h36 = "0"
    else:
        h36 = ""
        while x:
            x, r = divmod(x, 36)
            h36 = chars[r] + h36
    return base64.b64encode(f"{bucket}.{h36}".encode()).decode()


def parse_stockeasy_sector_flow(payload):
    """Slim market-wide 52-week new-high sector context from the StockEasy
    sector-flow payload. Display/context only."""
    if not payload or not payload.get("success"):
        return None
    data = payload.get("data") or {}
    timeline = data.get("major_timeline") or []
    if not timeline:
        return None
    last = timeline[-1]
    pct = (data.get("major_percentage") or [{}])[-1]
    today_major = []
    for name, count in last.items():
        if name in ("date", "_total"):
            continue
        today_major.append(
            {"name": name, "count": count, "pct": pct.get(name)}
        )
    today_major.sort(key=lambda x: -x["count"])
    mid_last = (data.get("mid_timeline") or [{}])[-1]
    today_mid = [
        {"name": k, "count": v}
        for k, v in mid_last.items()
        if k not in ("date", "_total")
    ]
    today_mid.sort(key=lambda x: -x["count"])
    totals = [
        {
            "name": t["name"],
            "weighted": t.get("weighted_count"),
            "distinct": t.get("distinct_count"),
        }
        for t in (data.get("major_totals") or [])[:5]
    ]
    flow = data.get("sector_flow") or {}
    slim_flow = lambda items: [
        {"sector": i["sector"], "change": i.get("change")}
        for i in (items or [])[:3]
    ]
    return {
        "as_of": last.get("date"),
        "today_total": last.get("_total"),
        "today_major": today_major,
        "today_mid_top": today_mid[:5],
        "period_start": (data.get("date_range") or {}).get("start"),
        "period_end": (data.get("date_range") or {}).get("end"),
        "trading_days": data.get("trading_days"),
        "period_major_top": totals,
        "inflow": slim_flow(flow.get("inflow_sectors")),
        "outflow": slim_flow(flow.get("outflow_sectors")),
    }


def fetch_stockeasy_sector_flow(timeout=10):
    """Best-effort sector-flow fetch; returns None on any failure."""
    try:
        req = urllib.request.Request(
            STOCKEASY_SECTOR_FLOW_URL,
            headers={
                "User-Agent": "Mozilla/5.0 (Mingo dashboard sync)",
                "X-App-Token": stockeasy_app_token(),
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8", "ignore"))
        return parse_stockeasy_sector_flow(payload)
    except Exception:
        return None


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


def load_current_price(symbol):
    bars = yf.Ticker(symbol).history(period="1d", interval="1m", auto_adjust=False)
    if bars is None or bars.empty or bars["Close"].dropna().empty:
        raise RuntimeError("no current minute price")
    series = bars["Close"].dropna()
    timestamp = pd.Timestamp(series.index[-1])
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize(KST)
    else:
        timestamp = timestamp.tz_convert(KST)
    return float(series.iloc[-1]), timestamp.isoformat()


def select_completed(df, expected_session):
    eligible = df[df["_session_date"] <= expected_session].copy()
    if eligible.empty:
        raise RuntimeError("no completed session data")
    latest = eligible["_session_date"].iloc[-1]
    return eligible, latest, (latest == expected_session)


def chart_series(hist, n=60):
    """Compact completed-session OHLCV tail for the stock detail page chart.

    Muse 2026-10-01: detail pages draw a real candle chart (with MA20/MA50
    overlays) from this field. Additive only; whole-won rounding keeps the
    payload small. MA values are computed on the full history, then aligned
    to the displayed tail.
    """
    if hist is None or len(hist) == 0:
        return []
    closes = pd.Series(hist["Close"].values, dtype=float)
    ma20 = closes.rolling(20).mean()
    ma50 = closes.rolling(50).mean()
    tail = hist.tail(n)
    base = len(hist) - len(tail)

    def _v(x):
        return None if x is None or pd.isna(x) else int(round(float(x)))

    out = []
    for j, (_, r) in enumerate(tail.iterrows()):
        i = base + j
        out.append({
            "d": str(r["_session_date"])[5:],
            "o": _v(r["Open"]), "h": _v(r["High"]), "l": _v(r["Low"]),
            "c": _v(r["Close"]), "v": _v(r["Volume"]),
            "ma20": _v(ma20.iloc[i]), "ma50": _v(ma50.iloc[i]),
        })
    return out


def build_index_series(bench, n=60, completed_session=None):
    """Compact close series for the two benchmark indices (board sparklines).

    bench maps exchange code ("KS"/"KQ") to a prepared history DataFrame.
    When completed_session ("YYYY-MM-DD") is given, rows after it (e.g. a
    partial intraday bar) are excluded so the series matches the regime.
    Returns {"KOSPI": {...}, "KOSDAQ": {...}}; missing data yields {}.
    """
    out = {}
    for ex, label in (("KS", "KOSPI"), ("KQ", "KOSDAQ")):
        df = (bench or {}).get(ex)
        if df is None or len(df) == 0 or "Close" not in df.columns:
            continue
        if completed_session is not None and "_session_date" in df.columns:
            df = df[df["_session_date"] <= completed_session]
        closes = pd.Series(df["Close"].values, dtype=float).dropna()
        if len(closes) < 2:
            continue
        tail = df.tail(n)
        series = [
            {"d": str(r["_session_date"])[5:], "c": round(float(r["Close"]), 2)}
            for _, r in tail.iterrows()
            if not pd.isna(r["Close"])
        ]
        last = float(closes.iloc[-1])
        prev = float(closes.iloc[-2])
        out[label] = {
            "close": round(last, 2),
            "change_pct": None if prev == 0 else round((last / prev - 1) * 100, 2),
            "series": series,
        }
    return out


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


def technical_metrics(df, bench_df=None, relative_valid=True):
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
    ex = excess_returns(df, bench_df) if (relative_valid and bench_df is not None) else {20: None, 60: None}

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

    parts = [(trend, 0.45), (momentum_score, 0.15), (volume_score, 0.10)]
    relative_available = rel20 is not None or rel60 is not None
    if relative_available:
        parts.append((rel_score, 0.30))
    weight_sum = sum(w for _, w in parts)
    technical_score = round(sum(v * w for v, w in parts) / weight_sum, 1)
    extension = None if ma20 is None else (p / ma20 - 1) * 100

    # 52-week high context from completed-session history (display only —
    # feeds the signals tab, never execution or research scores).
    win = df.tail(252)
    if len(win):
        hi_s = win["High"].astype(float)
        high52 = float(hi_s.max())
        hi_pos = int(hi_s.values.argmax())
        high52_date = (
            str(win["_session_date"].iloc[hi_pos]) if "_session_date" in win else None
        )
        days_since_high52 = int(len(win) - 1 - hi_pos)
        close52 = float(win["Close"].astype(float).max())
    else:
        high52 = close52 = None
        high52_date = None
        days_since_high52 = None
    new_high_close = bool(close52 is not None and p >= close52)
    new_high_touch = bool(high52 is not None and float(h.iloc[-1]) >= high52)
    dist_high52 = None if not high52 else round((p / high52 - 1) * 100, 2)

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
        "high52_actual": None if high52 is None else round(high52, 2),
        "high52_date": high52_date,
        "new_high_close": new_high_close,
        "new_high_touch": new_high_touch,
        "dist_high52_pct": dist_high52,
        "days_since_high52": days_since_high52,
        "extension_ma20_pct": None if extension is None else round(extension, 1),
        "technical_score": technical_score,
        "trend_score": round(trend, 1),
        "relative_return_score": round(rel_score, 1) if relative_available else None,
        "relative_return_status": "valid" if relative_available else "N/A — benchmark session mismatch/unavailable",
    }


REGIME_ADJUSTMENT = {"attack": 10.0, "neutral": 0.0, "defense": -10.0, "unknown": 0.0}
REGIME_LABELS = {"attack": "공격", "neutral": "중립", "defense": "방어", "unknown": "판정 불가"}


def market_regime(bench, expected_session):
    """Market regime from the KOSPI/KOSDAQ benchmark histories (completed
    sessions only). Per index: +1 close above MA20, +1 above MA60, +1 positive
    20-session return. attack: average >= 2.5, defense: average <= 1.0, else
    neutral. The regime only modulates execution — the relative-overheat
    yardstick, a bounded execution-score adjustment, and defense-mode setup
    blocks. It never lifts an invalidation and never creates research scores.
    Unknown (benchmark unavailable) behaves exactly like the pre-regime code.
    """
    indices = {}
    points = []
    extensions = []
    as_of = None
    for ex, label in (("KS", "KOSPI"), ("KQ", "KOSDAQ")):
        df = bench.get(ex) if bench else None
        if df is None:
            continue
        try:
            hist, sess, _ = select_completed(df, expected_session)
        except Exception:
            continue
        closes = hist["Close"].astype(float)
        if len(closes) < 61:
            continue
        last = float(closes.iloc[-1])
        ma20 = float(closes.tail(20).mean())
        ma60 = float(closes.tail(60).mean())
        ret20 = trailing_return(closes, 20)
        pts = int(last > ma20) + int(last > ma60) + int(ret20 is not None and ret20 > 0)
        ext = (last / ma20 - 1) * 100 if ma20 else 0.0
        indices[label] = {
            "close": round(last, 2),
            "ma20": round(ma20, 2),
            "ma60": round(ma60, 2),
            "return_20d_pct": None if ret20 is None else round(ret20 * 100, 2),
            "extension_ma20_pct": round(ext, 1),
            "points": pts,
            "as_of": sess,
        }
        points.append(pts)
        extensions.append(ext)
        as_of = sess
    if not points:
        return {
            "level": "unknown",
            "label": REGIME_LABELS["unknown"],
            "points_avg": None,
            "index_extension_ma20_pct": None,
            "execution_adjustment": 0.0,
            "as_of": None,
            "indices": {},
        }
    avg = sum(points) / len(points)
    level = "attack" if avg >= 2.5 else "defense" if avg <= 1.0 else "neutral"
    return {
        "level": level,
        "label": REGIME_LABELS[level],
        "points_avg": round(avg, 2),
        "index_extension_ma20_pct": round(sum(extensions) / len(extensions), 1),
        "execution_adjustment": REGIME_ADJUSTMENT[level],
        "as_of": as_of,
        "indices": indices,
    }


def setup_gate(df, metrics, setup, regime=None):
    p = metrics["price"]
    ma20 = metrics["ma20"]
    ma50 = metrics["ma50"]
    rsi = metrics["rsi14_wilder"]
    ext = metrics["extension_ma20_pct"]

    buy_lo, buy_hi = setup["buy"]
    trigger = setup.get("trigger")
    stop = setup.get("stop")
    stype = setup["type"]

    regime_level = (regime or {}).get("level", "unknown")
    idx_ext = (regime or {}).get("index_extension_ma20_pct")
    idx_ext = 0.0 if idx_ext is None else float(idx_ext)

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
    # Overheat extension is judged relative to the market: in a broad melt-up
    # the index itself sits far above its MA20, so only the stock's *excess*
    # extension over the index counts as idiosyncratic froth. With no regime
    # data idx_ext is 0 and this reduces to the old absolute rule.
    extension_overheated = (
        ext is not None and ext > 20 and (ext - idx_ext) > 10
    )
    overheated = (
        (rsi is not None and rsi > 84)
        or extension_overheated
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

    # Defense regime: breakouts fail too often to chase, and pullbacks are
    # only trusted in the lower half of the buy zone. Invalidation and
    # overheat blocks above are regime-independent and stay untouched.
    regime_blocked = None
    if regime_level == "defense":
        if breakout_pass:
            breakout_pass = False
            regime_blocked = "breakout"
        if pullback_pass and p > (buy_lo + buy_hi) / 2:
            pullback_pass = False
            regime_blocked = regime_blocked or "pullback_upper_half"

    passed = pullback_pass or breakout_pass or recovery_pass or value_swing_pass
    if invalidated or overheated:
        passed = False

    if invalidated:
        reason = "무효화 가격 이탈"
    elif overheated:
        reason = "과열/이격 과다 — 신규 추격 금지"
    elif regime_blocked == "breakout":
        reason = "방어 국면 — 돌파 셋업 비활성화"
    elif regime_blocked == "pullback_upper_half":
        reason = "방어 국면 — 눌림은 매수구간 하단에서만 허용"
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
        "regime_level": regime_level,
        "market_extension_ma20_pct": None if regime is None else regime.get("index_extension_ma20_pct"),
        "excess_extension_ma20_pct": None if ext is None else round(ext - idx_ext, 1),
        "regime_blocked": regime_blocked,
        "setup_reason": reason,
    }


def compute_research_score(research):
    if not research:
        return None, "N/A — no structured research evidence"
    factors = [research.get("F", {}), research.get("E", {}), research.get("V", {})]
    if any(x.get("status") != "verified" or x.get("score") is None for x in factors):
        return None, "N/A — one or more F/E/V factors are not verified"
    score = round(
        0.375 * float(research["F"]["score"])
        + 0.375 * float(research["E"]["score"])
        + 0.25 * float(research["V"]["score"]),
        1,
    )
    return score, "verified"


def classify(data_valid, gate, evidence_status, research_score, technical_score):
    if not data_valid:
        return "gray", "⚪ 데이터 확인 필요"
    if gate["invalidated"] or gate["overheated"]:
        return "red", "🔴 보류"
    if gate["setup_pass"]:
        if evidence_status == "verified" and research_score is not None and research_score >= 70:
            if gate["setup_type"] == "value_swing":
                return "blue", "🟦 가치스윙 조건충족 · 연구점수 통과"
            return "green", "🟢 데이터·셋업·연구점수 통과"
        if evidence_status == "verified" and research_score is not None:
            return "blue", f"🔵 셋업 통과 · 연구점수 {research_score}(<70)"
        if gate["setup_type"] == "value_swing":
            return "blue", "🟦 가치스윙 조건충족 · F/E/V 검증중"
        return "blue", "🔵 셋업 통과 · F/E/V 검증중"
    if technical_score < 30:
        return "red", "🔴 기술 약세"
    return "yellow", "🟡 조건부/대기"


def apply_manual_snapshot(row, price, price_timestamp, setup, context):
    """Overlay the latest Yahoo price without pretending an unfinished candle is final.

    Muse fix 2026-10-01 (extended): the overlay is a display/downgrade tool
    only — it may never upgrade a verdict beyond the completed-session
    classification:
    - a live tick inside the buy zone (or touching the trigger) does NOT
      promote a stock whose daily gate failed: intraday there is no
      reversal/trend/volume confirmation, so the touch is annotated on the
      card, not promoted to blue/green;
    - gate-passed stocks keep their state while the live price confirms, and
      are downgraded when the live price breaks the completed-session MA20
      or the invalidation price;
    - stale daily data is never overridden by a live price;
    - implausible ticks (beyond the KRX +/-30% daily limit vs the completed
      close) and stale feed timestamps are rejected outright.
    """
    price = float(price)
    ref = row.get("price")
    if price <= 0 or (ref and (price > float(ref) * 1.30 or price < float(ref) * 0.70)):
        row["snapshot_status"] = "rejected: implausible live price vs completed close"
        return row
    expected = (context or {}).get("expected_completed_session")
    if expected and price_timestamp:
        try:
            ts_date = datetime.fromisoformat(str(price_timestamp)).date().isoformat()
        except ValueError:
            ts_date = None
        if ts_date is not None and ts_date < expected:
            row["snapshot_status"] = "rejected: stale live-price timestamp"
            return row

    low, high = map(float, setup["buy"])
    stop = setup.get("stop")
    trigger = setup.get("trigger")
    ma20 = row.get("ma20")
    in_zone = low <= price <= high
    invalidated = stop is not None and price <= float(stop)
    triggered = (
        trigger is not None
        and price >= float(trigger)
        and price <= float(trigger) * 1.08
    )
    above_ma20 = ma20 is None or price >= float(ma20)
    gate_passed = bool(row.get("setup_pass"))
    data_valid = bool(row.get("quote_valid"))

    delta = 0
    if gate_passed and in_zone:
        delta += 8
    if gate_passed and triggered:
        delta += 5
    if not above_ma20:
        delta -= 10
    if invalidated:
        delta -= 25
    row["execution_score"] = round(clamp(float(row["execution_score"]) + delta), 1)

    if invalidated or row.get("invalidated"):
        row["state"], row["label"] = "red", "🔴 현재가 손절선 이탈"
        reason = (
            "수동 조회 현재가가 손절선 이하"
            if invalidated
            else "완료세션 무효화 상태 — 장중 가격으로 해제 불가"
        )
    elif row.get("overheated"):
        row["state"], row["label"] = "red", "🔴 보류"
        reason = "완료세션 과열/이격 과다 — 장중 가격으로 해제 불가"
    elif not data_valid:
        reason = "일봉 데이터 stale — 현재가로 판정을 바꾸지 않음"
    elif not above_ma20:
        if row.get("state") in ("green", "blue"):
            row["state"], row["label"] = "yellow", "🟡 현재가 MA20 하회"
        reason = "수동 조회 현재가가 완료세션 MA20 아래 — 종가 확인 필요"
    elif gate_passed and (in_zone or triggered):
        reason = "현재가로 일봉 셋업 통과 유지 확인 · 종가는 미확정"
    elif gate_passed:
        reason = "일봉 셋업 통과 유지 · 현재가는 구간/트리거 밖 — 종가 재확인 필요"
    elif in_zone:
        reason = "현재가 매수구간 진입 — 일봉 셋업 미통과라 종가 확인 전 승격 안 함"
    elif triggered:
        reason = "현재가 트리거 터치 — 종가 돌파가 아니라 승격 안 함"
    else:
        reason = "수동 조회 현재가 반영 · 일봉 지표는 완료세션 기준"
    row.update({
        "price": price,
        "setup_reason": reason,
        "price_mode": "manual_snapshot",
        "price_timestamp": price_timestamp or context["calculated_at"],
        "live_in_buy_zone": in_zone,
        "live_triggered": triggered,
        "live_invalidated": invalidated,
    })
    return row


def process_stock(stock, bench_df, context, research_map, intraday_snapshot=False, regime=None):
    symbol = stock["code"] + (".KS" if stock["exchange"] == "KS" else ".KQ")
    raw = load_history(symbol)
    hist, quote_as_of, quote_ok = select_completed(raw, context["expected_completed_session"])
    if bench_df is not None:
        bench_hist, bench_as_of, bench_ok = select_completed(
            bench_df, context["expected_completed_session"]
        )
    else:
        bench_hist, bench_as_of, bench_ok = None, None, False
    benchmark_aligned = bool(
        quote_ok and bench_ok and quote_as_of == bench_as_of
    )

    metrics = technical_metrics(
        hist, bench_hist, relative_valid=benchmark_aligned
    )
    gate = setup_gate(hist, metrics, stock["setup"], regime=regime)
    research = research_map.get(stock["code"])
    evidence_status = research.get("overall_status", "legacy_unverified") if research else "legacy_unverified"
    research_score, research_score_status = compute_research_score(research)

    data_valid = bool(quote_ok)
    state, label = classify(
        data_valid, gate, evidence_status, research_score, metrics["technical_score"]
    )

    legacy = stock.get("legacy_scores", {})
    regime_adj = float((regime or {}).get("execution_adjustment", 0.0) or 0.0)
    execution_score = round(
        clamp(
            metrics["technical_score"]
            + (10 if gate["setup_pass"] else -10)
            + regime_adj
        ),
        1,
    )

    row = {
        "name": stock["name"],
        "code": stock["code"],
        "exchange": stock["exchange"],
        "page": stock["page"],
        "theme": stock["theme"],
        "source": SOURCE,
        "quote_as_of": quote_as_of,
        "benchmark_as_of": bench_as_of,
        "benchmark_status": "aligned" if benchmark_aligned else "stale_or_unavailable",
        "expected_completed_session": context["expected_completed_session"],
        "session": context["market_state"],
        "chart": chart_series(hist),
        "calculated_at": context["calculated_at"],
        "data_status": "valid" if data_valid else "stale",
        "quote_valid": data_valid,
        "evidence_status": evidence_status,
        "research_F": None if not research else research.get("F", {}).get("score"),
        "research_E": None if not research else research.get("E", {}).get("score"),
        "research_V": None if not research else research.get("V", {}).get("score"),
        "research_F_status": None if not research else research.get("F", {}).get("status"),
        "research_E_status": None if not research else research.get("E", {}).get("status"),
        "research_V_status": None if not research else research.get("V", {}).get("status"),
        "research_next_check": [] if not research else research.get("next_check", []),
        "evidence_notes": [] if not research else (
            research.get("F", {}).get("basis", [])
            + research.get("E", {}).get("basis", [])
            + research.get("V", {}).get("basis", [])
        ),
        "evidence_sources": [] if not research else list(dict.fromkeys(
            research.get("F", {}).get("sources", [])
            + research.get("E", {}).get("sources", [])
            + research.get("V", {}).get("sources", [])
        )),
        "legacy_F": legacy.get("F"),
        "legacy_E": legacy.get("E"),
        "legacy_V": legacy.get("V"),
        "legacy_PR": legacy.get("PR"),
        "research_score": research_score,
        "research_score_status": research_score_status,
        "execution_score": execution_score,
        "regime_level": (regime or {}).get("level", "unknown"),
        "regime_label": (regime or {}).get("label", REGIME_LABELS["unknown"]),
        "regime_adjustment": regime_adj,
        **metrics,
        **gate,
        "state": state,
        "label": label,
    }
    if intraday_snapshot:
        if not data_valid:
            row["snapshot_status"] = "skipped: stale daily data is never overridden by a live price"
        else:
            try:
                current_price, price_timestamp = load_current_price(symbol)
                return apply_manual_snapshot(row, current_price, price_timestamp, stock["setup"], context)
            except Exception as exc:
                row["snapshot_status"] = f"unavailable: {type(exc).__name__}"
    return row


def should_auto_snapshot(now_kst, explicit_snapshot=False, completed_only=False):
    """Decide the intraday overlay for plain (unflagged) runs.

    Muse 2026-10-01: the GitHub App cannot edit workflow files in this repo,
    so the market-hours decision lives here instead of the workflow YAML.
    Plain runs on weekdays 09:00-15:40 KST overlay live prices automatically —
    the board stays fresh without anyone clicking through the Actions page.
    Explicit flags always win; the 16:10 scheduled run lands after 15:40 and
    therefore finalizes completed-session closes.
    """
    if explicit_snapshot:
        return True
    if completed_only:
        return False
    if now_kst.weekday() >= 5:
        return False
    hm = now_kst.hour * 100 + now_kst.minute
    return 900 <= hm <= 1540


def build_signals(rows, as_of, market_context=None):
    """Display-only signal lists built from completed-session row metrics.

    new_high: 종가 기준 52주 신고가 경신 (last completed close is the highest
    close of the trailing 252 sessions). near_high: 신고가까지 -5% 이내
    (경신 종목 제외, 장중 터치 포함 표시). volume_surge: 거래량이 직전 20일
    평균의 1.8배 이상. Tracked stocks only; signals never feed execution or
    research scores.
    """
    valid = [
        r
        for r in rows
        if r.get("data_status") == "valid" and r.get("price") is not None
    ]

    def slim(r):
        return {
            "code": r["code"],
            "name": r["name"],
            "page": r.get("page"),
            "price": r.get("price"),
            "change_pct": r.get("change_pct"),
            "rs_score": r.get("rs_score"),
            "volume_ratio": r.get("volume_ratio"),
            "state": r.get("state"),
            "execution_score": r.get("execution_score"),
            "high52": r.get("high52_actual"),
            "high52_date": r.get("high52_date"),
            "dist_high52_pct": r.get("dist_high52_pct"),
            "days_since_high52": r.get("days_since_high52"),
            "new_high_close": bool(r.get("new_high_close")),
            "new_high_touch": bool(r.get("new_high_touch")),
            "se_pos52": r.get("se_pos52"),
        }

    new_high = sorted(
        (slim(r) for r in valid if r.get("new_high_close")),
        key=lambda x: (-(x["change_pct"] or 0), -(x["rs_score"] or 0)),
    )
    near_high = sorted(
        (
            slim(r)
            for r in valid
            if not r.get("new_high_close")
            and r.get("dist_high52_pct") is not None
            and r["dist_high52_pct"] >= -5.0
        ),
        key=lambda x: -x["dist_high52_pct"],
    )
    volume_surge = sorted(
        (slim(r) for r in valid if (r.get("volume_ratio") or 0) >= 1.8),
        key=lambda x: -x["volume_ratio"],
    )
    return {
        "as_of": as_of,
        "new_high": new_high,
        "near_high": near_high,
        "volume_surge": volume_surge,
        "market_context": market_context,
        "source": "Mingo tracked stocks · completed-session daily data (display only)",
    }


def main(now=None, intraday_snapshot=False, completed_only=False):
    with open(CFG, encoding="utf-8") as f:
        cfg = json.load(f)
    research_map = {}
    if os.path.exists(EVIDENCE):
        with open(EVIDENCE, encoding="utf-8") as f:
            research_map = json.load(f).get("stocks", {})

    context = market_context(now)
    snapshot_auto = False
    if not intraday_snapshot and not completed_only:
        if should_auto_snapshot(datetime.fromisoformat(context["calculated_at"])):
            intraday_snapshot = True
            snapshot_auto = True
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
            errors.append(f"benchmark {ex}: {exc} — relative-return metric withheld")

    regime = market_regime(bench, context["expected_completed_session"])

    index_series = build_index_series(bench, completed_session=context["expected_completed_session"])
    # 2026-10-02: index live overlay removed per user request — completed-session values only

    rows = []
    for stock in cfg["stocks"]:
        try:
            b = bench.get(stock["exchange"])
            row = process_stock(stock, b, context, research_map, intraday_snapshot, regime=regime)
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

    # RS (종합) and the summary extras come from StockEasy summary pages,
    # refreshed every run from a single fetch per stock. On fetch failure,
    # fall back to the previous run's values marked stale.
    se_fields = (
        "se_market_cap", "se_high52", "se_low52", "se_pos52",
        "se_quarterly", "se_disclosures", "se_sectors",
    )
    for row in rows:
        page = fetch_stockeasy_page(row["code"])
        rs = parse_stockeasy_rs(page) if page else None
        if rs is not None:
            row["rs_score"] = rs["score"]
            row["rs_source"] = STOCKEASY_RS_SOURCE
            row["rs_basis_date"] = rs["basis_date"]
            row["rs_basis_price"] = rs["basis_price"]
            row["rs_status"] = "live"
        else:
            prev = old.get(row["code"], {})
            row["rs_score"] = prev.get("rs_score")
            row["rs_source"] = prev.get("rs_source", STOCKEASY_RS_SOURCE)
            row["rs_basis_date"] = prev.get("rs_basis_date")
            row["rs_basis_price"] = prev.get("rs_basis_price")
            row["rs_status"] = "stale_fallback" if prev.get("rs_score") is not None else "unavailable"
        summ = parse_stockeasy_summary(page) if page else None
        prev = old.get(row["code"], {})
        if summ is not None:
            row["se_market_cap"] = summ.get("market_cap")
            row["se_high52"] = summ.get("high52")
            row["se_low52"] = summ.get("low52")
            row["se_pos52"] = summ.get("pos52")
            row["se_quarterly"] = summ.get("quarterly")
            row["se_disclosures"] = summ.get("disclosures")
            row["se_sectors"] = summ.get("sectors")
            row["se_status"] = "live"
        else:
            for field in se_fields:
                row[field] = prev.get(field)
            row["se_status"] = (
                "stale_fallback" if prev.get("se_status") else "unavailable"
            )

    # Market-wide investor flow (외국인/기관/개인 순매수) from the StockEasy
    # main page; display-only context for the board header.
    market_flow = fetch_stockeasy_market()
    prev_flow = {}
    if os.path.exists(OUT):
        try:
            with open(OUT, encoding="utf-8") as f:
                prev_flow = (json.load(f).get("market_flow") or {})
        except Exception:
            prev_flow = {}
    if market_flow is not None:
        market_flow_out = {
            **market_flow,
            "source": STOCKEASY_FLOW_SOURCE,
            "status": "live",
        }
    elif prev_flow.get("foreign") is not None:
        market_flow_out = {**prev_flow, "status": "stale_fallback"}
    else:
        market_flow_out = {"status": "unavailable"}

    # Market-wide 52-week new-high sector flow from StockEasy (public
    # sector-flow endpoint; the per-stock dashboard endpoint needs a login
    # session, so market-wide stock lists are linked, not collected).
    sector_flow = fetch_stockeasy_sector_flow()
    prev_ctx = {}
    if os.path.exists(OUT):
        try:
            with open(OUT, encoding="utf-8") as f:
                prev_ctx = (
                    (json.load(f).get("signals") or {}).get("market_context") or {}
                )
        except Exception:
            prev_ctx = {}
    if sector_flow is not None:
        sector_ctx = {
            **sector_flow,
            "source": STOCKEASY_SECTOR_FLOW_SOURCE,
            "status": "live",
        }
    elif prev_ctx.get("today_total") is not None:
        sector_ctx = {**prev_ctx, "status": "stale_fallback"}
    else:
        sector_ctx = {"status": "unavailable"}

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
        "market_regime": regime,
        "index_series": index_series,
        "market_flow": market_flow_out,
        "signals": build_signals(
            rows, context["expected_completed_session"], sector_ctx
        ),
        "source": SOURCE,
        "price_mode": "manual_snapshot" if intraday_snapshot else "completed_session",
        "snapshot_auto": snapshot_auto,
        "notes": [
            "completed regular-session daily data only",
            "stale/error/fallback can never produce green",
            "legacy F/E/V are audit-only until structured evidence is re-verified",
            "price decline alone does not increase valuation score",
            "market regime (KOSPI/KOSDAQ vs MA20/MA60 + 20d return) modulates execution only: relative-overheat yardstick, bounded +/-10 execution adjustment, defense-mode setup blocks; invalidation and research verification are regime-independent",
            "manual intraday snapshot never upgrades a verdict beyond the completed-session classification: it annotates zone/trigger touches, downgrades on MA20/invalidation breaks, and rejects implausible or stale ticks",
            "index cards may carry a display-only live value (live_close/live_change_pct) next to the completed-session close during snapshot runs; the market regime and all gates never use it",
            "RS (rs_score) is the 종합 RS published by StockEasy (stockeasy.intellio.kr) per-stock summary pages, fetched each run; on fetch failure the previous value is kept with rs_status=stale_fallback. RS is display/context only and does not enter execution or research scores",
            "StockEasy summary extras (se_* fields: market cap, 52w high/low and position, last reported quarters, latest disclosures, sector tags) and market_flow (외국인/기관/개인 net buying) are display/context only, refreshed on the same cadence; they never enter execution or research scores",
            "signals (52w new-high / near-high within -5% / volume surge >= 1.8x) are computed from completed-session daily data for tracked stocks only and are display/context only; they never enter execution or research scores",
        ],
        "errors": errors,
        "stocks": rows,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"updated {len(rows)} stocks; errors={len(errors)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--intraday-snapshot", action="store_true")
    parser.add_argument("--completed-only", action="store_true")
    args = parser.parse_args()
    main(intraday_snapshot=args.intraday_snapshot, completed_only=args.completed_only)
