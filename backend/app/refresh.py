"""Data refresh: collect -> validate -> compute -> upsert. Also the in-process
auto-refresh loop and a CLI (`python -m app.refresh`) for Windows Task Scheduler."""
import argparse
import datetime as dt
import threading
import time
import traceback

import pandas as pd

from . import analyst, calendar_, dart, earnings, etf, flows, indicators, leaders, macro, sectors, store, term, universes, world
from .collectors import massive, public, yahoo
from .config import CRYPTO_SCANNER, DART_API_KEY, KR_SCANNER, MASSIVE_API_KEY, MASSIVE_START, REFRESH_INTERVAL_MIN, YAHOO_HISTORY, YAHOO_SCANNER
from .market_calendar import CALENDARS, latest_complete_session, live_session, session_elapsed, sessions, volume_share

_busy = threading.Lock()


def enabled_sources() -> list[str]:
    return (["public_repo", "indices", "macro"] + (["yahoo"] if YAHOO_SCANNER else [])
            + (["kospi", "kosdaq"] if KR_SCANNER else []) + (["crypto"] if CRYPTO_SCANNER else [])
            + (["massive"] if MASSIVE_API_KEY else []) + ["sectors", "etf", "analyst", "earnings"]
            + (["flows"] if KR_SCANNER else []) + (["dart"] if DART_API_KEY else []) + ["leaders", "calendar", "term"])


# Sources with their own table (the rest are breadth sources, dated by breadth20).
OWN_TABLE = {"indices": "indices", "macro": "macro", "sectors": "sector_map", "etf": "etf_latest",
             "analyst": "analyst_reports", "earnings": "earnings", "flows": "kr_flow", "dart": "dart_prelim",
             "leaders": "leaders_breadth", "calendar": "econ_calendar", "term": "vol_index"}


def latest_date(source: str):
    if source in OWN_TABLE:
        df = store.read(OWN_TABLE[source])
    else:
        df = store.read("breadth20")
        df = df[df["source"] == source] if len(df) else df
    return max(df["date"]) if len(df) else None


def _save_computed(source: str, bars: pd.DataFrame) -> dict:
    b20, mm = indicators.compute(bars, universes.params_of(source))
    now = store.now_utc()
    b20 = b20.assign(source=source, updated_at=now)
    mm = mm.assign(source=source, updated_at=now)
    store.replace_source("breadth20", source, b20)
    store.replace_source("market_monitor_daily", source, mm)
    return {"sessions": len(b20), "first_date": str(b20["date"].min()), "latest_date": str(b20["date"].max())}


def _paced(bars: pd.DataFrame, cal: str) -> pd.DataFrame:
    """While today's session is live, project today's partial volume to a full day (typical intraday
    volume curve), so 'volume >= min' and 'volume > yesterday' compare like with like (stored bars stay raw)."""
    today = live_session(cal=cal)
    frac = session_elapsed(cal=cal)
    if not today or frac >= 1 or bars.empty:
        return bars
    b = bars.copy()
    on = pd.to_datetime(b["date"]).dt.date == today
    b.loc[on, "volume"] = b.loc[on, "volume"] / volume_share(frac)
    return b


def _clean_bars(bars: pd.DataFrame, cal: str = "NYSE", live: bool = False) -> pd.DataFrame:
    """Keep only completed sessions of the exchange calendar (plus today's in-progress
    session when live); one row per (ticker, date)."""
    last = (live and live_session(cal=cal)) or latest_complete_session(cal=cal)
    valid = set(sessions(min(bars["date"]), last, cal))
    bars = bars[bars["date"].isin(valid)]
    return bars.drop_duplicates(["ticker", "date"], keep="last").sort_values(["ticker", "date"]).reset_index(drop=True)


# ---- per-source refreshers ----------------------------------------------------
def refresh_public() -> dict:
    df, st = public.fetch()
    old = store.read("breadth20")
    n_old = int((old["source"] == "public_repo").sum()) if len(old) else 0
    if n_old and len(df) < 0.9 * n_old:
        raise RuntimeError(f"Upstream series shrank ({len(df)} < {n_old}); keeping existing data")
    store.upsert("breadth20", df.assign(source="public_repo", updated_at=store.now_utc()), ["source", "date"])
    return {"latest_date": str(df["date"].max()), "first_date": str(df["date"].min()), "rows": len(df),
            "upstream_status": st}


