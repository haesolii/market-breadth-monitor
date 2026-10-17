"""Data-quality checks and cross-source / manual-reference comparisons."""
import datetime as dt

import duckdb
import pandas as pd

from . import store, universes
from .market_calendar import latest_complete_session, sessions

# Columns a user can enter from the original Market Monitor / TC2000 for comparison.
REF_METRICS = ["bull", "bear", "up4", "down4", "ratio5", "ratio10", "quarter_up25", "quarter_down25",
               "month_up25", "month_down25", "month_up50", "month_down50", "day34_up13", "day34_down13", "t2108"]
SUSPICIOUS = r"(?i)\b(trust|fund|etf|etn|warrant|preferred|depositary|units?|notes?|partners|L\.?P\.?)\b"


def _missing_sessions(dates: list[dt.date], cal: str = "NYSE") -> list[str]:
    if not dates:
        return []
    have = set(dates)
    return [str(d) for d in sessions(min(dates), max(dates), cal) if d not in have]


def bars_checks(source: str) -> dict | None:
    cfg = universes.UNIVERSES.get(source, {})
    p = store.path(cfg["bars"]) if cfg and not cfg.get("derived_from") else None
    if source == "massive":
        from .collectors import massive
        if not massive.CACHE.exists() or not any(massive.CACHE.glob("*.parquet")):
            return None
        rel = f"read_parquet('{(massive.CACHE / '*.parquet').as_posix()}')"
    elif p is not None and p.exists():
        rel = f"read_parquet('{p.as_posix()}')"
    else:
        return None
    con = duckdb.connect()
    try:
        q = lambda s: con.sql(s.replace("BARS", rel)).df()  # noqa: E731
        summary = q("""SELECT count(*) AS rows, count(DISTINCT ticker) AS tickers,
                        min(date) AS first_date, max(date) AS last_date,
                        sum((close <= 0 OR close IS NULL)::INT) AS bad_close,
                        sum((volume IS NULL OR volume <= 0)::INT) AS zero_volume FROM BARS""").iloc[0]
        dups = int(q("SELECT count(*) AS n FROM (SELECT ticker, date FROM BARS GROUP BY 1,2 HAVING count(*) > 1)").n[0])
        last = summary["last_date"]
        latest = q(f"""SELECT count(*) AS tickers, sum((volume IS NULL OR volume <= 0)::INT) AS zero_volume
                       FROM BARS WHERE date = DATE '{pd.Timestamp(last).date()}'""").iloc[0]
        extreme = q("""WITH x AS (SELECT ticker, date, close, LAG(close) OVER (PARTITION BY ticker ORDER BY date) AS c1 FROM BARS)
                       SELECT ticker, date, c1, close, round(100*(close/c1-1),1) AS pct FROM x
                       WHERE c1 > 0 AND (close / c1 > 4 OR close / c1 < 0.2)
                       ORDER BY date DESC LIMIT 50""")
        per_day = q("SELECT date, count(*) AS n FROM BARS GROUP BY 1 ORDER BY 1")
    finally:
        con.close()
    per_day["date"] = pd.to_datetime(per_day["date"]).dt.date
    med = per_day["n"].rolling(20, min_periods=5).median()
    thin = per_day[per_day["n"] < 0.8 * med]
    extreme["date"] = extreme["date"].astype(str)
    return {
        "summary": {k: (str(pd.Timestamp(v).date()) if "date" in k else int(v)) for k, v in summary.items()},
        "duplicate_ticker_dates": dups,
        "latest_day": {"date": str(pd.Timestamp(last).date()), "tickers": int(latest["tickers"]), "zero_volume": int(latest["zero_volume"] or 0)},
        "missing_sessions": _missing_sessions(per_day["date"].tolist(), universes.cal_of(source)),
        "thin_sessions": [{"date": str(r.date), "tickers": int(r.n)} for r in thin.itertuples()][-30:],
        "extreme_moves": extreme.to_dict("records"),
    }


