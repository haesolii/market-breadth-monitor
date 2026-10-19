"""Global index monitor: daily closes from Yahoo, per-index summary and
anomaly flags ("특이사항"), comparison history and return correlations.

Only COMPLETED daily bars are stored: if an index's market is open right now,
its in-progress bar is dropped (the live state is reported separately).
"""
import concurrent.futures as cf
import datetime as dt
import json
import math
import os
import time

import numpy as np
import pandas as pd

from . import remote, store
from .collectors import http_session
from .config import DATA

DEFAULT = [
    ("^GSPC", "S&P 500", "미국"), ("^IXIC", "나스닥 종합", "미국"), ("^DJI", "다우존스", "미국"),
    ("^RUT", "러셀 2000", "미국"), ("^VIX", "VIX 변동성지수", "미국"),
    ("^KS11", "코스피", "아시아"), ("^KQ11", "코스닥", "아시아"), ("^N225", "닛케이 225", "아시아"),
    ("^HSI", "항셍", "아시아"), ("000001.SS", "상해종합", "아시아"), ("^TWII", "대만 가권", "아시아"),
    ("^NSEI", "인도 Nifty 50", "아시아"), ("^AXJO", "호주 ASX 200", "아시아"),
    ("^STOXX50E", "유로스톡스 50", "유럽"), ("^GDAXI", "독일 DAX", "유럽"), ("^FTSE", "영국 FTSE 100", "유럽"),
    ("^FCHI", "프랑스 CAC 40", "유럽"),
    ("^GSPTSE", "캐나다 TSX", "미주"), ("^BVSP", "브라질 보베스파", "미주"),
    ("CL=F", "WTI 원유 (근월물)", "원자재"), ("BZ=F", "브렌트유 (근월물)", "원자재"),
    ("^IRX", "미국 13주 금리", "채권"), ("^FVX", "미국 5년물 금리", "채권"), ("^TNX", "미국 10년물 금리", "채권"),
    ("^TYX", "미국 30년물 금리", "채권"),
]
# Yahoo quotes these as yields in percent: changes are shown in basis points.
YIELDS = {"^IRX", "^FVX", "^TNX", "^TYX"}
# Higher = worse for stocks (fear / rates): colors and flags are inverted.
INVERSE = {"^VIX"} | YIELDS
# Tradeable ETFs used as the Market Monitor's comparison panel (stored with the indices,
# but not part of the world-index list / summary).
ETF_BENCH = {"SPY": "SPY (S&P 500 ETF)", "QQQ": "QQQ (나스닥100 ETF)", "RSP": "RSP (S&P 500 동일가중 ETF)",
             "069500.KS": "KODEX 200", "229200.KS": "KODEX 코스닥150"}
CONFIG = DATA / "indices.json"


def config() -> list[dict]:
    if remote.ON:
        saved = remote.kv_get("indices_config")
        return saved or [{"symbol": s, "name": n, "region": r} for s, n, r in DEFAULT]
    if CONFIG.exists():
        return json.loads(CONFIG.read_text("utf-8"))
    return [{"symbol": s, "name": n, "region": r} for s, n, r in DEFAULT]


def save_config(items: list[dict]) -> None:
    if remote.ON:
        return remote.kv_set("indices_config", items)
    tmp = DATA / ".indices.tmp.json"
    tmp.write_text(json.dumps(items, ensure_ascii=False, indent=1), "utf-8")
    os.replace(tmp, CONFIG)


def chart(symbol: str, s=None, live: bool = False) -> tuple[pd.DataFrame, dict]:
    s = s or http_session()
    r = s.get(f"https://query2.finance.yahoo.com/v8/finance/chart/{symbol}",
              params={"period1": 946684800, "period2": int(time.time()), "interval": "1d"}, timeout=30)
    r.raise_for_status()
    res = (r.json().get("chart") or {}).get("result")
    if not res or not res[0].get("timestamp"):
        raise ValueError(f"{symbol}: no data")
    res = res[0]
    meta = res["meta"]
    off = meta.get("gmtoffset", 0)
    q = res["indicators"]["quote"][0]
    df = pd.DataFrame({
        "date": [dt.datetime.fromtimestamp(t + off, dt.timezone.utc).date() for t in res["timestamp"]],
        "open": q.get("open"), "high": q.get("high"), "low": q.get("low"), "close": q.get("close"),
    }).dropna(subset=["close"]).drop_duplicates("date", keep="last")
    for c in ("open", "high", "low"):  # some index days carry only a close
        df[c] = df[c].fillna(df["close"])
    reg = (meta.get("currentTradingPeriod") or {}).get("regular") or {}
    now = time.time()
    in_session = reg.get("start", 0) <= now < reg.get("end", 0)
    today_local = dt.datetime.fromtimestamp(now + off, dt.timezone.utc).date()
    if in_session and not live and len(df) and df["date"].iloc[-1] == today_local:
        df = df.iloc[:-1]  # in-progress session
    info = {"tz": meta.get("exchangeTimezoneName"), "live": in_session, "price": meta.get("regularMarketPrice"),
            "yahoo_name": meta.get("longName") or meta.get("shortName"), "currency": meta.get("currency")}
    return df.assign(symbol=symbol), info