def refresh_universe(name: str, live: bool = False) -> dict:
    """Yahoo-priced universe (US / KOSPI / KOSDAQ): update the listing, fetch new
    tickers in full and known tickers for the last month, then recompute.
    live: keep today's in-progress bar (provisional values, replaced after the close)."""
    cfg = universes.UNIVERSES[name]
    today = dt.date.today().isoformat()
    old_u = store.read(f"universe_{name}")
    if len(old_u) and old_u["last_seen"].max() == today:
        u = old_u  # listing already updated today (intraday runs every few minutes)
    else:
        u = cfg["load"]()
        u = u.assign(listed=u["listed"] if "listed" in u else True, last_seen=today)
        if len(old_u):
            gone = old_u[~old_u["ticker"].isin(u["ticker"])].assign(listed=False)
            u = pd.concat([u, gone], ignore_index=True)
        store.write(f"universe_{name}", u)
    keep = u[(u["excluded_reason"] == "") & u["listed"]]

    old = store.read(cfg["bars"])
    have = set(old["ticker"]) if len(old) else set()
    # Delisted names with downloadable history (crypto) are fetched once in full, never incrementally.
    hist = u[u["excluded_reason"] == ""] if cfg.get("delisted_history") else keep
    full = {t: y for t, y in zip(hist["ticker"], hist["yahoo"]) if t not in have}
    inc = {t: y for t, y in zip(keep["ticker"], keep["yahoo"]) if t in have}

    fetch = cfg.get("fetch", yahoo.fetch)
    b_full, _, f1 = fetch(full, YAHOO_HISTORY) if full else (pd.DataFrame(), [], [])
    b_inc, split_t, f2 = fetch(inc, "1mo") if inc else (pd.DataFrame(), [], [])
    if inc and b_inc["ticker"].nunique() < 0.5 * len(inc):
        raise RuntimeError(f"Yahoo returned only {b_inc['ticker'].nunique()}/{len(inc)} tickers; keeping existing data")
    # A split inside the window means older stored bars are on the old scale -> refetch full history.
    b_split, _, f3 = fetch({t: inc[t] for t in split_t}, YAHOO_HISTORY) if split_t else (pd.DataFrame(), [], [])

    replaced = set(b_split["ticker"]) if len(b_split) else set()
    parts = [old[~old["ticker"].isin(replaced)]] if len(old) else []
    parts += [b for b in (b_inc, b_full, b_split) if len(b)]
    bars = pd.concat(parts, ignore_index=True)
    bars["date"] = pd.to_datetime(bars["date"]).dt.date
    bars = _clean_bars(bars, cfg["cal"], live)
    store.write(cfg["bars"], bars)

    failed = f1 + f2 + f3
    if failed:
        store.log("warn", name, f"{len(failed)} tickers failed, e.g. {failed[:5]}")
    included = u[u["excluded_reason"] == ""]
    calc = _paced(bars, cfg["cal"]) if live else bars
    res = _save_computed(name, calc[calc["ticker"].isin(set(included["ticker"]))])
    # Yahoo publishes some tickers' close late; a thin last session stays provisional and is retried.
    cov = _coverage(bars)
    incomplete = live or cov < MIN_COVERAGE
    # Universes derived from this one's bars (e.g. Nasdaq composite basis from the US universe).
    for dname, d in universes.UNIVERSES.items():
        if d.get("derived_from") == name:
            sub = set(included.loc[included["exchange"] == d["exchange"], "ticker"])
            res[dname] = _save_computed(dname, calc[calc["ticker"].isin(sub)])
            store.set_source(dname, last_success=store.now_utc(), last_error=None, provisional=incomplete)
    return {**res, "tickers": int(bars["ticker"].nunique()), "failed": len(failed),
            "split_refetched": len(split_t), "new_tickers": len(full), "coverage": round(cov, 4),
            "provisional": incomplete}


MIN_COVERAGE = 0.99  # last session's tickers / previous session's tickers


def _coverage(bars: pd.DataFrame) -> float:
    """Share of the previous session's tickers that also have a bar on the last session."""
    days = sorted(bars["date"].unique())[-2:]
    if len(days) < 2:
        return 1.0
    prev, last = (set(bars.loc[bars["date"] == d, "ticker"]) for d in days)
    return len(prev & last) / len(prev) if prev else 1.0


