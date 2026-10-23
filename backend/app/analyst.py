"""Korean broker company reports (Naver research): broker, stock, target price, rating and the
broker's own summary, plus how the stock reacted.

Collected incrementally (newest first until a known report), BACKFILL_DAYS on the first run.
Enrichment, recomputed on every refresh from the stored KRX daily bars:
  prev_goal / goal_chg — the same broker's previous target for the stock, % change
  react1d              — stock's close on the report date vs the session before (reports are
                         published before / during the session, so this is the day's reaction)
  ret_since            — latest close vs the close before the report
  upside               — target vs latest close
"""
import datetime as dt
import html
import re

import pandas as pd

from . import store
from .collectors import http_session

API = "https://stock.naver.com/api/stockSecurity/researches/v2/company"
BACKFILL_DAYS = 180
PAGE = 50  # API maximum
BROWSER_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"
COLS = ["nid", "date", "broker", "code", "name", "title", "summary", "goal", "opinion"]


def _text(h: str | None, limit: int = 900) -> str:
    t = re.sub(r"<br\s*/?>|</p>|</li>", "\n", h or "")
    t = html.unescape(re.sub(r"<[^>]+>", "", t))
    t = re.sub(r"\n\s*\n+", "\n", t).strip()
    return t[:limit] + ("…" if len(t) > limit else "")


def _num(x) -> float | None:
    try:
        return float(str(x).replace(",", ""))
    except (TypeError, ValueError):
        return None


def parse(items: list[dict]) -> pd.DataFrame:
    rows = [{"nid": int(x["nid"]), "date": dt.date.fromisoformat(x["writeDate"]), "broker": x.get("brokerName") or "",
             "code": x.get("itemCode") or "", "name": x.get("itemName") or "", "title": html.unescape(x.get("title") or ""),
             "summary": "", "goal": _num(x.get("goalPrice")) or None,  # the broker's text is not kept (copyright); facts only
             "opinion": (x.get("opinionText") or "").strip()} for x in items]
    return pd.DataFrame(rows, columns=COLS)


def fetch(known: set[int], since: dt.date) -> pd.DataFrame:
    s = http_session()
    s.headers["User-Agent"] = BROWSER_UA
    frames = []
    for index in range(2000):
        r = s.get(API, params={"index": index, "size": PAGE}, timeout=30)
        r.raise_for_status()
        j = r.json()
        df = parse(j.get("items") or [])
        frames.append(df)
        if df.empty or not j.get("hasNext") or df["nid"].isin(known).any() or min(df["date"]) < since:
            break
    out = pd.concat(frames, ignore_index=True)
    return out[out["date"] >= since]


def enrich(rep: pd.DataFrame, bars: pd.DataFrame) -> pd.DataFrame:
    """Add prev_goal / goal_chg / react1d / ret_since / last_close / upside (see module doc)."""
    rep = rep.sort_values(["code", "broker", "date", "nid"]).copy()
    g = rep.groupby(["code", "broker"])["goal"]
    rep["prev_goal"] = g.transform(lambda x: x.ffill().shift(1))  # a report without a target keeps the last one
    rep["goal_chg"] = (rep["goal"] / rep["prev_goal"] - 1) * 100
    for c in ("react1d", "ret_since", "last_close", "upside"):
        rep[c] = float("nan")
    if len(bars):
        b = bars.sort_values(["ticker", "date"])
        for code, g in rep.groupby("code"):
            px = b[b["ticker"] == code]
            if px.empty:
                continue
            d, c = px["date"].to_numpy(), px["close"].to_numpy()
            last = c[-1]
            i_on = d.searchsorted(g["date"].to_numpy(), side="right") - 1    # session on/before the report
            i_pre = d.searchsorted(g["date"].to_numpy(), side="left") - 1    # session before the report
            on_ok, pre_ok = i_on >= 0, i_pre >= 0
            same = on_ok & (d[i_on.clip(0)] == g["date"].to_numpy())          # report date was a session
            pre = pd.Series(c[i_pre.clip(0)], index=g.index).where(pre_ok)
            rep.loc[g.index, "react1d"] = ((pd.Series(c[i_on.clip(0)], index=g.index) / pre - 1) * 100).where(same)
            rep.loc[g.index, "ret_since"] = (last / pre - 1) * 100
            rep.loc[g.index, "last_close"] = last
            rep.loc[g.index, "upside"] = (g["goal"] / last - 1) * 100
    return rep.sort_values(["date", "nid"], ascending=False).reset_index(drop=True)