def missing() -> bool:
    """A listed index or ETF has no stored history yet (newly added) -> refresh even when not stale."""
    df = store.read("indices")
    have = set(df["symbol"]) if len(df) else set()
    return any(it["symbol"] not in have for it in config()) or any(k not in have for k in ETF_BENCH)


def refresh(live: bool = False) -> dict:
    """live: keep the in-progress bar of indices whose market is open (provisional)."""
    items = config()
    items += [{"symbol": k} for k in ETF_BENCH if k not in {it["symbol"] for it in items}]
    s = http_session(pool=8)
    old = store.read("indices")
    frames, meta, failed = [], {}, []
    with cf.ThreadPoolExecutor(8) as ex:
        futs = {ex.submit(chart, it["symbol"], s, live): it["symbol"] for it in items}
        for f in cf.as_completed(futs):
            sym = futs[f]
            try:
                df, info = f.result()
            except Exception as e:  # noqa: BLE001
                failed.append(f"{sym}: {e}")
                continue
            n_old = int((old["symbol"] == sym).sum()) if len(old) else 0
            if n_old and len(df) < 0.9 * n_old:  # suspicious shrink -> keep stored history
                failed.append(f"{sym}: download shrank ({len(df)} < {n_old})")
                continue
            frames.append(df)
            meta[sym] = info
    if not frames:
        raise RuntimeError("all index downloads failed: " + "; ".join(failed[:5]))
    new = pd.concat(frames, ignore_index=True)
    # Keep stored history only for listed symbols that failed this time; drop removed ones.
    wanted = {it["symbol"] for it in items}
    keep = old[old["symbol"].isin(wanted) & ~old["symbol"].isin(new["symbol"])] if len(old) else old
    store.write("indices", pd.concat([keep, new], ignore_index=True).sort_values(["symbol", "date"]))
    store.set_source("indices", meta=meta)
    if failed:
        store.log("warn", "indices", "; ".join(failed))
    return {"latest_date": str(new["date"].max()), "indices": len(frames), "failed": len(failed)}


# ---- analysis -------------------------------------------------------------------
def _flag(code, label, level, strong=False):
    return {"code": code, "label": label, "level": level, "strong": strong}


def analyze(s: pd.Series, symbol: str, z_th: float, dd_th: float, today: dt.date) -> dict:
    """s: closes indexed by date (ascending). Returns metrics + anomaly flags."""
    c = float(s.iloc[-1])
    last = s.index[-1]
    is_yield = symbol in YIELDS
    if is_yield:  # yields: change in basis points, not percent of a percent
        chg = lambda base: (c - base) * 100  # noqa: E731
        r = s.diff()
    else:
        chg = lambda base: (c / base - 1) * 100  # noqa: E731
        r = s.pct_change()
    ret = lambda n: chg(float(s.iloc[-1 - n])) if len(s) > n else None  # noqa: E731
    prev_year = s[[d.year < last.year for d in s.index]]
    std1y = r.tail(252).std()
    r1 = r.iloc[-1] if len(r) > 1 else np.nan
    z = float(r1 / std1y) if std1y and not np.isnan(r1) else None
    w52 = s.tail(252)
    hi, lo = float(w52.max()), float(w52.min())
    sma50 = float(s.tail(50).mean()) if len(s) >= 50 else None
    sma200_s = s.rolling(200).mean()
    sma200 = float(sma200_s.iloc[-1]) if len(s) >= 200 else None
    above = (s > sma200_s).tail(6).tolist() if len(s) >= 205 else []
    m = {
        "date": str(last), "close": c, "chg1d": ret(1), "chg1w": ret(5), "chg1m": ret(21), "chg3m": ret(63),
        "ytd": chg(float(prev_year.iloc[-1])) if len(prev_year) else None, "unit": "bp" if is_yield else "%",
        "hi52": hi, "lo52": lo, "dd52": None if is_yield else (c / hi - 1) * 100,
        "from_lo52": None if is_yield else (c / lo - 1) * 100,
        "sma50": sma50, "sma200": sma200,
        "above50": c > sma50 if sma50 else None, "above200": c > sma200 if sma200 else None,
        "vol20": float(r.tail(20).std() * math.sqrt(252) * 100) if len(r) > 20 else None,  # bp/yr for yields
        "z1d": z, "stale_days": (today - last).days,
    }
    f = []
    inv = symbol in INVERSE
    if z is not None and abs(z) >= z_th:
        up = z > 0
        strong = abs(z) >= z_th + 1
        lab = f"{'금리 ' if is_yield else ''}{'급등' if up else '급락'} (평소 변동의 {abs(z):.1f}배)"
        f.append(_flag("big_move", lab, ("down" if up else "up") if inv else ("up" if up else "down"), strong))
    if is_yield:
        if c >= hi and len(w52) >= 200:
            f.append(_flag("high52", "금리 52주 최고", "down", True))
        elif c <= lo and len(w52) >= 200:
            f.append(_flag("low52", "금리 52주 최저", "up", True))
        if above and not all(above) and any(above):
            f.append(_flag("cross_up200", "금리 200일선 상향 돌파 (최근 5일)", "down") if above[-1]
                     else _flag("cross_dn200", "금리 200일선 하향 이탈 (최근 5일)", "up"))
    elif inv:
        if c >= 30:
            f.append(_flag("vix_fear", "공포 구간 (VIX ≥ 30)", "down", True))
        elif c >= 20:
            f.append(_flag("vix_alert", "경계 구간 (VIX ≥ 20)", "warn"))
        if m["chg1d"] is not None and m["chg1d"] >= 20:
            f.append(_flag("vix_spike", f"VIX 급등 ({m['chg1d']:+.0f}%)", "down", True))
    else:
        if c >= hi and len(w52) >= 200:
            f.append(_flag("high52", "52주 신고가", "up", True))
        elif c <= lo and len(w52) >= 200:
            f.append(_flag("low52", "52주 신저가", "down", True))
        if m["dd52"] <= -2 * dd_th:
            f.append(_flag("bear", f"약세장 (고점 대비 {m['dd52']:.1f}%)", "down", True))
        elif m["dd52"] <= -dd_th:
            f.append(_flag("correction", f"조정 국면 (고점 대비 {m['dd52']:.1f}%)", "warn"))
        if above and not all(above) and any(above):
            if above[-1]:
                f.append(_flag("cross_up200", "200일선 상향 돌파 (최근 5일)", "up"))
            else:
                f.append(_flag("cross_dn200", "200일선 하향 이탈 (최근 5일)", "down"))
    if m["stale_days"] > 4:
        f.append(_flag("stale", f"데이터 지연 ({m['stale_days']}일)", "stale"))
    m["flags"] = f
    return m


