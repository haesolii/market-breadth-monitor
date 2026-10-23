"""Qullamaggie-style market view: is the market trending, and are the momentum leaders working?

Per market, from the stored daily closes (DuckDB windows over each ticker's series):
  breadth  — per day: % of eligible stocks above their 10 / 20 / 50-day average, new 52-week highs
             and lows, and the leaders' health: the top LEADER_PCT % by 3-month return among liquid
             stocks that day, and how many of them are above their 10 / 20-day average
  list     — today's leaders: top LEADER_PCT % by 1 / 3 / 6-month return among liquid stocks, with
             the average daily move, distance from the 52-week high and their averages
Index trend (read side): the benchmark against its 10 / 20-day averages.

ADR = 20-day mean of (high / low - 1) once the bars carry high / low (collected since 2026-10-23;
the monthly incremental fetch fills the last 20 sessions on the first run); before that, or for a
stock with fewer than 15 such days, the mean absolute close-to-close move (adr_true = False,
roughly 0.6-0.7x the high-low ADR).
EP (episodic pivot) candidates: liquid stocks that today gapped up >= EP_GAP % (or closed up that
much when the open is unknown) on >= EP_VOL x their 50-day average volume.
ponytail: Korean corporate-action breaks are not cut here (rare; they can blip one stock's averages).
"""
import datetime as dt

import pandas as pd

from . import store, universes

LEADER_PCT = 2.0
EP_GAP, EP_VOL = 8.0, 2.0
HISTORY = 260  # sessions of breadth kept
# market -> (bars table, universe table, source for params, leader liquidity: 20-day avg turnover)
MARKETS = {"yahoo": ("bars_yahoo", "universe_yahoo", "yahoo", 20e6), "nasdaq": ("bars_yahoo", "universe_yahoo", "yahoo", 20e6),
           "kospi": ("bars_kospi", "universe_kospi", "kospi", 3e9), "kosdaq": ("bars_kosdaq", "universe_kosdaq", "kosdaq", 3e9),
           "crypto": ("bars_crypto", "universe_crypto", "crypto", 20e6)}
INDEX = {"yahoo": "^GSPC", "nasdaq": "^IXIC", "kospi": "^KS11", "kosdaq": "^KQ11", "crypto": "BTC-USD"}