def refresh_massive() -> dict:
    c = massive.Client()
    u_path_age = store.status()["sources"].get("massive", {}).get("universe_at")
    if u_path_age is None or store.read("universe_massive").empty or u_path_age[:10] != dt.date.today().isoformat():
        store.write("universe_massive", massive.universe(c))
        store.set_source("massive", universe_at=store.now_utc())
    todo = [d for d in sessions(dt.date.fromisoformat(MASSIVE_START), latest_complete_session())
            if not (massive.CACHE / f"{d}.parquet").exists()]
    skipped = []
    for i, d in enumerate(todo):
        try:
            if massive.grouped(c, d) is None:
                skipped.append(str(d))
        except massive.BeforeCoverage:
            skipped.append(str(d))  # older than the plan's history window
        store.set_source("massive", progress=f"{i + 1}/{len(todo)} sessions ({d})")
    u = store.read("universe_massive")
    bars = massive.cached_bars()
    bars = bars[bars["ticker"].isin(set(u["ticker"]))]
    bars = massive.adjust_for_splits(bars, massive.splits(c, MASSIVE_START))
    res = _save_computed("massive", _clean_bars(bars))
    return {**res, "skipped_sessions": len(skipped), "tickers": int(bars["ticker"].nunique())}


def scan_hits(source: str, date) -> pd.DataFrame:
    """Every stock meeting a scan condition on `date` (needs local bars)."""
    lo = date - dt.timedelta(days=130)  # >= 65 sessions of history for the quarter window
    if source in universes.UNIVERSES:
        cfg = universes.UNIVERSES[source]
        u = store.read(f"universe_{cfg.get('derived_from', source)}")
        u = u[u["excluded_reason"] == ""]
        if cfg.get("exchange"):
            u = u[u["exchange"] == cfg["exchange"]]
        rel = f"read_parquet('{store.path(cfg['bars']).as_posix()}')"
        bars = store.sql(f"SELECT date, ticker, close, volume FROM {rel} WHERE date BETWEEN DATE '{lo}' AND DATE '{date}'")
    else:
        u = store.read("universe_massive")
        bars = massive.cached_bars()
        bars = bars[(bars["date"] >= lo) & (bars["date"] <= date)]
        bars = massive.adjust_for_splits(bars, massive.splits(massive.Client(), str(lo)))
    bars = _paced(bars[bars["ticker"].isin(set(u["ticker"]))], universes.UNIVERSES.get(source, {}).get("cal", "NYSE"))
    hits = indicators.scan(bars, date, universes.params_of(source))
    return hits.merge(u[["ticker", "name", "exchange"]], on="ticker", how="left")


REFRESHERS = {"indices": world.refresh, "macro": macro.refresh, "public_repo": refresh_public,
              "yahoo": lambda: refresh_universe("yahoo"), "kospi": lambda: refresh_universe("kospi"),
              "kosdaq": lambda: refresh_universe("kosdaq"), "crypto": lambda: refresh_universe("crypto"),
              "massive": refresh_massive, "sectors": sectors.refresh,
              "etf": etf.refresh, "analyst": analyst.refresh, "earnings": earnings.refresh,
              "flows": flows.refresh, "dart": dart.refresh, "leaders": leaders.refresh, "calendar": calendar_.refresh, "term": term.refresh}
# Sources that can carry today's in-progress session (provisional until the close is final).
LIVE = {"indices": lambda: world.refresh(live=True), "sectors": sectors.refresh,
        "yahoo": lambda: refresh_universe("yahoo", True),
        "kospi": lambda: refresh_universe("kospi", True), "kosdaq": lambda: refresh_universe("kosdaq", True)}


def run(source: str, live: bool = False) -> dict:
    """Run one refresher with bookkeeping. Existing data is untouched on failure."""
    store.set_source(source, last_attempt=store.now_utc(), running=True)
    t0 = time.time()
    try:
        res = (LIVE if live else REFRESHERS)[source]()
        store.set_source(source, last_success=store.now_utc(), last_error=None, running=False,
                         provisional=bool(live or (isinstance(res, dict) and res.get("provisional"))),
                         result=res, seconds=round(time.time() - t0, 1), progress=None)
        store.log("info", source, f"refreshed in {time.time() - t0:.0f}s: { {k: v for k, v in res.items() if k != 'upstream_status'} }")
        return res
    except Exception as e:  # noqa: BLE001
        msg = f"{type(e).__name__}: {e}"
        store.set_source(source, last_error=msg, last_error_at=store.now_utc(), running=False)
        store.log("error", source, msg + "\n" + traceback.format_exc(limit=4))
        return {"error": msg}