def summary(z_th: float = 2.0, dd_th: float = 10.0) -> dict:
    df = store.read("indices")
    meta = store.status()["sources"].get("indices", {}).get("meta", {})
    today = dt.datetime.now(dt.timezone.utc).date()
    rows = []
    for it in config():
        s = df[df["symbol"] == it["symbol"]].set_index("date")["close"].sort_index() if len(df) else pd.Series(dtype=float)
        row = {**it, "inverse": it["symbol"] in INVERSE, **(meta.get(it["symbol"]) or {})}
        if len(s) >= 2:
            row.update(analyze(s, it["symbol"], z_th, dd_th, today))
        else:
            row["flags"] = [_flag("nodata", "데이터 없음", "stale")]
        rows.append(row)
    _curve_flag(rows)
    return {"rows": rows, "correlation": correlation(df), "z_th": z_th, "dd_th": dd_th}


def _curve_flag(rows: list[dict]) -> None:
    """10-year minus 13-week Treasury yield; flag an inverted curve on the 10Y row."""
    by = {r["symbol"]: r for r in rows}
    t10, t3m = by.get("^TNX"), by.get("^IRX")
    if t10 and t3m and t10.get("close") is not None and t3m.get("close") is not None:
        spread = (t10["close"] - t3m["close"]) * 100
        t10["spread_10y3m"] = spread
        if spread < 0:
            t10["flags"].append(_flag("inverted", f"장단기 금리 역전 (10년−3개월 {spread:+.0f}bp)", "down", True))


def correlation(df: pd.DataFrame, days: int = 60) -> dict:
    if df.empty:
        return {"symbols": [], "matrix": []}
    have = set(df["symbol"].unique())
    syms = [it["symbol"] for it in config() if it["symbol"] in have]
    w = df.pivot_table(index="date", columns="symbol", values="close").sort_index()[syms]
    rets = w.pct_change(fill_method=None).tail(days)
    cm = rets.corr(min_periods=int(days * 0.6)).round(2)
    return {"symbols": syms, "days": days,
            "matrix": [[None if pd.isna(v) else float(v) for v in row] for row in cm.to_numpy()]}


def history(symbols: list[str], ohlc: bool = False, since=None) -> dict:
    """{symbol: [[date, close], ...]} or, with ohlc, [[date, open, high, low, close], ...]."""
    df = store.read("indices")
    out = {}
    for sym in symbols:
        s = df[df["symbol"] == sym].sort_values("date") if len(df) else df
        if since is not None and len(s):
            s = s[s["date"] >= since]
        if ohlc and "open" in s:
            o = s[["open", "high", "low"]].fillna(s["close"], axis=0) if len(s) else s
            out[sym] = [[str(d), float(a), float(h), float(lo), float(c)]
                        for d, a, h, lo, c in zip(s["date"], o["open"], o["high"], o["low"], s["close"])]
        else:
            out[sym] = [[str(d), float(c)] for d, c in zip(s["date"], s["close"])]
    return out
