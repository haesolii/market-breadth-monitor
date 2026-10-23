"""Korean investor flows (Naver): net buying by foreigners / institutions / individuals.

  kr_flow        — per stock per day, for the TOP_N largest KOSPI + KOSDAQ stocks (by the sector
                   map's market value): net shares × that day's close = net value in KRW, plus the
                   foreign ownership ratio. BACKFILL_PAGES × 60 sessions on first sight of a stock,
                   then the last few sessions on each refresh.
  kr_flow_market — whole-market net value per day (억원) for KOSPI / KOSDAQ. Naver serves only the
                   current day, so the history starts with the first refresh (restored from Supabase
                   when the runner's data cache is gone).
"""
import datetime as dt
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from . import store
from .collectors import http_session

STOCK = "https://m.stock.naver.com/api/stock/{code}/trend"
INDEX = "https://m.stock.naver.com/api/index/{idx}/trend"
BROWSER_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"
TOP_N = 300
BACKFILL_PAGES = 2  # x 60 sessions
KEEP_DAYS = 400
WHO = {"foreign": "foreignerPureBuyQuant", "inst": "organPureBuyQuant", "indiv": "individualPureBuyQuant"}


def _num(x) -> float | None:
    try:
        return float(str(x).replace(",", "").replace("%", "").replace("+", ""))
    except (TypeError, ValueError):
        return None


def parse(code: str, items: list[dict]) -> pd.DataFrame:
    rows = []
    for x in items:
        close = _num(x.get("closePrice"))
        rows.append({"date": dt.datetime.strptime(x["bizdate"], "%Y%m%d").date(), "ticker": code, "close": close,
                     "hold_ratio": _num(x.get("foreignerHoldRatio")),
                     **{k: (_num(x.get(f)) or 0) * (close or 0) for k, f in WHO.items()}})
    return pd.DataFrame(rows)


def _stock(s, code: str, pages: int) -> pd.DataFrame:
    frames, bizdate = [], None
    for _ in range(pages):
        r = s.get(STOCK.format(code=code), params={"pageSize": 60 if pages > 1 else 10, **({"bizdate": bizdate} if bizdate else {})}, timeout=20)
        r.raise_for_status()
        items = r.json()
        if not items:
            break
        frames.append(parse(code, items))
        bizdate = (frames[-1]["date"].min() - dt.timedelta(days=1)).strftime("%Y%m%d")
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _market(s) -> pd.DataFrame:
    rows = []
    for m, idx in (("kospi", "KOSPI"), ("kosdaq", "KOSDAQ")):
        r = s.get(INDEX.format(idx=idx), timeout=20)
        r.raise_for_status()
        j = r.json()
        rows.append({"date": dt.datetime.strptime(j["bizdate"], "%Y%m%d").date(), "market": m, "foreign": _num(j.get("foreignValue")),
                     "inst": _num(j.get("institutionalValue")), "indiv": _num(j.get("personalValue"))})
    return pd.DataFrame(rows)


def top_stocks(n: int = TOP_N) -> pd.DataFrame:
    m = store.read("sector_map")
    m = m[m["market"].isin(["kospi", "kosdaq"])] if len(m) else m
    if m.empty:
        raise RuntimeError("sector map has no Korean stocks yet (run sectors first)")
    return m.nlargest(n, "size")[["ticker", "name", "market", "sector", "size"]]


def refresh() -> dict:
    s = http_session()
    s.headers["User-Agent"] = BROWSER_UA
    top = top_stocks()
    old = store.read("kr_flow")
    known = set(old["ticker"]) if len(old) else set()
    with ThreadPoolExecutor(8) as ex:
        frames = list(ex.map(lambda c: _stock(s, c, 1 if c in known else BACKFILL_PAGES), top["ticker"]))
    new = pd.concat([f for f in frames if len(f)], ignore_index=True)
    if new.empty:
        raise RuntimeError("Naver trend: no rows")
    out = pd.concat([old, new], ignore_index=True).drop_duplicates(["date", "ticker"], keep="last")
    out = out[out["date"] >= dt.date.today() - dt.timedelta(days=KEEP_DAYS)]
    store.write("kr_flow", out.sort_values(["date", "ticker"]).reset_index(drop=True))
    mk = pd.concat([store.read("kr_flow_market"), _market(s)], ignore_index=True).drop_duplicates(["date", "market"], keep="last")
    store.write("kr_flow_market", mk.sort_values("date").reset_index(drop=True))
    return {"latest_date": str(out["date"].max()), "stocks": int(new["ticker"].nunique()), "rows": len(out)}


