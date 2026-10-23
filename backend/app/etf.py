"""Active ETF holdings: daily snapshots and the changes between them (편입 / 편출 / 비중·수량 변화).

Funds: every Korean equity active ETF (Naver ETF list, by name; money-market, bond, rate and
covered-call actives are left out) up to MAX_KR by size, plus ARK's ETFs.
Holdings:
  Korea — WiseReport ETF page (navercomp), the full CU (creation unit) list: name, shares per
          CU, weight. Shares per CU change only when the manager trades (or the CU is resized).
  ARK   — the daily holdings CSV ARK publishes per fund (ticker, shares, weight).
Snapshots are kept locally (etf_snapshots); the dashboard reads the derived tables
etf_latest (latest snapshot per fund), etf_changes (all changes) and etf_funds.
History starts on the first collection day: providers keep no past holdings.
"""
import concurrent.futures as cf
import datetime as dt
import io
import json
import re

import pandas as pd

from . import store
from .collectors import http_session

NAVER_ETFS = "https://finance.naver.com/api/sise/etfItemList.nhn"
WISE = "https://navercomp.wisereport.co.kr/v2/ETF/index.aspx"
ARK_CSV = "https://assets.ark-funds.com/fund-documents/funds-etf-csv/{}"
ARK = {"ARKK": "ARK_INNOVATION_ETF_ARKK_HOLDINGS.csv", "ARKW": "ARK_NEXT_GENERATION_INTERNET_ETF_ARKW_HOLDINGS.csv",
       "ARKG": "ARK_GENOMIC_REVOLUTION_ETF_ARKG_HOLDINGS.csv", "ARKQ": "ARK_AUTONOMOUS_TECH._&_ROBOTICS_ETF_ARKQ_HOLDINGS.csv",
       "ARKF": "ARK_BLOCKCHAIN_&_FINTECH_INNOVATION_ETF_ARKF_HOLDINGS.csv", "ARKX": "ARK_SPACE_&_DEFENSE_INNOVATION_ETF_ARKX_HOLDINGS.csv"}
NOT_EQUITY = re.compile(r"머니마켓|금리|채권|국채|회사채|금융채|CD|KOFR|단기|혼합|커버드콜|TDF|TRF|달러|엔화|국공채|국고채|전단채|특수채|은행채|하이일드|크레딧|자산배분| 금액티브| 은액티브")
MAX_KR = 60
BROWSER_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"
SHARE_TOL = 0.005  # relative share change below this is rounding, not a trade


def funds() -> pd.DataFrame:
    s = http_session()
    s.headers["User-Agent"] = BROWSER_UA
    r = s.get(NAVER_ETFS, params={"etfType": "0"}, timeout=30)
    r.raise_for_status()
    items = pd.DataFrame(r.json()["result"]["etfItemList"])
    act = items[items["itemname"].str.contains("액티브") & ~items["itemname"].str.contains(NOT_EQUITY)]
    act = act.nlargest(MAX_KR, "marketSum")
    kr = pd.DataFrame({"etf": act["itemcode"], "name": act["itemname"], "market": "KR",
                       "aum": act["marketSum"] * 1e8, "ret3m": act["threeMonthEarnRate"]})  # 억원 -> 원
    us = pd.DataFrame({"etf": list(ARK), "name": [f"ARK {k}" for k in ARK], "market": "US", "aum": None, "ret3m": None})
    return pd.concat([kr, us], ignore_index=True)


def _kr_holdings(s, code: str) -> pd.DataFrame:
    r = s.get(WISE, params={"cmp_cd": code}, timeout=30)
    r.raise_for_status()
    m = re.search(r"var CU_data = (\{.*?\});", r.text, re.S)
    rows = json.loads(m.group(1)).get("grid_data") if m else None
    if not rows:
        raise ValueError(f"{code}: no CU data")
    df = pd.DataFrame(rows)
    return pd.DataFrame({"date": pd.to_datetime(df["TRD_DT"]).dt.date, "name": df["STK_NM_KOR"].str.strip(), "ticker": "",
                         "shares": pd.to_numeric(df["AGMT_STK_CNT"], errors="coerce"),
                         "weight": pd.to_numeric(df["ETF_WEIGHT"], errors="coerce")})


