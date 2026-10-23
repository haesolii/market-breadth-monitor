"""One stock across every dataset: returns and rank within its sector, peers, broker reports,
active ETFs holding / trading it, earnings (US) or DART preliminary results (Korea) and investor flows."""
import pandas as pd

from . import analyst, dart, flows, sectors, store
from .analyst import _rows

KR = ("kospi", "kosdaq")


def search(q: str, limit: int = 20) -> list[dict]:
    m = store.read("sector_map")
    if m.empty or not q:
        return []
    q = q.strip()
    hit = m[(m["ticker"].str.upper() == q.upper()) | m["ticker"].str.upper().str.startswith(q.upper())
            | m["name"].fillna("").str.contains(q, case=False, regex=False)]
    exact = hit["ticker"].str.upper() == q.upper()
    hit = pd.concat([hit[exact], hit[~exact].nlargest(limit, "size")]).head(limit)
    return _rows(hit[["ticker", "name", "market", "exchange", "sector", "size"]])


def detail(ticker: str, market: str | None = None) -> dict | None:
    m = store.read("sector_map")
    rows = m[m["ticker"] == ticker] if len(m) else m
    if market:
        rows = rows[rows["market"] == market]
    if rows.empty:
        return None
    me = rows.nlargest(1, "size").iloc[0]
    mk, sec = me["market"], me["sector"]
    same = m[(m["market"] == mk) & (m["sector"] == sec)]
    ranks = {p: {"rank": int((same[p] > me[p]).sum() + 1), "of": int(same[p].notna().sum()),
                 "mkt_pctile": float((m.loc[m["market"] == mk, p] <= me[p]).mean() * 100)}
             for p in sectors.PERIODS if pd.notna(me[p])}
    peers = same.nlargest(12, "size")[["ticker", "name", "size", *sectors.PERIODS]]
    sd = store.read("sector_daily")
    sd = sd[(sd["market"] == mk) & (sd["sector"] == sec)].sort_values("date") if len(sd) and "above" in sd else pd.DataFrame()
    kr = mk in KR
    return {"ticker": ticker, "name": me["name"], "market": mk, "exchange": me["exchange"], "sector": sec, "industry": me["industry"],
            "size": float(me["size"]), "close": float(me["close"]), "date": str(me["date"]),
            "returns": {p: None if pd.isna(me[p]) else float(me[p]) for p in sectors.PERIODS}, "ranks": ranks,
            "sector_above": None if sd.empty or pd.isna(sd["above"].iloc[-1]) else float(sd["above"].iloc[-1]),
            "peers": _rows(peers), "etf": _etf(me["name"] if kr else ticker, kr),
            "analyst": analyst.stock(ticker) if kr else None, "dart": dart.view(code=ticker) if kr else [],
            "earnings": _earnings(ticker) if not kr else [], "flow": flows.stock(ticker) if kr else None}


def _etf(key: str, kr: bool) -> dict:
    """Funds holding the stock now (Korean CU lists name holdings, ARK lists tickers) and their changes."""
    latest, ch, fl = store.read("etf_latest"), store.read("etf_changes"), store.read("etf_funds")
    names = dict(zip(fl["etf"], fl["name"])) if len(fl) else {}
    col = "name" if kr else "ticker"
    h = latest[latest[col] == key] if len(latest) else latest
    c = ch[ch[col] == key].sort_values("date", ascending=False) if len(ch) else ch
    return {"holders": [{**r, "etf_name": names.get(r["etf"], r["etf"])} for r in _rows(h.sort_values("weight", ascending=False)[["etf", "shares", "weight", "date"]])],
            "changes": [{**r, "etf_name": names.get(r["etf"], r["etf"])} for r in _rows(c[["date", "etf", "kind", "shares_prev", "shares", "weight_prev", "weight"]].head(40))]}


def _earnings(ticker: str) -> list[dict]:
    e = store.read("earnings")
    return _rows(e[e["symbol"] == ticker].sort_values("date", ascending=False)) if len(e) else []