# ---- read side ----------------------------------------------------------------------
def _sum(df: pd.DataFrame, keys: list[str], dates) -> pd.DataFrame:
    return df[df["date"].isin(dates)].groupby(keys)[list(WHO)].sum()


def overview(days: int = 120) -> dict:
    """Daily net value of the tracked stocks per investor (+ the official whole-market numbers where
    recorded), net buying by sector over 5 / 20 sessions, and the stocks most bought / sold."""
    f = store.read("kr_flow")
    if f.empty:
        return {"dates": [], "daily": {}, "market": [], "sectors": [], "stocks": {}}
    f = f.copy()
    f["date"] = pd.to_datetime(f["date"]).dt.date
    top = store.read("sector_map")
    top = top[top["market"].isin(["kospi", "kosdaq"])][["ticker", "name", "market", "sector", "size"]] if len(top) else pd.DataFrame()
    f = f.merge(top, on="ticker", how="left")
    dates = sorted(f["date"].unique())
    tail = dates[-days:]
    daily = _sum(f, ["date"], tail).reindex(tail).fillna(0) / 1e8  # 억원
    mk = store.read("kr_flow_market")
    sec = _sum(f, ["sector"], dates[-20:]).add_suffix("20").join(_sum(f, ["sector"], dates[-5:]).add_suffix("5")) / 1e8
    last5 = _sum(f, ["ticker"], dates[-5:]).join(f.drop_duplicates("ticker", keep="last").set_index("ticker")[["name", "market", "sector", "size", "hold_ratio"]])
    ratio = f.pivot_table(index="ticker", columns="date", values="hold_ratio")
    last5["hold_chg20"] = ratio.iloc[:, -1] - ratio.iloc[:, max(0, ratio.shape[1] - 21)]
    last5["foreign_pct"] = last5["foreign"] / last5["size"] * 100  # 5-day foreign net buying as % of market value
    last5[list(WHO)] = last5[list(WHO)] / 1e8  # 억원
    rows = lambda d: d.reset_index().astype(object).where(d.reset_index().notna(), None).to_dict("records")  # noqa: E731
    return {"latest": str(dates[-1]), "tracked": int(f["ticker"].nunique()), "dates": [str(d) for d in tail],
            "daily": {k: [round(float(v), 1) for v in daily[k]] for k in WHO},
            "market": [{**r, "date": str(r["date"])} for r in mk.to_dict("records")] if len(mk) else [],
            "sectors": rows(sec.sort_values("foreign20", ascending=False).round(1)),
            "stocks": {f"{who}_{side}": rows(getattr(last5, side)(15, who)[["name", "market", "sector", who, "hold_ratio", "hold_chg20", "foreign_pct"]].round(3))
                       for who in ("foreign", "inst") for side in ("nlargest", "nsmallest")}}


def stock(code: str, days: int = 120) -> dict:
    f = store.read("kr_flow")
    f = f[f["ticker"] == code].sort_values("date").tail(days) if len(f) else f
    if f.empty:
        return {"dates": []}
    return {"dates": [str(d) for d in f["date"]], "close": [None if pd.isna(v) else float(v) for v in f["close"]],
            **{k: [round(float(v) / 1e8, 1) for v in f[k]] for k in WHO},
            "hold_ratio": [None if pd.isna(v) else float(v) for v in f["hold_ratio"]],
            "sum5": {k: round(float(f[k].tail(5).sum()) / 1e8, 1) for k in WHO}, "sum20": {k: round(float(f[k].tail(20).sum()) / 1e8, 1) for k in WHO}}