def _frame(market: str) -> pd.DataFrame:
    bars_t, uni_t, src, _ = MARKETS[market]
    if not store.path(bars_t).exists():
        return pd.DataFrame()
    u = store.read(uni_t)
    u = u[(u["excluded_reason"] == "") & u["listed"]]
    if market == "nasdaq":
        u = u[u["exchange"] == "NASDAQ"]
    since = dt.date.today() - dt.timedelta(days=int(HISTORY * 1.5) + 400)  # history + a 252-session lookback
    p = universes.params_of(src)
    rel = f"read_parquet('{store.path(bars_t).as_posix()}')"
    cols = set(store.sql(f"DESCRIBE SELECT * FROM {rel}")["column_name"])
    ohl = "open, high, low" if {"open", "high", "low"} <= cols else "NULL::DOUBLE AS open, NULL::DOUBLE AS high, NULL::DOUBLE AS low"
    df = store.sql(f"""
        WITH b AS (
            SELECT date, ticker, close, volume, {ohl}, close / lag(close) OVER w - 1 AS r1,
                   CASE WHEN high > 0 AND low > 0 THEN (high / low - 1) * 100 END AS hl
            FROM {rel}
            WHERE date >= DATE '{since}' AND close > 0
            WINDOW w AS (PARTITION BY ticker ORDER BY date))
        SELECT date, ticker, close,
               avg(close) OVER (w ROWS 9 PRECEDING) AS ma10, count(*) OVER (w ROWS 9 PRECEDING) AS n10,
               avg(close) OVER (w ROWS 19 PRECEDING) AS ma20,
               avg(close) OVER (w ROWS 49 PRECEDING) AS ma50, count(*) OVER (w ROWS 49 PRECEDING) AS n50,
               max(close) OVER (w ROWS 251 PRECEDING) AS hi252, min(close) OVER (w ROWS 251 PRECEDING) AS lo252,
               count(*) OVER (w ROWS 251 PRECEDING) AS n252,
               avg(close * volume) OVER (w ROWS 19 PRECEDING) AS dvol,
               avg(abs(r1)) OVER (w ROWS 19 PRECEDING) * 100 AS adr_cc,
               avg(hl) OVER (w ROWS 19 PRECEDING) AS adr_hl, count(hl) OVER (w ROWS 19 PRECEDING) AS n_hl,
               r1 * 100 AS r1, (open / lag(close) OVER w - 1) * 100 AS gap,
               volume / avg(volume) OVER (w ROWS BETWEEN 50 PRECEDING AND 1 PRECEDING) AS vratio,
               close > max(close) OVER (w ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING) AS breakout,
               (close / lag(close, 21) OVER w - 1) * 100 AS r21,
               (close / lag(close, 63) OVER w - 1) * 100 AS r63,
               (close / lag(close, 126) OVER w - 1) * 100 AS r126
        FROM b WINDOW w AS (PARTITION BY ticker ORDER BY date)""")
    df = df[df["ticker"].isin(set(u["ticker"]))]
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df["adr_true"] = df["n_hl"] >= 15
    df["adr"] = df["adr_hl"].where(df["adr_true"], df["adr_cc"])
    df["ok"] = (df["close"] >= p.price_floor) & (df["dvol"] >= p.min_dollar_vol) & (df["n10"] >= 10)
    df["liquid"] = df["ok"] & (df["dvol"] >= MARKETS[market][3])
    return df


def breadth(df: pd.DataFrame) -> pd.DataFrame:
    e = df[df["ok"]].copy()
    e["a10"], e["a20"] = e["close"] > e["ma10"], e["close"] > e["ma20"]
    e["a50"] = (e["close"] > e["ma50"]).where(e["n50"] >= 50)
    full = (e["n252"] >= 252) & (e["hi252"] > e["lo252"])  # a price unchanged for a year is neither
    e["hi"], e["lo"] = (e["close"] >= e["hi252"]) & full, (e["close"] <= e["lo252"]) & full
    g = e.groupby("date")
    out = pd.DataFrame({"n": g.size(), "above10": g["a10"].mean() * 100, "above20": g["a20"].mean() * 100,
                        "above50": g["a50"].mean() * 100, "new_high": g["hi"].sum(), "new_low": g["lo"].sum()})
    liq = e[e["liquid"] & e["r63"].notna()].copy()
    liq["pct"] = liq.groupby("date")["r63"].rank(pct=True) * 100
    lead = liq[liq["pct"] > 100 - LEADER_PCT].groupby("date")
    out = out.join(pd.DataFrame({"leaders": lead.size(), "leaders_above10": lead["a10"].mean() * 100,
                                 "leaders_above20": lead["a20"].mean() * 100, "leaders_r21": lead["r21"].median()}))
    return out.reset_index().tail(HISTORY)


def leaders(df: pd.DataFrame) -> pd.DataFrame:
    last = df[df["date"] == df["date"].max()]
    liq = last[last["liquid"]].copy()
    hit = pd.Series(False, index=liq.index)
    for c in ("r21", "r63", "r126"):
        hit |= liq[c].rank(pct=True) * 100 > 100 - LEADER_PCT
    out = liq[hit].copy()
    out["off_high"] = (out["close"] / out["hi252"] - 1) * 100
    for n in (10, 20, 50):
        out[f"above{n}"] = out["close"] > out[f"ma{n}"]
    keep = ["ticker", "date", "close", "r1", "r21", "r63", "r126", "adr", "adr_true", "dvol", "off_high", "above10", "above20", "above50",
            "breakout", "gap", "vratio"]
    move = liq["gap"].fillna(liq["r1"])
    ep = liq[(move >= EP_GAP) & (liq["vratio"] >= EP_VOL)].copy()
    ep["off_high"] = (ep["close"] / ep["hi252"] - 1) * 100
    for n in (10, 20, 50):
        ep[f"above{n}"] = ep["close"] > ep[f"ma{n}"]
    return pd.concat([out[keep].assign(kind="leader"), ep[keep].assign(kind="ep")], ignore_index=True)