def _provisional(source: str) -> bool:
    return bool(store.status()["sources"].get(source, {}).get("provisional"))


def refresh(sources: list[str] | None = None, only_stale: bool = False, live: bool = False) -> dict:
    """live: sources in LIVE whose market is in session (open .. final hour) are refreshed
    with today's in-progress bar; a provisional source counts as stale for only_stale."""
    if not _busy.acquire(blocking=False):
        return {"busy": True}
    try:
        out = {}
        for s in sources or enabled_sources():
            cals = CALENDARS if s in ALWAYS else [universes.cal_of(s)]  # indices / sectors: US or Korea open
            if live and s in LIVE and any(live_session(cal=c) for c in cals):
                out[s] = run(s, live=True)
                continue
            ld = latest_date(s)
            # indices span many exchanges (e.g. Korea closes before the NYSE session is final),
            # so they are never skipped as "not stale"; the download is a few seconds.
            # macro / ETF holdings / reports follow release schedules, not sessions: every PERIODIC[s].
            if only_stale and s in PERIODIC and s not in ALWAYS:
                if time.time() - _last_ok(s) < PERIODIC[s]:
                    continue
            elif (only_stale and s not in ALWAYS and ld is not None
                    and ld >= latest_complete_session(cal=universes.cal_of(s)) and not _provisional(s)):
                continue
            out[s] = run(s)
        return out
    finally:
        _busy.release()


def is_busy() -> bool:
    return _busy.locked()


def _behind(source: str) -> bool:
    ld = latest_date(source)
    return ld is None or ld < latest_complete_session(cal=universes.cal_of(source))


def _last_ok(source: str) -> float:
    ts = store.status()["sources"].get(source, {}).get("last_success")
    return dt.datetime.fromisoformat(ts).timestamp() if ts else 0.0


# Refreshed on a timer instead of against the trading calendar: world markets close at
# different times (indices) and macro series are released on their own schedules.
PERIODIC = {"indices": 3600, "macro": 1800, "sectors": 3600, "etf": 3 * 3600,
            "analyst": 3600, "earnings": 3600, "flows": 1800, "dart": 1800, "leaders": 1800, "calendar": 6 * 3600, "term": 1800}
# Recomputed on every pass (cheap; they follow several markets' sessions).
ALWAYS = {"indices", "sectors"}


def auto_loop(stop: threading.Event) -> None:
    """While the server runs: every REFRESH_INTERVAL_MIN, refresh any source whose
    latest date is behind the latest completed NYSE session. A source that did
    not advance (provider publishing lag) is retried after 60 min."""
    retry_at: dict[str, float] = {}
    while not stop.is_set():
        target = latest_complete_session()
        stale = [s for s in enabled_sources()
                 if s not in PERIODIC and _behind(s) and time.time() >= retry_at.get(s, 0)]
        stale += [s for s, every in PERIODIC.items() if time.time() - _last_ok(s) >= every]
        if any(s in universes.UNIVERSES for s in stale):
            stale += [x for x in ("sectors", "leaders") if x not in stale]  # new bars -> new returns / averages
        if stale:
            refresh(stale)
            for s in (x for x in stale if x not in PERIODIC):
                if _behind(s):
                    retry_at[s] = time.time() + 3600
        store.set_source("_scheduler", last_check=store.now_utc(), target_session=str(target))
        stop.wait(REFRESH_INTERVAL_MIN * 60)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Refresh breadth data (used by Task Scheduler).")
    ap.add_argument("--source", action="append", help="indices|macro|public_repo|yahoo|kospi|kosdaq|crypto|massive|sectors|etf|analyst|earnings|flows|dart|leaders|calendar|term (default: all enabled)")
    ap.add_argument("--only-stale", action="store_true")
    ap.add_argument("--live", action="store_true", help="include today's in-progress session for markets now open")
    a = ap.parse_args()
    print(refresh(a.source, a.only_stale, a.live))
