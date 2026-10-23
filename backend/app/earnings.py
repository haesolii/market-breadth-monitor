"""US earnings calendar (Nasdaq): reported vs consensus EPS and the stock's reaction.

Fetched per date: BACKFILL_DAYS back on the first run, then the last REFETCH_DAYS (actuals
arrive after the report) and the next AHEAD_DAYS (schedule). Past dates come back without the
report time, so the time seen while a date was still upcoming is kept.
Reaction, from the stored US daily bars:
  pre-market      close(D)   / close(D-1)
  after-hours     close(D+1) / close(D)
  time unknown    close(D+1) / close(D-1)   (both sessions; labelled as a 2-day reaction)
"""
import datetime as dt
import time as _time

import numpy as np
import pandas as pd

from . import store
from .collectors import http_session

API = "https://api.nasdaq.com/api/calendar/earnings"
BACKFILL_DAYS, REFETCH_DAYS, AHEAD_DAYS = 120, 7, 21
BROWSER_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"
TIME = {"time-pre-market": "pre", "time-after-hours": "after"}
COLS = ["date", "symbol", "name", "time", "eps", "eps_forecast", "surprise", "n_est", "mcap", "quarter"]


def _money(x) -> float | None:
    """'$1.99' / '($0.12)' / 'N/A' -> float."""
    if not isinstance(x, str) or not any(c.isdigit() for c in x):
        return None
    neg = x.strip().startswith("(") or x.strip().startswith("-")
    v = float(x.replace("$", "").replace(",", "").strip("()- "))
    return -v if neg else v


def parse(d: dt.date, rows: list[dict]) -> pd.DataFrame:
    out = []
    for r in rows:
        eps, fc = _money(r.get("eps")), _money(r.get("epsForecast"))
        out.append({"date": d, "symbol": r["symbol"].strip(), "name": (r.get("name") or "").strip(),
                    "time": TIME.get(r.get("time"), ""), "eps": eps, "eps_forecast": fc,
                    "surprise": (eps - fc) / abs(fc) * 100 if eps is not None and fc else None,
                    "n_est": _money(r.get("noOfEsts")), "mcap": _money(r.get("marketCap")),
                    "quarter": r.get("fiscalQuarterEnding") or ""})
    return pd.DataFrame(out, columns=COLS)


def fetch(dates: list[dt.date]) -> pd.DataFrame:
    s = http_session()
    s.headers.update({"User-Agent": BROWSER_UA, "Accept": "application/json"})
    frames = []
    for d in dates:
        r = s.get(API, params={"date": d.isoformat()}, timeout=30)
        r.raise_for_status()
        frames.append(parse(d, ((r.json().get("data") or {}).get("rows")) or []))
        _time.sleep(0.2)  # polite: one public endpoint, ~150 calls on the first run
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=COLS)


def react(ev: pd.DataFrame, bars: pd.DataFrame) -> pd.DataFrame:
    """Add react (% move around the report), react_days (1 or 2) and ret_since (% to the latest close)."""
    ev = ev.copy()
    ev["react"], ev["react_days"], ev["ret_since"] = np.nan, np.nan, np.nan
    b = bars.sort_values(["ticker", "date"])
    for sym, g in ev.groupby("symbol"):
        px = b[b["ticker"] == sym]
        if px.empty:
            continue
        d, c = px["date"].to_numpy(), px["close"].to_numpy()
        n = len(d)
        on = d.searchsorted(g["date"].to_numpy(), side="left")    # first session on/after the report date
        same = (on < n) & (d[np.minimum(on, n - 1)] == g["date"].to_numpy())
        for k, idx, t, is_same in zip(g.index, on, g["time"], same):
            if not is_same:
                continue
            a, z = {"pre": (idx - 1, idx), "after": (idx, idx + 1)}.get(t, (idx - 1, idx + 1))
            if a >= 0 and z < n:
                ev.loc[k, ["react", "react_days", "ret_since"]] = [(c[z] / c[a] - 1) * 100, z - a, (c[-1] / c[a] - 1) * 100]
    return ev


def refresh() -> dict:
    old = store.read("earnings")
    today = dt.date.today()
    start = today - dt.timedelta(days=REFETCH_DAYS if len(old) else BACKFILL_DAYS)
    dates = [start + dt.timedelta(days=i) for i in range((today - start).days + AHEAD_DAYS + 1)]
    new = fetch([d for d in dates if d.weekday() < 5])
    if len(old):
        known = old[old["time"] != ""].set_index(["date", "symbol"])["time"]
        idx = pd.MultiIndex.from_frame(new[["date", "symbol"]])
        new["time"] = new["time"].where(new["time"] != "", known.reindex(idx).fillna("").to_numpy())
        # a date re-fetched replaces its old rows (rescheduled names move to their new date)
        old = old[~old["date"].isin(set(dates))]
    ev = pd.concat([old[COLS] if len(old) else None, new], ignore_index=True)
    ev = ev[ev["date"] >= today - dt.timedelta(days=365)]
    path = store.path("bars_yahoo")
    since = min(ev["date"]) - dt.timedelta(days=7)
    bars = store.sql(f"SELECT date, ticker, close FROM read_parquet('{path.as_posix()}') WHERE date >= DATE '{since}'") \
        if path.exists() else pd.DataFrame(columns=["date", "ticker", "close"])
    bars["date"] = pd.to_datetime(bars["date"]).dt.date
    out = react(ev, bars)
    store.write("earnings", out.sort_values(["date", "mcap"], ascending=[True, False]).reset_index(drop=True))
    return {"latest_date": str(min(today, max(out["date"]))), "fetched_dates": len(dates), "rows": len(out),
            "upcoming": int((out["date"] > today).sum())}


def view(back: int = 7, ahead: int = 14, min_cap: float = 2e9) -> dict:
    df = store.read("earnings")
    if df.empty:
        return {"reported": [], "upcoming": []}
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"]).dt.date
    today = dt.date.today()
    big = df[df["mcap"].fillna(0) >= min_cap]
    rep = big[(big["date"] >= today - dt.timedelta(days=back)) & (big["date"] <= today) & big["eps"].notna()]
    up = big[(big["date"] >= today) & (big["date"] <= today + dt.timedelta(days=ahead)) & big["eps"].isna()]

    def rows(x: pd.DataFrame) -> list[dict]:
        x = x.assign(date=x["date"].astype(str))
        return x.astype(object).where(x.notna(), None).to_dict("records")
    return {"reported": rows(rep.sort_values(["date", "mcap"], ascending=[False, False])),
            "upcoming": rows(up.sort_values(["date", "mcap"], ascending=[True, False])), "min_cap": min_cap}
