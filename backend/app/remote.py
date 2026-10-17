"""Supabase (Postgres) as the table store.

- GitHub Actions computes locally (Parquet), then `app.publish` copies the result
  tables into Postgres.
- On Vercel (STORE=supabase) the API reads those tables instead of local files and
  writes only the small user-owned settings (indices list, manual reference values).
"""
import io
import json
import os
import threading
import time

import pandas as pd

DB_URL = os.getenv("SUPABASE_DB_URL", "").strip()
ON = os.getenv("STORE", "") == "supabase" and bool(DB_URL)
CACHE_SECONDS = 60

_cache: dict[str, tuple[float, object]] = {}
_lock = threading.Lock()


def _connect():
    import psycopg  # only needed when Supabase is configured

    return psycopg.connect(DB_URL, autocommit=False, prepare_threshold=None)


def _q(name: str) -> str:
    return '"' + name.replace('"', "") + '"'


def ensure_kv(cur) -> None:
    cur.execute('CREATE TABLE IF NOT EXISTS "kv" (key text PRIMARY KEY, value jsonb NOT NULL, updated_at timestamptz DEFAULT now())')


def read_table(name: str) -> pd.DataFrame:
    hit = _cache.get("t:" + name)
    if hit and time.time() - hit[0] < CACHE_SECONDS:
        return hit[1]  # type: ignore[return-value]
    with _connect() as con, con.cursor() as cur:
        cur.execute("SELECT to_regclass(%s)", (name,))
        if cur.fetchone()[0] is None:
            df = pd.DataFrame()
        else:
            cur.execute(f"SELECT * FROM {_q(name)}")
            cols = [d.name for d in cur.description]
            df = pd.DataFrame(cur.fetchall(), columns=cols)
            for c in df.columns:  # Postgres numeric -> float, keep dates as date objects
                if df[c].dtype == object and len(df) and type(df[c].dropna().iloc[0]).__name__ == "Decimal":
                    df[c] = df[c].astype(float)
    with _lock:
        _cache["t:" + name] = (time.time(), df)
    return df


_PG = {"b": "boolean", "i": "bigint", "u": "bigint", "f": "double precision"}


def _pg_type(s: pd.Series) -> str:
    if s.dtype.kind in _PG:
        return _PG[s.dtype.kind]
    if s.dtype.kind == "M":
        return "timestamp"
    sample = s.dropna()
    if len(sample) and type(sample.iloc[0]).__name__ == "date":
        return "date"
    return "text"


def write_table(name: str, df: pd.DataFrame, cur=None) -> None:
    """Replace a whole table (schema from the frame) in one transaction via COPY."""
    own = cur is None
    con = _connect() if own else None
    cur = con.cursor() if own else cur
    try:
        cols = ", ".join(f"{_q(c)} {_pg_type(df[c])}" for c in df.columns)
        cur.execute(f"DROP TABLE IF EXISTS {_q(name)}")
        cur.execute(f"CREATE TABLE {_q(name)} ({cols})")
        if len(df):
            buf = io.StringIO()
            df.to_csv(buf, index=False, header=False, na_rep="\\N")
            buf.seek(0)
            col_list = ", ".join(_q(c) for c in df.columns)
            with cur.copy(f"COPY {_q(name)} ({col_list}) FROM STDIN WITH (FORMAT csv, NULL '\\N')") as cp:
                while chunk := buf.read(1 << 20):
                    cp.write(chunk)
        if own:
            con.commit()
    finally:
        if own:
            cur.close()
            con.close()
    _cache.pop("t:" + name, None)


def kv_get(key: str, default=None):
    hit = _cache.get("k:" + key)
    if hit and time.time() - hit[0] < CACHE_SECONDS:
        return hit[1]
    with _connect() as con, con.cursor() as cur:
        ensure_kv(cur)
        cur.execute('SELECT value FROM "kv" WHERE key = %s', (key,))
        row = cur.fetchone()
        con.commit()
    val = row[0] if row else default
    with _lock:
        _cache["k:" + key] = (time.time(), val)
    return val


def kv_set(key: str, value, cur=None) -> None:
    own = cur is None
    con = _connect() if own else None
    cur = con.cursor() if own else cur
    try:
        ensure_kv(cur)
        cur.execute('INSERT INTO "kv"(key, value, updated_at) VALUES (%s, %s::jsonb, now()) '
                    'ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()',
                    (key, json.dumps(value, ensure_ascii=False, default=str)))
        if own:
            con.commit()
    finally:
        if own:
            cur.close()
            con.close()
    _cache.pop("k:" + key, None)