def universe_checks(source: str) -> dict | None:
    u = store.read(f"universe_{source}")
    if u.empty:
        return None
    inc = u[u["excluded_reason"] == ""] if "excluded_reason" in u else u
    sus = inc[inc["name"].fillna("").str.contains(SUSPICIOUS)]
    out = {
        "total_symbols": int(len(u)), "included": int(len(inc)),
        "duplicate_tickers": int(u["ticker"].duplicated().sum()),
        "by_exchange": inc["exchange"].value_counts().to_dict(),
        "suspicious_names_included": sus[["ticker", "name", "exchange"]].head(40).to_dict("records"),
        "suspicious_count": int(len(sus)),
    }
    if "excluded_reason" in u:
        out["excluded_by_reason"] = u.loc[u["excluded_reason"] != "", "excluded_reason"].value_counts().to_dict()
    if "listed" in u:
        out["delisted_tracked"] = int((~u["listed"].astype(bool)).sum())
    if "active" in u:
        out["inactive_included"] = int((~u["active"].astype(bool)).sum())
    return out


def report() -> dict:
    b = store.read("breadth20")
    mm = store.read("market_monitor_daily")
    sources = {}
    for src in sorted(b["source"].unique()) if len(b) else []:
        cal = universes.cal_of(src)
        target = latest_complete_session(cal=cal)
        s = b[b["source"] == src]
        m = mm[mm["source"] == src] if len(mm) else mm
        sources[src] = {
            "first_date": str(s["date"].min()), "latest_date": str(s["date"].max()),
            "expected_session": str(target), "lag_sessions": len(sessions(s["date"].max(), target, cal)) - 1,
            "missing_sessions": _missing_sessions(s["date"].tolist(), cal)[:100],
            "mm_latest_date": str(m["date"].max()) if len(m) else None,
            "bars": bars_checks(src),
            "universe": universe_checks(src) if src in ("massive", *universes.UNIVERSES) and
            not universes.UNIVERSES.get(src, {}).get("derived_from") else None,
        }
    return {"expected_session": str(latest_complete_session()),
            "sources": sources, "source_diff": source_diff(b)}


def source_diff(b: pd.DataFrame, last_n: int = 250) -> dict:
    """Day-by-day 20% bull/bear differences between every pair of sources."""
    if b.empty or b["source"].nunique() < 2:
        return {}
    w = b.pivot_table(index="date", columns="source", values=["bull", "bear"])
    out = {}
    srcs = sorted(b["source"].unique())
    for i, a in enumerate(srcs):
        for c in srcs[i + 1:]:
            pair = {}
            for metric in ("bull", "bear"):
                d = w[metric][[a, c]].dropna().tail(last_n)
                if d.empty:
                    continue
                diff = d[a] - d[c]
                pair[metric] = {"days": int(len(d)), "mean_abs_diff": round(float(diff.abs().mean()), 2),
                                "corr": round(float(d[a].corr(d[c])), 3) if len(d) > 2 else None,
                                "exact_match_pct": round(float((diff == 0).mean() * 100), 1),
                                "recent": [{"date": str(k), a: int(r[a]), c: int(r[c])} for k, r in d.tail(15).iterrows()]}
            out[f"{a} vs {c}"] = pair
    return out


def compare_reference() -> list[dict]:
    """Manual reference values (from TC2000 / the original sheet) vs each computed source."""
    ref = store.read("manual_reference")
    if ref.empty:
        return []
    b = store.read("breadth20")
    mm = store.read("market_monitor_daily")
    rows = []
    for r in ref.itertuples():
        row = {"date": str(r.date), "metric": r.metric, "reference": r.value, "note": r.note, "by_source": {}}
        tab = b if r.metric in ("bull", "bear") else mm
        if len(tab):
            hit = tab[(tab["date"] == r.date)]
            for s in hit.itertuples():
                v = getattr(s, r.metric, None)
                if v is not None and not pd.isna(v):
                    row["by_source"][s.source] = {"value": float(v), "diff": round(float(v) - r.value, 2)}
        rows.append(row)
    return rows
