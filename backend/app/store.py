"""Parquet tables (one file each) + a small JSON status file. Writes are atomic
(tmp file + os.replace) and upserts keep existing rows that the new batch lacks."""
import datetime as dt
import json
import os
import threading

import duckdb
import pandas as pd

from .config import DATA

_lock = threading.RLock()


def path(name: str):
    return DATA / f"{name}.parquet"


def read(name: str) -> pd.DataFrame:
    p = path(name)
    return pd.read_parquet(p) if p.exists() else pd.DataFrame()


def write(name: str, df: pd.DataFrame) -> None:
    with _lock:
        tmp = DATA / f".{name}.tmp.parquet"
        df.to_parquet(tmp, index=False)
        os.replace(tmp, path(name))


def upsert(name: str, df: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    """Insert or replace rows by key. Never drops rows absent from `df`."""
    with _lock:
        old = read(name)
        out = pd.concat([old, df], ignore_index=True) if len(old) else df
        out = out.drop_duplicates(keys, keep="last").sort_values(keys).reset_index(drop=True)
        write(name, out)
        return out


def replace_source(name: str, source: str, df: pd.DataFrame) -> None:
    """Swap all rows of one source for a full recomputation. Refuses (keeps the old
    rows) if the new set is >10% smaller, which would mean input data went missing."""
    with _lock:
        old = read(name)
        mine = old[old["source"] == source] if len(old) else old
        if len(mine) and len(df) < 0.9 * len(mine):
            raise RuntimeError(f"{name}/{source}: recomputed {len(df)} rows < {len(mine)} stored; keeping existing data")
        rest = old[old["source"] != source] if len(old) else old
        write(name, pd.concat([rest, df], ignore_index=True).sort_values(["source", "date"]).reset_index(drop=True))


def sql(query: str, **frames) -> pd.DataFrame:
    con = duckdb.connect()
    try:
        for k, v in frames.items():
            con.register(k, v)
        return con.sql(query).df()
    finally:
        con.close()


# ---- status / log -------------------------------------------------------------
_STATUS = DATA / "status.json"


def status() -> dict:
    with _lock:
        if _STATUS.exists():
            return json.loads(_STATUS.read_text("utf-8"))
        return {"sources": {}, "log": []}


def _save(st: dict) -> None:
    tmp = DATA / ".status.tmp.json"
    tmp.write_text(json.dumps(st, indent=1, default=str), "utf-8")
    os.replace(tmp, _STATUS)


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def set_source(source: str, **fields) -> None:
    with _lock:
        st = status()
        st["sources"].setdefault(source, {}).update(fields)
        _save(st)


def log(level: str, source: str, msg: str) -> None:
    with _lock:
        st = status()
        st["log"] = ([{"t": now_utc(), "level": level, "source": source, "msg": msg[:2000]}] + st["log"])[:300]
        _save(st)
    print(f"[{level}] {source}: {msg[:300]}", flush=True)
