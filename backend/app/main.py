"""FastAPI backend: http://localhost:8000 (the Next.js app proxies /api/* here)."""
import datetime as dt
import hashlib
import hmac
import os
import urllib.parse
import threading
from contextlib import asynccontextmanager

import pandas as pd
from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import analyst, brief, dart, earnings, etf, flows, indicators, macro, refresh, remote, research, sectors, stock, store, universes, usage, validation, world
from .config import MASSIVE_API_KEY, REFRESH_INTERVAL_MIN, YAHOO_SCANNER
from .indicators import MM_COLS
from .market_calendar import CALENDARS, latest_complete_session

SOURCE_INFO = {
    "massive": {"label": "Massive (자체 계산, 생존편향 없음)", "real": True, "tickers": True},
    "public_repo": {"label": "미국 전체 보통주 (상장폐지 포함)", "short": "미국 전체 (상장폐지 포함)", "real": True, "tickers": False},
    **{k: {"label": v["label"], "short": v["short"], "real": True, "tickers": True, "market": True,
           "cal": v["cal"], "benchmark": v["benchmark"], "etf": v["etf"], "params": v["params"]}
       for k, v in universes.describe().items()},
}

_stop = threading.Event()


@asynccontextmanager
async def lifespan(_app):
    if not remote.ON:  # deployed API is read-only; GitHub Actions refreshes the data
        threading.Thread(target=refresh.auto_loop, args=(_stop,), daemon=True, name="auto-refresh").start()
    yield
    _stop.set()


