"""Sector heatmap: every stock of a market grouped by sector, sized by market cap and
colored by its return over 1D / 1W / 1M / 3M / YTD.

Returns come from the stored daily bars (the same split-adjusted bars as the breadth
indicators; a Korean corporate-action break restarts the series, see indicators.cut_breaks).
Sector and size come from listing providers, fetched at most once a day:
  US     — Nasdaq stock screener (sector, industry, market cap in USD)
  Korea  — Naver industry groups (79, WICS-like: 반도체와반도체장비 ...) with market value (KRW);
           a stock in no group falls back to its KRX KIND (KSIC) industry
  crypto — no sectors; sized by 20-day USDT turnover
"""
import datetime as dt

import pandas as pd

from . import indicators, store, universes
from .collectors import http_session

SCREENER = "https://api.nasdaq.com/api/screener/stocks"
NAVER_IND = "https://m.stock.naver.com/api/stocks/industry"
BROWSER_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"

SECTOR_KO = {
    "Technology": "기술", "Health Care": "헬스케어", "Finance": "금융", "Consumer Discretionary": "경기소비재",
    "Consumer Staples": "필수소비재", "Industrials": "산업재", "Energy": "에너지", "Utilities": "유틸리티",
    "Real Estate": "부동산", "Basic Materials": "소재", "Telecommunications": "통신", "Miscellaneous": "기타",
}
# market -> (bars table, universe table, sessions per 1W / 1M / 3M / 1Y)
MARKETS = {"yahoo": ("bars_yahoo", "universe_yahoo", (5, 21, 63, 252)),
           "kospi": ("bars_kospi", "universe_kospi", (5, 21, 63, 252)),
           "kosdaq": ("bars_kosdaq", "universe_kosdaq", (5, 21, 63, 252)),
           "crypto": ("bars_crypto", "universe_crypto", (7, 30, 91, 365))}
PERIODS = ["r1d", "r1w", "r1m", "r3m", "r1y", "ytd"]
HISTORY_DAYS = 400  # calendar days of bars read: one year of sessions plus YTD
ALL = "시장 전체"  # cap-weighted index of every stock in the map


def _daily(name: str, fetch) -> pd.DataFrame:
    """Provider table cached for the day (data/<name>.parquet); a failed fetch reuses the last copy."""
    old = store.read(name)
    today = dt.date.today().isoformat()
    if len(old) and str(old["fetched"].iloc[0]) == today:
        return old
    try:
        df = fetch().assign(fetched=today)
    except Exception as e:  # noqa: BLE001
        if len(old):
            store.log("warn", "sectors", f"{name}: {e}; using {old['fetched'].iloc[0]} copy")
            return old
        raise
    store.write(name, df)
    return df


def us_info() -> pd.DataFrame:
    s = http_session()
    s.headers.update({"User-Agent": BROWSER_UA, "Accept": "application/json"})
    r = s.get(SCREENER, params={"tableonly": "true", "limit": "25", "download": "true"}, timeout=60)
    r.raise_for_status()
    rows = r.json()["data"]["rows"]
    if len(rows) < 3000:
        raise RuntimeError(f"Nasdaq screener: only {len(rows)} rows")
    df = pd.DataFrame(rows)
    return pd.DataFrame({"ticker": df["symbol"].str.strip().str.replace("/", ".", regex=False),
                         "sector": df["sector"].map(lambda x: SECTOR_KO.get(x, x or "기타")),
                         "industry": df["industry"].fillna(""),
                         "mcap": pd.to_numeric(df["marketCap"], errors="coerce")})


def _num(x: str) -> float | None:
    try:
        return float(x.replace(",", ""))
    except (AttributeError, ValueError):
        return None


def kr_info() -> pd.DataFrame:
    s = http_session()
    s.headers["User-Agent"] = BROWSER_UA
    r = s.get(NAVER_IND, params={"page": 1, "pageSize": 100}, timeout=30)
    r.raise_for_status()
    rows = []
    for grp in r.json()["groups"]:
        for page in range(1, 20):
            r = s.get(f"{NAVER_IND}/{grp['no']}", params={"page": page, "pageSize": 100}, timeout=30)
            r.raise_for_status()
            stocks = r.json().get("stocks") or []
            rows += [(x["itemCode"], grp["name"], (_num(x.get("marketValue")) or 0) * 1e8 or None)  # 억원 -> 원
                     for x in stocks]
            if len(stocks) < 100:
                break
    if len(rows) < 1500:
        raise RuntimeError(f"Naver industries: only {len(rows)} stocks")
    return pd.DataFrame(rows, columns=["ticker", "sector", "mcap"]).drop_duplicates("ticker")