def _kr_bars(codes: set[str], since: dt.date) -> pd.DataFrame:
    frames = []
    for t in ("bars_kospi", "bars_kosdaq"):
        if store.path(t).exists():
            frames.append(store.sql(f"SELECT date, ticker, close FROM read_parquet('{store.path(t).as_posix()}') "
                                    f"WHERE date >= DATE '{since}'"))
    b = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["date", "ticker", "close"])
    b["date"] = pd.to_datetime(b["date"]).dt.date
    return b[b["ticker"].isin(codes)]


def refresh() -> dict:
    old = store.read("analyst_reports")
    since = dt.date.today() - dt.timedelta(days=BACKFILL_DAYS)
    new = fetch(set(old["nid"]) if len(old) else set(), since)
    raw = pd.concat([old[COLS] if len(old) else None, new], ignore_index=True).drop_duplicates("nid", keep="last")
    raw = raw[raw["date"] >= since - dt.timedelta(days=BACKFILL_DAYS)]  # keep ~a year
    raw["summary"] = ""  # drop summaries stored before they were left out
    out = enrich(raw, _kr_bars(set(raw["code"]), min(raw["date"]) - dt.timedelta(days=10)))
    store.write("analyst_reports", out)
    return {"latest_date": str(out["date"].max()), "new": len(new), "reports": len(out)}


# ---- read side ----------------------------------------------------------------------
def _rows(df: pd.DataFrame) -> list[dict]:
    df = df.drop(columns=["summary"], errors="ignore").copy()  # never served: the brokers' text
    if "date" in df:
        df["date"] = df["date"].astype(str)
    return df.astype(object).where(df.notna(), None).to_dict("records")


def feed(days: int = 7, q: str = "", kind: str = "all", broker: str = "") -> dict:
    df = store.read("analyst_reports")
    if df.empty:
        return {"rows": [], "brokers": [], "top_covered": [], "up": [], "down": []}
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"]).dt.date
    win = df[df["date"] >= max(df["date"]) - dt.timedelta(days=days)]
    if q:
        win = win[win["name"].str.contains(q, case=False, regex=False) | (win["code"] == q)
                  | win["title"].str.contains(q, case=False, regex=False)]
    if broker:
        win = win[win["broker"] == broker]
    view = win[win["goal_chg"] > 0] if kind == "up" else win[win["goal_chg"] < 0] if kind == "down" else \
        win[win["prev_goal"].isna()] if kind == "new" else win
    cov = (win.groupby(["code", "name"]).agg(n=("nid", "size"), brokers=("broker", "nunique"), react=("react1d", "mean"),
                                             upside=("upside", "median"))
           .reset_index().sort_values(["n", "brokers"], ascending=False).head(20))
    moved = win.dropna(subset=["goal_chg"])
    return {"latest": str(max(df["date"])), "rows": _rows(view.head(500)), "brokers": sorted(df["broker"].unique().tolist()),
            "top_covered": _rows(cov), "up": _rows(moved.nlargest(10, "goal_chg")), "down": _rows(moved.nsmallest(10, "goal_chg"))}


def stock(code: str) -> dict:
    df = store.read("analyst_reports")
    df = df[df["code"] == code] if len(df) else df
    if df.empty:
        return {"code": code, "rows": [], "consensus": None}
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"]).dt.date
    recent = df[df["date"] >= max(df["date"]) - dt.timedelta(days=90)]
    latest = recent.sort_values("date").groupby("broker").tail(1).dropna(subset=["goal"])  # each broker's current target
    cons = None if latest.empty else {"brokers": int(len(latest)), "mean": float(latest["goal"].mean()), "high": float(latest["goal"].max()),
                                      "low": float(latest["goal"].min()), "last_close": _f(df["last_close"].iloc[0]),
                                      "upside": _f((latest["goal"].mean() / df["last_close"].iloc[0] - 1) * 100)}
    return {"code": code, "name": df["name"].iloc[0], "rows": _rows(df.sort_values("date", ascending=False)), "consensus": cons}


def _f(v) -> float | None:
    return None if v is None or pd.isna(v) else float(v)
