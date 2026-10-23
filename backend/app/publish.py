"""Copy computed results from the local Parquet store to Supabase (run by GitHub Actions).

    python -m app.publish --pull-config   # before refresh: user's indices list -> data/indices.json
    python -m app.publish                 # after refresh: result tables + status + validation + scans

Result tables are replaced as a whole inside one transaction, so the dashboard
never sees a half-written state. User-owned tables (manual_reference, the
indices list in kv) are never overwritten here.
"""
import argparse
import json

import pandas as pd

from . import refresh, remote, store, universes, validation, world
from .config import DATA

TABLES = ["breadth20", "market_monitor_daily", "indices", "macro", "sector_map"]
SCAN_SESSIONS = 20  # recent sessions of per-ticker scan results kept for the dashboard


def _scan_table() -> pd.DataFrame:
    b = store.read("breadth20")
    frames = []
    for src in universes.UNIVERSES:
        dates = sorted(b.loc[b["source"] == src, "date"])[-SCAN_SESSIONS:] if len(b) else []
        for d in dates:
            frames.append(refresh.scan_hits(src, d).assign(source=src))
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    out["date"] = pd.to_datetime(out["date"]).dt.date  # a date column, not a timestamp
    return out


def pull_config() -> None:
    items = remote.kv_get("indices_config")
    if items:
        (DATA / "indices.json").write_text(json.dumps(items, ensure_ascii=False, indent=1), "utf-8")
        print(f"indices list from Supabase: {len(items)} symbols")


def publish() -> None:
    frames = {name: store.read(name) for name in TABLES}
    frames["scan_hits"] = _scan_table()
    report = validation.report()
    st = store.status()
    old = remote.kv_get("versions") or {}
    versions = {name: remote.version(df) for name, df in frames.items()}
    con = remote._connect()
    try:
        with con.cursor() as cur:
            for name, df in frames.items():
                if old.get(name, {}).get("hash") == versions[name]["hash"]:
                    print(f"{name}: unchanged")
                    continue
                part = remote.recent_part(df, old.get(name))
                if part:  # intraday publishes: only the last days changed
                    remote.replace_since(name, part[0], part[1], cur)
                    print(f"{name}: {len(part[1]):,} recent rows (since {part[0]})")
                    continue
                remote.write_table(name, df, cur)
                print(f"{name}: {len(df):,} rows")
            remote.kv_set("versions", versions, cur)
            remote.kv_set("status", st, cur)
            remote.kv_set("validation", report, cur)
            if remote.kv_get("indices_config") is None:  # seed once; afterwards the dashboard owns it
                remote.kv_set("indices_config", world.config(), cur)
        con.commit()
    finally:
        con.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--pull-config", action="store_true")
    a = ap.parse_args()
    if not remote.DB_URL:
        raise SystemExit("SUPABASE_DB_URL is not set")
    pull_config() if a.pull_config else publish()