def _ark_holdings(s, fund: str) -> pd.DataFrame:
    r = s.get(ARK_CSV.format(ARK[fund]), timeout=30)
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text), dtype=str).dropna(subset=["fund", "company"])
    num = lambda c: pd.to_numeric(df[c].str.replace(r"[,$%]", "", regex=True), errors="coerce")  # noqa: E731
    return pd.DataFrame({"date": pd.to_datetime(df["date"], format="%m/%d/%Y").dt.date, "name": df["company"].str.strip(),
                         "ticker": df["ticker"].fillna("").str.strip(), "shares": num("shares"), "weight": num("weight (%)")})


def snapshot(fund_list: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    s = http_session(pool=8)
    s.headers["User-Agent"] = BROWSER_UA
    frames, failed = [], []

    def one(row):
        try:
            df = (_ark_holdings if row.market == "US" else _kr_holdings)(s, row.etf)
            if (dt.date.today() - max(df["date"])).days > 10:  # provider stopped updating this file
                return None, f"{row.etf}: stale holdings ({max(df['date'])})"
            return df.assign(etf=row.etf), None
        except Exception as e:  # noqa: BLE001
            return None, f"{row.etf}: {e}"

    with cf.ThreadPoolExecutor(8) as ex:
        for df, err in ex.map(one, fund_list.itertuples()):
            if err:
                failed.append(err)
            else:
                frames.append(df)
    return (pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()), failed


def changes(snaps: pd.DataFrame) -> pd.DataFrame:
    """One row per holding that entered, left, or changed shares between consecutive snapshots of a fund."""
    out = []
    for etf, g in snaps.groupby("etf"):
        dates = sorted(g["date"].unique())
        for prev_d, d in zip(dates[:-1], dates[1:]):
            a = g[g["date"] == prev_d].drop_duplicates("name").set_index("name")
            b = g[g["date"] == d].drop_duplicates("name").set_index("name")
            m = a[["shares", "weight"]].join(b[["shares", "weight", "ticker"]], how="outer", lsuffix="_prev")
            m["ticker"] = m["ticker"].fillna(a["ticker"].reindex(m.index))
            rel = (m["shares"] - m["shares_prev"]) / m["shares_prev"]
            kind = pd.Series(None, index=m.index, dtype=object)
            kind[m["shares_prev"].isna()] = "편입"
            kind[m["shares"].isna()] = "편출"
            kind[kind.isna() & (rel > SHARE_TOL)] = "증가"
            kind[kind.isna() & (rel < -SHARE_TOL)] = "감소"
            m = m.assign(kind=kind, etf=etf, date=d, prev_date=prev_d).dropna(subset=["kind"])
            out.append(m.rename_axis("name").reset_index())
    cols = ["date", "prev_date", "etf", "name", "ticker", "kind", "shares_prev", "shares", "weight_prev", "weight"]
    return pd.concat(out, ignore_index=True)[cols] if out else pd.DataFrame(columns=cols)


def refresh() -> dict:
    fl = funds()
    snap, failed = snapshot(fl)
    if snap.empty:
        raise RuntimeError("all ETF holdings downloads failed: " + "; ".join(failed[:5]))
    snaps = store.upsert("etf_snapshots", snap, ["etf", "date", "name"])
    snaps = snaps[snaps["etf"].isin(set(fl["etf"]))]  # funds dropped from the list stay stored, not shown
    latest = snaps[snaps["date"] == snaps.groupby("etf")["date"].transform("max")]
    store.write("etf_latest", latest.reset_index(drop=True))
    store.upsert("etf_changes", changes(snaps), ["date", "etf", "name"])  # kept even if old snapshots are lost
    store.write("etf_funds", fl)
    if failed:
        store.log("warn", "etf", f"{len(failed)} funds failed, e.g. {failed[:3]}")
    return {"latest_date": str(snap["date"].max()), "funds": int(snap["etf"].nunique()), "failed": len(failed),
            "snapshots": int(snaps["date"].nunique())}


# ---- read side ----------------------------------------------------------------------
def _returns() -> dict[tuple[str, str], float]:
    """(market, name or ticker) -> today's return, from the sector map (KR by name, US by ticker)."""
    sm = store.read("sector_map")
    if sm.empty:
        return {}
    out = {}
    for r in sm[["market", "ticker", "name", "r1d"]].dropna(subset=["r1d"]).itertuples():
        if r.market in ("kospi", "kosdaq"):
            out[("KR", r.name)] = r.r1d
        elif r.market == "yahoo":
            out[("US", r.ticker)] = r.r1d
    return out


def _key(market: str, name: str, ticker: str) -> tuple[str, str]:
    return (market, name if market == "KR" else ticker)


def overview(days: int = 7) -> dict:
    fl, latest, ch = store.read("etf_funds"), store.read("etf_latest"), store.read("etf_changes")
    if fl.empty:
        return {"funds": [], "changes": [], "consensus": []}
    rets = _returns()
    mk = dict(zip(fl["etf"], fl["market"]))
    names = dict(zip(fl["etf"], fl["name"]))
    if len(ch):
        ch = ch.copy()
        ch["date"] = pd.to_datetime(ch["date"]).dt.date
        cut = max(ch["date"]) - dt.timedelta(days=days)
        ch = ch[ch["date"] >= cut]
    funds_out = []
    for f in fl.itertuples():
        h = latest[latest["etf"] == f.etf] if len(latest) else latest
        c = ch[ch["etf"] == f.etf] if len(ch) else ch
        funds_out.append({"etf": f.etf, "name": f.name, "market": f.market, "aum": None if pd.isna(f.aum) else float(f.aum),
                          "ret3m": None if pd.isna(f.ret3m) else float(f.ret3m),
                          "date": str(max(h["date"])) if len(h) else None, "holdings": int(len(h)),
                          "changes": int(len(c)), "top": h.dropna(subset=["weight"]).nlargest(3, "weight")["name"].tolist()})  # some CU lists carry no weights
    rows = []
    for r in ch.itertuples() if len(ch) else []:
        m = mk.get(r.etf, "KR")
        rows.append({"date": str(r.date), "etf": r.etf, "etf_name": names.get(r.etf, r.etf), "market": m, "name": r.name,
                     "ticker": r.ticker, "kind": r.kind, "shares_prev": _f(r.shares_prev), "shares": _f(r.shares),
                     "weight_prev": _f(r.weight_prev), "weight": _f(r.weight), "ret1d": rets.get(_key(m, r.name, r.ticker))})
    # Names several funds bought (or sold) in the window: the managers' consensus moves.
    cons = {}
    for r in rows:
        side = 1 if r["kind"] in ("편입", "증가") else -1
        k = (r["market"], r["name"])
        c = cons.setdefault(k, {"market": r["market"], "name": r["name"], "ticker": r["ticker"], "buy": set(), "sell": set(), "ret1d": r["ret1d"]})
        c["buy" if side > 0 else "sell"].add(r["etf_name"])
    consensus = sorted(({**c, "buy": sorted(c["buy"]), "sell": sorted(c["sell"])} for c in cons.values()),
                       key=lambda c: -abs(len(c["buy"]) - len(c["sell"])))
    return {"funds": funds_out, "changes": sorted(rows, key=lambda r: (r["date"], r["etf_name"]), reverse=True),
            "consensus": [c for c in consensus if len(c["buy"]) + len(c["sell"]) >= 2][:40], "days": days}


def holdings(etf: str) -> dict:
    latest, fl = store.read("etf_latest"), store.read("etf_funds")
    h = latest[latest["etf"] == etf] if len(latest) else latest
    m = dict(zip(fl["etf"], fl["market"])).get(etf, "KR") if len(fl) else "KR"
    rets = _returns()
    rows = [{"name": r.name, "ticker": r.ticker, "shares": _f(r.shares), "weight": _f(r.weight),
             "ret1d": rets.get(_key(m, r.name, r.ticker))} for r in h.sort_values("weight", ascending=False).itertuples()]
    ch = store.read("etf_changes")
    ch = ch[ch["etf"] == etf] if len(ch) else ch
    hist = [{"date": str(r.date), "name": r.name, "kind": r.kind, "shares_prev": _f(r.shares_prev), "shares": _f(r.shares),
             "weight_prev": _f(r.weight_prev), "weight": _f(r.weight)} for r in ch.sort_values("date", ascending=False).itertuples()]
    return {"etf": etf, "date": str(max(h["date"])) if len(h) else None, "holdings": rows, "history": hist}


def _f(v) -> float | None:
    return None if v is None or pd.isna(v) else float(v)