def returns(bars: pd.DataFrame, p: universes.Params, steps: tuple[int, ...]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(per ticker: last date/close, 1D/1W/1M/3M/1Y/YTD % and 20-bar average turnover,
    per ticker per day: return) within the ticker's latest unbroken series."""
    b = indicators.cut_breaks(bars, p.daily_limit, p.max_gap_days).sort_values(["ticker", "date"])
    b["base"] = b["ticker"].str.split("#").str[0]
    b = b[b["ticker"] == b.groupby("base")["ticker"].transform("last")]
    g = b.groupby("base")
    last = g.tail(1).set_index("base")
    out = pd.DataFrame({"date": last["date"], "close": last["close"]})
    for col, n in zip(["r1d", "r1w", "r1m", "r3m", "r1y"], (1, *steps)):
        prev = g["close"].nth(-1 - n)
        prev.index = b.loc[prev.index, "base"]
        out[col] = (out["close"] / prev - 1) * 100
    year = max(b["date"]).year
    py = b[pd.to_datetime(b["date"]).dt.year < year].groupby("base")["close"].last()
    out["ytd"] = (out["close"] / py - 1) * 100
    out["turnover"] = (b.assign(tv=b["close"] * b["volume"]).groupby("base")["tv"]
                       .apply(lambda s: s.tail(20).mean()))
    daily = pd.DataFrame({"ticker": b["base"], "date": b["date"], "r": g["close"].pct_change()}).dropna()
    return out.rename_axis("ticker").reset_index(), daily


def sector_daily(daily: pd.DataFrame, stocks: pd.DataFrame) -> pd.DataFrame:
    """Daily return of each sector (and ALL) weighted by each stock's current size.
    ponytail: today's constituents and weights applied to the whole year (no historical caps or
    delisted names); a true index needs point-in-time caps."""
    d = daily.merge(stocks[["ticker", "sector", "size"]], on="ticker").dropna(subset=["size"])
    d = pd.concat([d, d.assign(sector=ALL)], ignore_index=True)
    d["wr"] = d["r"] * d["size"]
    g = d.groupby(["sector", "date"])
    out = (g["wr"].sum() / g["size"].sum()).rename("ret").reset_index()
    out["n"] = g.size().to_numpy()
    return out


def _bars(table: str, since: dt.date) -> pd.DataFrame:
    rel = f"read_parquet('{store.path(table).as_posix()}')"
    return store.sql(f"SELECT date, ticker, close, volume FROM {rel} WHERE date >= DATE '{since}'")


def build(market: str, info: pd.DataFrame | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    bars_t, uni_t, steps = MARKETS[market]
    u = store.read(uni_t)
    if u.empty or not store.path(bars_t).exists():
        return pd.DataFrame(), pd.DataFrame()
    u = u[(u["excluded_reason"] == "") & u["listed"]]
    today = dt.date.today()
    bars = _bars(bars_t, today - dt.timedelta(days=HISTORY_DAYS))
    bars = bars[bars["ticker"].isin(set(u["ticker"]))]
    if bars.empty:
        return pd.DataFrame(), pd.DataFrame()
    bars["date"] = pd.to_datetime(bars["date"]).dt.date
    r, daily = returns(bars, universes.params_of(market), steps)
    latest = r["date"].max()
    r = r[r["date"] >= latest - dt.timedelta(days=5)]  # halted / stale names are not today's market
    df = r.merge(u[["ticker", "name", "exchange", *(["industry"] if "industry" in u else [])]], on="ticker", how="left")
    if market == "yahoo":
        df = df.merge(info, on="ticker", how="left")
        df["size"] = df["mcap"].fillna(df["turnover"])
    elif market in ("kospi", "kosdaq"):
        df = df.merge(info, on="ticker", how="left")
        df["sector"] = df["sector"].fillna(df["industry"]).replace("", "기타")
        df["size"] = df["mcap"].fillna(df["turnover"])
    else:
        df["sector"], df["industry"], df["size"] = "크립토", "", df["turnover"]
    df["sector"] = df["sector"].fillna("기타")
    df["industry"] = df["industry"].fillna("")
    cols = ["ticker", "name", "exchange", "sector", "industry", "size", "close", *PERIODS, "date"]
    df = df[cols].assign(market=market)
    hist = [sector_daily(daily, df).assign(market=market)]
    if market == "yahoo":  # the NASDAQ-listed part has its own sector indexes
        hist.append(sector_daily(daily, df[df["exchange"] == "NASDAQ"]).assign(market="nasdaq"))
    return df, pd.concat(hist, ignore_index=True)


def refresh() -> dict:
    us = _daily("sector_info_us", us_info)[["ticker", "sector", "industry", "mcap"]]
    kr = _daily("sector_info_kr", kr_info)[["ticker", "sector", "mcap"]]
    frames, hists, counts = [], [], {}
    for market in MARKETS:
        df, hist = build(market, us if market == "yahoo" else kr)
        counts[market] = len(df)
        if len(df):
            frames.append(df)
            hists.append(hist)
    if not frames:
        raise RuntimeError("no bars for any market")
    out = pd.concat(frames, ignore_index=True)
    store.write("sector_map", out)
    store.write("sector_daily", pd.concat(hists, ignore_index=True))
    return {"latest_date": str(out["date"].max()), **counts}


def summary(market: str, period: str = "r1d", leaves: int = 800) -> dict:
    """Sector aggregates over all stocks (cap-weighted return, share of risers, best/worst) and the
    largest `leaves` stocks for the treemap. market 'nasdaq' = NASDAQ-listed part of the US map."""
    if period not in PERIODS:
        raise ValueError("unknown period")
    df = store.read("sector_map")
    src = "yahoo" if market == "nasdaq" else market
    df = df[df["market"] == src] if len(df) else df
    if market == "nasdaq" and len(df):
        df = df[df["exchange"] == "NASDAQ"]
    df = df.dropna(subset=[period, "size"])
    df = df[df["size"] > 0]
    if df.empty:
        return {"market": market, "period": period, "sectors": [], "stocks": []}
    sectors = []
    for name, g in df.groupby("sector"):
        w = g["size"] / g["size"].sum()
        top = g.nlargest(30, "size").sort_values(period)  # best / worst among the sector's larger names
        sectors.append({"sector": name, "n": len(g), "size": float(g["size"].sum()),
                        "ret": float((g[period] * w).sum()), "median": float(g[period].median()),
                        "up_pct": float((g[period] > 0).mean() * 100),
                        "best": top.iloc[-1][["ticker", "name", period]].tolist(),
                        "worst": top.iloc[0][["ticker", "name", period]].tolist()})
    sectors.sort(key=lambda x: -x["size"])
    stocks = df.nlargest(leaves, "size")[["ticker", "name", "sector", "industry", "size", "close", period]]
    return {"market": market, "period": period, "date": str(df["date"].max()), "n": len(df),
            "sectors": sectors, "stocks": stocks.rename(columns={period: "ret"}).to_dict("records")}


def history(market: str, days: int = 252, picked: list[str] | None = None, top: int = 7) -> dict:
    """Sector indexes over the last `days` sessions (=100 at the start), per-sector stats over all
    sectors (return, annualized volatility, correlation and beta to the whole market) and the
    correlation matrix of daily returns for the picked sectors (default: ALL and the `top` largest)."""
    sd = store.read("sector_daily")
    sd = sd[sd["market"] == market] if len(sd) else sd
    if sd.empty:
        return {"market": market, "dates": [], "picked": [], "series": {}, "stats": [], "corr": {"sectors": [], "matrix": []}}
    w = sd.pivot_table(index="date", columns="sector", values="ret").sort_index()
    w = (w[w[ALL].notna()] if ALL in w else w).tail(days)
    sizes = summary(market, "r1d", leaves=0)["sectors"]
    order = [x["sector"] for x in sizes]
    n = {x["sector"]: x["n"] for x in sizes}
    year = 365 if market == "crypto" else 252
    mkt = w[ALL] if ALL in w else None
    stats = []
    for sec in [ALL, *order]:
        r = w[sec].dropna() if sec in w else pd.Series(dtype=float)
        if len(r) < 5:
            continue
        both = pd.concat([r, mkt], axis=1).dropna() if mkt is not None else pd.DataFrame()
        beta = float(both.iloc[:, 0].cov(both.iloc[:, 1]) / both.iloc[:, 1].var()) if len(both) > 5 else None
        stats.append({"sector": sec, "n": n.get(sec, len(r) and None), "ret": float(((1 + r).prod() - 1) * 100),
                      "vol": float(r.std() * year ** 0.5 * 100),
                      "corr": float(both.iloc[:, 0].corr(both.iloc[:, 1])) if len(both) > 5 else None, "beta": beta})
    picked = [p for p in (picked or []) if p in w] or [c for c in [ALL, *[s for s in order if n.get(s, 0) >= 3][:top]] if c in w]
    level = (1 + w[picked].fillna(0)).cumprod() * 100
    cm = w[picked].corr(min_periods=max(5, len(w) // 3)).round(2)
    return {"market": market, "days": len(w), "dates": [str(d) for d in w.index], "picked": picked,
            "series": {c: [round(float(v), 2) for v in level[c]] for c in picked}, "stats": stats,
            "corr": {"sectors": picked, "matrix": [[None if pd.isna(v) else float(v) for v in row] for row in cm.to_numpy()]}}