app = FastAPI(title="Market Breadth Monitor", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000"], allow_methods=["*"], allow_headers=["*"])

# Same single-user password gate as the frontend (cookie set by /auth/login); off when unset (local use).
_PW = os.getenv("DASHBOARD_PASSWORD", "")
_TOKEN = hashlib.sha256(f"{_PW}:mb".encode()).hexdigest() if _PW else ""


@app.middleware("http")
async def require_login(request: Request, call_next):
    if request.url.path == "/api/login":
        return await call_next(request)
    if _TOKEN and not hmac.compare_digest(request.cookies.get("mb_auth", ""), _TOKEN):
        return JSONResponse({"detail": "로그인이 필요합니다"}, status_code=401)
    if request.url.path == "/api/visit":  # page load + every 10 min from the status bar (never cached)
        usage.record_visit(request)
    res = await call_next(request)
    # Deployed site: the CDN answers repeat GETs, so API work does not grow with viewers.
    # Vercel won't cache on Vary: Cookie, so the dashboard also sends the token as X-Mb-Key
    # (from the readable mb_key cookie) and the cache is keyed by that header. Only requests
    # carrying the right key are cacheable; anything else misses and reaches the check above.
    key = request.headers.get("x-mb-key", "")
    if (remote.ON and request.method == "GET" and res.status_code == 200 and request.url.path not in NO_CDN
            and (not _TOKEN or hmac.compare_digest(key, _TOKEN))):
        ttl, swr = CDN_TTL.get(request.url.path, (60, 60))
        res.headers["Vercel-CDN-Cache-Control"] = f"max-age={ttl}, stale-while-revalidate={swr}"
        res.headers["Vary"] = "X-Mb-Key"
    elif _TOKEN and request.cookies.get("mb_key") != _TOKEN:  # logged in before mb_key existed
        res.set_cookie("mb_key", _TOKEN, max_age=60 * 60 * 24 * 30, secure=True, samesite="lax")
    return res


NO_CDN = {"/api/visit", "/api/login"}
CDN_TTL = {"/api/status": (30, 30)}  # (seconds fresh, seconds served stale while refetching); data: at most ~2 min old


@app.get("/api/visit")
def visit():
    return {"ok": True}


@app.post("/api/login")
async def login(request: Request):
    """Form post from /login: sets the auth cookie and records the attempt (for the daily report)."""
    form = urllib.parse.parse_qs((await request.body()).decode())
    nxt = (form.get("next") or ["/"])[0]
    nxt = nxt if nxt.startswith("/") and not nxt.startswith("//") else "/"
    ok = bool(_PW) and hmac.compare_digest((form.get("password") or [""])[0], _PW)
    usage.record_login(request, ok)
    if not ok:
        return RedirectResponse(f"/login?error=1&next={urllib.parse.quote(nxt)}", status_code=303)
    res = RedirectResponse(nxt, status_code=303)
    res.set_cookie("mb_auth", _TOKEN, max_age=60 * 60 * 24 * 30, httponly=True, secure=True, samesite="lax")
    res.set_cookie("mb_key", _TOKEN, max_age=60 * 60 * 24 * 30, secure=True, samesite="lax")  # readable: sent as X-Mb-Key
    return res


def records(df: pd.DataFrame) -> list[dict]:
    df = df.copy()
    for c in df.columns:
        if c == "date" or df[c].dtype == object:
            df[c] = df[c].map(lambda v: v.isoformat() if isinstance(v, (dt.date, pd.Timestamp)) else v)
    return df.astype(object).where(df.notna(), None).to_dict("records")


def available(table: str) -> list[str]:
    df = store.read(table)
    return sorted(df["source"].unique().tolist()) if len(df) else []


def default_source(table: str) -> str | None:
    av = available(table)
    for s in ("massive", "public_repo", "yahoo") if table == "breadth20" else ("massive", "yahoo", "nasdaq", "kospi", "kosdaq", "crypto"):
        if s in av:
            return s
    return None


def table_for(table: str, source: str | None) -> tuple[str, pd.DataFrame]:
    source = source or default_source(table)
    df = store.read(table)
    if source is None or df.empty or source not in set(df["source"]):
        raise HTTPException(404, "데이터가 아직 없습니다 — 수집 중이면 잠시 후 다시 확인하세요 (데이터 관리 메뉴에서 진행 상황 확인)")
    return source, df[df["source"] == source].sort_values("date").reset_index(drop=True)


# ---- endpoints ------------------------------------------------------------------
@app.get("/api/status")
def status():
    st = store.status()
    out = {"expected_session": str(latest_complete_session()), "busy": refresh.is_busy(),
           "enabled": refresh.enabled_sources(), "massive_key": bool(MASSIVE_API_KEY), "yahoo_scanner": YAHOO_SCANNER,
           "sources": {}, "log": st.get("log", [])[:50], "scheduler": st["sources"].get("_scheduler"),
           "breadth20_sources": available("breadth20"), "monitor_sources": available("market_monitor_daily"),
           "default_breadth20": default_source("breadth20"), "default_monitor": default_source("market_monitor_daily"),
           "source_info": SOURCE_INFO,
           "expected_sessions": {c: str(latest_complete_session(cal=c)) for c in ("NYSE", "XKRX")},
           "final_hours": {c: h for c, (_, h) in CALENDARS.items()}, "refresh_min": REFRESH_INTERVAL_MIN}
    enabled = refresh.enabled_sources()
    for s in ["indices", "macro", "public_repo", "yahoo", "nasdaq", "kospi", "kosdaq", "crypto", "massive", "sectors", "etf", "analyst", "earnings", "flows", "dart"]:
        ld = refresh.latest_date(s)
        derived = universes.UNIVERSES.get(s, {}).get("derived_from")
        out["sources"][s] = {**st["sources"].get(s, {}), "latest_date": str(ld) if ld else None,
                             "expected": str(latest_complete_session(cal=universes.cal_of(s))),
                             "enabled": s in enabled or derived in enabled, "derived_from": derived}
    return out


@app.post("/api/refresh")
def do_refresh(bg: BackgroundTasks, source: str | None = None):
    if remote.ON:
        return {"started": False, "reason": "서버 버전은 매일 자동 갱신됩니다 (GitHub Actions)"}
    if refresh.is_busy():
        return {"started": False, "reason": "이미 갱신 중입니다 (refresh already running)"}
    srcs = [source] if source else None
    if source and source not in refresh.REFRESHERS:
        raise HTTPException(400, "unknown source")
    bg.add_task(refresh.refresh, srcs)
    return {"started": True}


@app.get("/api/breadth20")
def breadth20(source: str | None = None):
    source, df = table_for("breadth20", source)
    cols = [c for c in ["date", "bull", "bear", "elig_20", "eligible_universe_count"] if c in df]
    return {"source": source, "rows": records(df[cols].assign(market=source))}


@app.get("/api/monitor")
def monitor(source: str | None = None):
    source, df = table_for("market_monitor_daily", source)
    b20 = store.read("breadth20")
    if len(b20):
        df = df.merge(b20[b20["source"] == source][["date", "bull", "bear"]], on="date", how="left")
    cols = [c for c in df.columns if c not in ("source",)]
    return {"source": source, "rows": records(df[cols].assign(market=source))}


@app.get("/api/day")
def day(date: dt.date, source: str | None = None, mm_source: str | None = None):
    """Snapshot for one date: values + 5/10-session changes. No forward returns here."""
    out = {"date": str(date), "breadth20": {}, "monitor": None}
    for s in available("breadth20"):
        _, df = table_for("breadth20", s)
        i = df.index[df["date"] == date]
        if len(i):
            k = i[0]
            row = {"bull": df.at[k, "bull"], "bear": df.at[k, "bear"]}
            for n in (5, 10):
                if k - n >= 0:
                    row[f"bull_chg{n}"] = df.at[k, "bull"] - df.at[k - n, "bull"]
                    row[f"bear_chg{n}"] = df.at[k, "bear"] - df.at[k - n, "bear"]
            out["breadth20"][s] = {**{k2: (None if pd.isna(v) else float(v)) for k2, v in row.items()}, "market": s}
    try:
        ms, mm = table_for("market_monitor_daily", mm_source)
        i = mm.index[mm["date"] == date]
        if len(i):
            k = i[0]
            cur = mm.loc[k, MM_COLS]
            out["monitor"] = {"source": ms, "values": {**records(mm.loc[[k]])[0], "market": ms}}
            for n in (5, 10):
                if k - n >= 0:
                    prev = mm.loc[k - n, MM_COLS]
                    out["monitor"][f"chg{n}"] = {c: (None if pd.isna(cur[c]) or pd.isna(prev[c]) else float(cur[c] - prev[c])) for c in MM_COLS}
    except HTTPException:
        pass
    return out


@app.get("/api/research")
def research_study(source: str | None = None, metric: str = "bear", threshold: float = 100, op: str = ">=",
                   mode: str = "independent", gap: int = Query(5, ge=1, le=60),
                   start: dt.date | None = None, end: dt.date | None = None, benchmark: str | None = None,
                   metric2: str | None = None, op2: str = ">=", threshold2: float | None = None):
    """metric2 / op2 / threshold2: optional second condition (AND), read from the same market."""
    source, s = _metric_series(metric, source)
    if metric2 and threshold2 is not None:
        _, s2 = _metric_series(metric2, source)
        s = s.merge(s2.rename(columns={"value": "value2"}), on="date", how="inner")
    if start:
        s = s[s["date"] >= start]
    if end:
        s = s[s["date"] <= end]
    benchmark = benchmark or universes.benchmark_of(source)
    res = research.study(s, benchmark_prices(benchmark), threshold, op, mode, gap, op2, threshold2 if metric2 else None)
    return {"source": source, "metric": metric, "threshold": threshold, "op": op, "mode": mode, "gap": gap,
            "metric2": metric2, "op2": op2, "threshold2": threshold2, "benchmark": benchmark, **res}


def _metric_series(metric: str, source: str | None) -> tuple[str, pd.DataFrame]:
    """(source, date/value frame) of one indicator; a source missing from the indicator's table
    (e.g. Bear of a market whose monitor is computed elsewhere) falls back to that table's default."""
    table = "breadth20" if metric in ("bull", "bear") else "market_monitor_daily"
    if table == "market_monitor_daily" and metric not in MM_COLS:
        raise HTTPException(400, "unknown metric")
    source, df = table_for(table, source if source in available(table) else None)
    return source, df[["date", metric]].rename(columns={metric: "value"})


COMPARE_MARKETS = ("yahoo", "nasdaq", "kospi", "kosdaq", "crypto")


@app.get("/api/compare")
def compare(metric: str = "t2108"):
    """One size-free breadth reading per market on a shared date axis: T2108, 10-day ratio,
    Bear as % of eligible stocks, net 4% movers as % of eligible stocks."""
    if metric not in ("t2108", "ratio10", "bear_pct", "net4_pct"):
        raise HTTPException(400, "unknown metric")
    mm, b20 = store.read("market_monitor_daily"), store.read("breadth20")
    out = {}
    for s in COMPARE_MARKETS:
        if metric == "bear_pct":
            df = b20[b20["source"] == s] if len(b20) else b20
            v = 100 * df["bear"] / df["elig_20"].where(df["elig_20"] > 0) if len(df) and "elig_20" in df else None
        else:
            df = mm[mm["source"] == s] if len(mm) else mm
            if metric == "net4_pct":
                v = 100 * (df["up4"] - df["down4"]) / df["elig_daily"].where(df["elig_daily"] > 0) if len(df) else None
            else:
                v = df[metric] if len(df) else None
        if v is not None:
            d = pd.DataFrame({"date": df["date"], "v": pd.to_numeric(v, errors="coerce")}).dropna().sort_values("date")
            out[s] = [[str(a), round(float(b), 2)] for a, b in zip(d["date"], d["v"])]
    return {"metric": metric, "series": out, "labels": {s: SOURCE_INFO[s].get("short", s) for s in out}}


@app.get("/api/research/flow")
def research_flow(source: str | None = None, days: int = Query(252, ge=0, le=5000), benchmark: str | None = None):
    """Indicator levels vs the benchmark's returns (research screen only: uses forward returns)."""
    source, _ = table_for("market_monitor_daily", source if source in available("market_monitor_daily") else None)
    benchmark = benchmark or universes.benchmark_of(source)
    res = research.indicator_study(research.indicator_frame(source), benchmark_prices(benchmark), research.SCORE_COLS, days or None)
    return {"source": source, "benchmark": benchmark, **res}


@app.get("/api/research/leadlag")
def research_leadlag(source: str | None = None, metric: str = "t2108", days: int = Query(756, ge=0, le=5000), benchmark: str | None = None):
    """Lead / lag and rolling correlation of one indicator (or the health score) with the benchmark."""
    source, _ = table_for("market_monitor_daily", source if source in available("market_monitor_daily") else None)
    mm = research.indicator_frame(source)
    if metric == "score":
        sc = research.health_score(mm, research.SCORE_COLS)
        mm = mm.assign(score=mm["date"].map(sc))
    elif metric not in mm:
        raise HTTPException(400, "unknown metric")
    benchmark = benchmark or universes.benchmark_of(source)
    return {"source": source, "benchmark": benchmark, **research.lead_lag(mm[["date", metric]], benchmark_prices(benchmark), metric, days or None)}


def benchmark_prices(symbol: str) -> pd.DataFrame:
    """(date, close) of a symbol in the world-index table."""
    df = store.read("indices")
    df = df[df["symbol"] == symbol][["date", "close"]] if len(df) else df
    if df.empty:
        raise HTTPException(404, f"벤치마크 '{symbol}' 데이터가 없습니다 (세계 지수 목록에 추가 후 갱신하세요)")
    return df


@app.get("/api/benchmarks")
def benchmarks():
    idx = store.read("indices")
    names = {**world.ETF_BENCH, **{it["symbol"]: it["name"] for it in world.config()}}
    listed = [it["symbol"] for it in world.config()] + list(world.ETF_BENCH)
    have = set(idx["symbol"]) if len(idx) else set()
    syms = [s for s in listed if s in have]
    return [{"symbol": s, "name": names.get(s, s)} for s in syms]


@app.get("/api/research/day")
def research_day(date: dt.date, benchmark: str = "^GSPC"):
    """Forward benchmark returns from one date (historical research screen only)."""
    fr = research.forward_returns(benchmark_prices(benchmark))
    r = fr[fr["date"] == date]
    if r.empty:
        raise HTTPException(404, f"해당 날짜의 {benchmark} 데이터 없음")
    return records(r)[0]


@app.get("/api/scan/dates")
def scan_dates():
    if remote.ON:  # precomputed recent sessions only
        h = store.read("scan_hits")
        return {s: sorted({str(d)[:10] for d in g["date"]}) for s, g in h.groupby("source")} if len(h) else {}
    out = {}
    for s in ("massive", *universes.UNIVERSES):
        b = store.read("breadth20")
        if len(b) and s in set(b["source"]):
            out[s] = [str(d) for d in sorted(b.loc[b["source"] == s, "date"])[-400:]]
    return out


@app.get("/api/scan")
def scan(date: dt.date | None = None, source: str | None = None):
    if source not in (None, "massive", *universes.UNIVERSES):
        raise HTTPException(400, "종목 단위 결과는 자체 계산 소스(미국 전체·나스닥·코스피·코스닥·크립토·massive)만 제공됩니다")
    if remote.ON:
        h = store.read("scan_hits")
        source = source or "yahoo"
        h = h[h["source"] == source].copy() if len(h) else h
        if h.empty:
            raise HTTPException(404, f"'{source}' 종목 검색 데이터가 없습니다.")
        h["date"] = pd.to_datetime(h["date"]).dt.date
        date = date or max(h["date"])
        hits = h[h["date"] == date].drop(columns=["source"])
    else:
        b = store.read("breadth20")
        have = set(b["source"]) if len(b) else set()
        source = source or ("massive" if "massive" in have else "yahoo")
        if source not in have:
            raise HTTPException(404, f"'{source}' 데이터가 없습니다. 데이터 관리에서 갱신하세요.")
        date = date or max(b.loc[b["source"] == source, "date"])
        hits = refresh.scan_hits(source, date)
    hits = hits.copy()
    hits["date"] = hits["date"].astype(str)
    return {"source": source, "date": str(date), "rows": records(hits.sort_values("ret5", ascending=False))}


@app.get("/api/validation")
def get_validation():
    report = remote.kv_get("validation") or {} if remote.ON else validation.report()
    return {**report, "reference": validation.compare_reference()}


class RefIn(BaseModel):
    date: dt.date
    metric: str
    value: float
    note: str = ""


@app.post("/api/reference")
def add_reference(r: RefIn):
    if r.metric not in validation.REF_METRICS:
        raise HTTPException(400, f"metric must be one of {validation.REF_METRICS}")
    store.upsert("manual_reference", pd.DataFrame([{**r.model_dump(), "entered_at": store.now_utc()}]), ["date", "metric"])
    return {"ok": True}


@app.delete("/api/reference")
def delete_reference(date: dt.date, metric: str):
    ref = store.read("manual_reference")
    if len(ref):
        store.write("manual_reference", ref[~((ref["date"] == date) & (ref["metric"] == metric))])
    return {"ok": True}


# ---- world indices ------------------------------------------------------------
@app.get("/api/world")
def world_summary(z: float = Query(2.0, gt=0, le=10), dd: float = Query(10.0, gt=0, le=90)):
    st = store.status()["sources"].get("indices", {})
    return {**world.summary(z, dd), "last_success": st.get("last_success"), "last_error": st.get("last_error")}


@app.get("/api/world/history")
def world_history(symbols: str, ohlc: bool = False, since: dt.date | None = None):
    return world.history([s for s in symbols.split(",") if s], ohlc, since)


class IndexIn(BaseModel):
    symbol: str
    name: str
    region: str = "기타"


@app.get("/api/world/config")
def world_config():
    return {"items": world.config(), "defaults": [{"symbol": s, "name": n, "region": r} for s, n, r in world.DEFAULT]}


@app.post("/api/world/config")
def world_set_config(items: list[IndexIn], bg: BackgroundTasks):
    known = {it["symbol"] for it in world.config()}
    for it in items:
        try:
            (it.symbol + it.name + it.region).encode("utf-8")
        except UnicodeEncodeError:
            raise HTTPException(400, f"잘못된 문자 인코딩입니다 (UTF-8 아님): {it.symbol!r}")
        if not it.symbol.strip() or not it.name.strip():
            raise HTTPException(400, "심볼과 이름은 비울 수 없습니다")
        if it.symbol not in known:  # validate new symbols before saving
            try:
                world.chart(it.symbol)
            except Exception as e:  # noqa: BLE001
                raise HTTPException(400, f"'{it.symbol}' 데이터를 가져올 수 없습니다: {e}")
    world.save_config([i.model_dump() for i in items])
    bg.add_task(refresh.refresh, ["indices"])
    return {"ok": True}


# ---- sector heatmap ---------------------------------------------------------------
@app.get("/api/sectors")
def sector_map(market: str = "yahoo", period: str = "r1d", leaves: int = Query(800, ge=10, le=3000)):
    if period not in sectors.PERIODS or market not in (*sectors.MARKETS, "nasdaq"):
        raise HTTPException(400, "unknown market or period")
    return sectors.summary(market, period, leaves)


@app.get("/api/sectors/history")
def sector_history(market: str = "yahoo", days: int = Query(252, ge=5, le=400), sectors_: str = Query("", alias="sectors")):
    if market not in (*sectors.MARKETS, "nasdaq"):
        raise HTTPException(400, "unknown market")
    return sectors.history(market, days, [x for x in sectors_.split("|") if x])


# ---- active ETF holdings ------------------------------------------------------------
@app.get("/api/etf")
def etf_overview(days: int = Query(7, ge=1, le=90)):
    st = store.status()["sources"].get("etf", {})
    return {**etf.overview(days), "last_success": st.get("last_success"), "last_error": st.get("last_error")}


@app.get("/api/etf/holdings")
def etf_holdings(etf_code: str = Query(..., alias="etf")):
    return etf.holdings(etf_code)


# ---- broker reports & earnings ---------------------------------------------------
@app.get("/api/analyst")
def analyst_feed(days: int = Query(7, ge=1, le=365), q: str = "", kind: str = "all", broker: str = ""):
    if kind not in ("all", "up", "down", "new"):
        raise HTTPException(400, "kind must be all|up|down|new")
    return analyst.feed(days, q.strip(), kind, broker)


@app.get("/api/analyst/stock")
def analyst_stock(code: str):
    return analyst.stock(code)


@app.get("/api/flows")
def kr_flows(days: int = Query(120, ge=5, le=400)):
    st = store.status()["sources"].get("flows", {})
    return {**flows.view(days), "last_success": st.get("last_success"), "last_error": st.get("last_error")}


@app.get("/api/dart")
def dart_prelim(days: int = Query(30, ge=1, le=365)):
    return {"enabled": bool(dart.DART_API_KEY) or not store.read("dart_prelim").empty, "rows": dart.view(days)}


@app.get("/api/stock/search")
def stock_search(q: str = ""):
    return stock.search(q)


@app.get("/api/stock")
def stock_detail(ticker: str, market: str | None = None):
    d = stock.detail(ticker, market)
    if d is None:
        raise HTTPException(404, f"'{ticker}' 종목을 찾을 수 없습니다 (섹터 맵에 있는 종목만 조회 가능)")
    return d


@app.get("/api/earnings")
def earnings_view(back: int = Query(7, ge=1, le=120), ahead: int = Query(14, ge=0, le=21), min_cap: float = Query(2e9, ge=0)):
    return earnings.view(back, ahead, min_cap)


# ---- macro (FRED) ---------------------------------------------------------------
@app.get("/api/macro")
def macro_summary():
    st = store.status()["sources"].get("macro", {})
    return {**macro.summary(), "last_success": st.get("last_success"), "last_error": st.get("last_error")}


@app.get("/api/macro/releases")
def macro_releases(days: int = Query(45, ge=1, le=730)):
    return macro.releases(days)


@app.get("/api/brief")
def ai_brief(n: int = Query(7, ge=1, le=60)):
    return brief.latest(n)


@app.get("/api/macro/history")
def macro_history(ids: str, since: dt.date | None = None):
    return macro.history([s for s in ids.split(",") if s], since)