def refresh() -> dict:
    hist, lists, counts = [], [], {}
    for m in MARKETS:
        df = _frame(m)
        if df.empty:
            continue
        hist.append(breadth(df).assign(market=m))
        lists.append(leaders(df).assign(market=m))
        counts[m] = len(lists[-1])
    if not hist:
        raise RuntimeError("no bars")
    b = pd.concat(hist, ignore_index=True)
    store.write("leaders_breadth", b)
    store.write("leaders_list", pd.concat(lists, ignore_index=True))
    return {"latest_date": str(b["date"].max()), **counts}


# ---- read side ----------------------------------------------------------------------
def trend(closes: pd.Series) -> dict | None:
    """Index vs its 10 / 20-day averages: 강세 = above both with the 10-day rising and above the
    20-day; 약세 = below the 20-day with the 10-day under it; otherwise 중립."""
    c = closes.dropna()
    if len(c) < 25:
        return None
    ma10, ma20 = c.rolling(10).mean(), c.rolling(20).mean()
    last, a, b = float(c.iloc[-1]), float(ma10.iloc[-1]), float(ma20.iloc[-1])
    rising = a > float(ma10.iloc[-6])
    state = "강세" if last > a > b and rising else "약세" if last < b and a < b else "중립"
    return {"close": last, "ma10": a, "ma20": b, "ma10_rising": rising, "state": state,
            "dist10": (last / a - 1) * 100, "dist20": (last / b - 1) * 100}


def _kind(lst: pd.DataFrame, kind: str) -> pd.DataFrame:
    d = lst[lst["kind"] == kind] if "kind" in lst else (lst if kind == "leader" else lst.iloc[0:0])
    return d.drop(columns=[c for c in ("market", "kind") if c in d]).assign(date=d["date"].astype(str))


def _sort(d: pd.DataFrame, col: str) -> pd.DataFrame:
    return d.sort_values(col, ascending=False) if col in d else d  # a list published by an older version lacks newer columns


def view(market: str) -> dict:
    b, lst, idx = store.read("leaders_breadth"), store.read("leaders_list"), store.read("indices")
    b = b[b["market"] == market].sort_values("date") if len(b) else b
    lst = lst[lst["market"] == market] if len(lst) else lst
    sym = INDEX[market]
    px = idx[idx["symbol"] == sym].sort_values("date") if len(idx) else idx
    sm = store.read("sector_map")
    if len(lst) and len(sm):
        src = "yahoo" if market == "nasdaq" else market
        lst = lst.merge(sm[sm["market"] == src][["ticker", "name", "sector"]], on="ticker", how="left")
    rows = lambda d: d.astype(object).where(d.notna(), None).to_dict("records")  # noqa: E731
    return {"market": market, "index": sym, "trend": trend(px.set_index("date")["close"]) if len(px) else None,
            "index_closes": [[str(d), float(c)] for d, c in zip(px["date"].tail(HISTORY), px["close"].tail(HISTORY))],
            "breadth": rows(b.drop(columns="market").assign(date=b["date"].astype(str))) if len(b) else [],
            "leaders": rows(_sort(_kind(lst, "leader"), "r63")) if len(lst) else [],
            "ep": rows(_sort(_kind(lst, "ep"), "vratio")) if len(lst) else [],
            "leader_pct": LEADER_PCT}
