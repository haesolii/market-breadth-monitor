"""Supabase (Postgres) as the table store.

- GitHub Actions computes locally (Parquet), then `app.publish` copies the result
  tables into Postgres.
- On Vercel (STORE=supabase) the API reads those tables instead of local files and
  writes only the small user-owned settings (indices list, manual reference values).
"""
import datetime as dt
import io
import json
import os
import threading
import time

import pandas as pd

DB_URL = os.getenv("SUPABASE_DB_URL", "").strip()
ON = os.getenv("STORE", "") == "supabase" and bool(DB_URL)
CACHE_SECONDS = 60  # data changes every few minutes while a market is open (intraday publishes)
SPLICE_DAYS = 10  # changed tables are re-read only from this many days before the cached end
FULL_SECONDS = 3600  # ...and in full at least this often (older rows can change, e.g. split refetch)

_cache: dict[str, tuple[float, object]] = {}
_lock = threading.Lock()
_loading: dict[str, threading.Lock] = {}


def _url() -> str:
    """Serverless (Vercel) uses Supabase's transaction pooler (port 6543): the session
    pooler (5432) allows only 15 clients and a dashboard page fires dozens of requests."""
    if os.getenv("VERCEL") and "pooler.supabase.com:5432" in DB_URL:
        return DB_URL.replace("pooler.supabase.com:5432", "pooler.supabase.com:6543")
    return DB_URL


def _connect():
    import psycopg  # only needed when Supabase is configured

    return psycopg.connect(_url(), autocommit=False, prepare_threshold=None)  # no prepared stmts: pooler-safe


POOL_MAX = 8  # per Vercel instance; the transaction pooler multiplexes them onto the database
_pool = None


def connection():
    """Context manager yielding a connection that commits on success. On Vercel an instance serves many
    requests, so connections are pooled and reused (opening one costs a TCP + TLS + auth round trip);
    the refresh job and local runs open a fresh one."""
    global _pool
    if not os.getenv("VERCEL"):
        return _connect()
    if _pool is None:
        with _lock:
            if _pool is None:
                from psycopg_pool import ConnectionPool
                _pool = ConnectionPool(_url(), min_size=1, max_size=POOL_MAX, open=True, check=ConnectionPool.check_connection,
                                       kwargs={"autocommit": False, "prepare_threshold": None})
    return _pool.connection()


def _q(name: str) -> str:
    return '"' + name.replace('"', "") + '"'


def ensure_kv(cur) -> None:
    cur.execute('CREATE TABLE IF NOT EXISTS "kv" (key text PRIMARY KEY, value jsonb NOT NULL, updated_at timestamptz DEFAULT now())')


def read_table(name: str) -> pd.DataFrame:
    hit = _cache.get("t:" + name)
    if hit and time.time() - hit[0] < CACHE_SECONDS:
        return hit[1]  # type: ignore[return-value]
    with _lock:
        loader = _loading.setdefault(name, threading.Lock())
    with loader:  # concurrent requests for the same table share one download
        hit = _cache.get("t:" + name)
        if hit and time.time() - hit[0] < CACHE_SECONDS:
            return hit[1]  # type: ignore[return-value]
        return _load(name, hit)


def _load(name: str, hit=None) -> pd.DataFrame:
    """Unchanged version -> keep the cached frame; changed -> re-read only the last
    SPLICE_DAYS (intraday publishes touch recent rows), full read if rows don't add up."""
    with connection() as con, con.cursor() as cur:
        ensure_kv(cur)
        cur.execute("""SELECT value -> %s FROM "kv" WHERE key = 'versions'""", (name,))
        row = cur.fetchone()
        ver = row[0] if row else None
        full_at = hit[3] if hit and len(hit) > 3 else 0.0
        if hit and ver and len(hit) > 2 and hit[2] == ver.get("hash"):
            df = hit[1]
        else:
            cur.execute("SELECT to_regclass(%s)", (name,))
            if cur.fetchone()[0] is None:
                df = pd.DataFrame()
            elif hit and ver and len(hit[1]) and "date" in hit[1].columns and time.time() - full_at < FULL_SECONDS:
                cut = max(hit[1]["date"]) - dt.timedelta(days=SPLICE_DAYS)
                new = _select(cur, f"SELECT * FROM {_q(name)} WHERE date >= %s", (cut,))
                df = pd.concat([hit[1][hit[1]["date"] < cut], new], ignore_index=True)
                if len(df) != ver.get("rows"):
                    df, full_at = _select(cur, f"SELECT * FROM {_q(name)}"), time.time()
            else:
                df, full_at = _select(cur, f"SELECT * FROM {_q(name)}"), time.time()
        con.commit()
    with _lock:
        _cache["t:" + name] = (time.time(), df, (ver or {}).get("hash"), full_at)
    return df


def _select(cur, sql: str, params=()) -> pd.DataFrame:
    cur.execute(sql, params)
    cols = [d.name for d in cur.description]
    return _decimals(pd.DataFrame(cur.fetchall(), columns=cols))


def _decimals(df: pd.DataFrame) -> pd.DataFrame:
    """Postgres numeric -> float, keep dates as date objects. A column may be all NULL."""
    for c in df.columns:
        v = df[c].dropna() if df[c].dtype == object else ()
        if len(v) and type(v.iloc[0]).__name__ == "Decimal":
            df[c] = df[c].astype(float)
    return df


def _h(df: pd.DataFrame) -> str:
    h = int(pd.util.hash_pandas_object(df, index=False).sum()) if len(df) else 0
    return f"{h & (2**64 - 1):016x}-{len(df)}"


def version(df: pd.DataFrame) -> dict:
    """Content fingerprint published next to each table (read side skips unchanged tables).
    Dated tables also fingerprint the rows before `cut`, so a publish can rewrite only the recent part."""
    v = {"hash": _h(df), "rows": len(df), "cols": list(map(str, df.columns))}
    if len(df) and "date" in df.columns:
        cut = max(df["date"]) - dt.timedelta(days=SPLICE_DAYS)
        v.update(cut=str(cut), head=_h(df[df["date"] < cut]))
    return v


def recent_part(df: pd.DataFrame, old: dict | None):
    """(cut, rows dated >= cut) when every row before the previous publish's cut is unchanged and the
    columns are the same (a new column needs the table recreated), else None."""
    if not old or "cut" not in old or not len(df) or "date" not in df.columns or old.get("cols") != list(map(str, df.columns)):
        return None
    cut = dt.date.fromisoformat(old["cut"])
    return (cut, df[df["date"] >= cut]) if _h(df[df["date"] < cut]) == old["head"] else None


def replace_since(name: str, cut, df: pd.DataFrame, cur) -> None:
    """Delete rows dated >= cut and insert `df` (same schema), inside the caller's transaction."""
    cur.execute(f"DELETE FROM {_q(name)} WHERE date >= %s", (cut,))
    _copy(cur, name, df)
    _cache.pop("t:" + name, None)


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
    if cur is None:
        with connection() as con, con.cursor() as c:
            return write_table(name, df, c)
    cols = ", ".join(f"{_q(c)} {_pg_type(df[c])}" for c in df.columns)
    cur.execute(f"DROP TABLE IF EXISTS {_q(name)}")
    cur.execute(f"CREATE TABLE {_q(name)} ({cols})")
    _copy(cur, name, df)
    _cache.pop("t:" + name, None)


def _copy(cur, name: str, df: pd.DataFrame) -> None:
    if not len(df):
        return
    buf = io.StringIO()
    df.to_csv(buf, index=False, header=False, na_rep="\\N")
    buf.seek(0)
    col_list = ", ".join(_q(c) for c in df.columns)
    with cur.copy(f"COPY {_q(name)} ({col_list}) FROM STDIN WITH (FORMAT csv, NULL '\\N')") as cp:
        while chunk := buf.read(1 << 20):
            cp.write(chunk)


def select(name: str, col: str, value) -> pd.DataFrame:
    """Rows of a published table where col = value, straight from the DB (for big tables the
    deployed API should not load whole, e.g. per-stock flows)."""
    hit = _cache.get(f"s:{name}:{col}:{value}")
    if hit and time.time() - hit[0] < CACHE_SECONDS:
        return hit[1]
    with connection() as con, con.cursor() as cur:
        cur.execute("SELECT to_regclass(%s)", (name,))
        df = _select(cur, f"SELECT * FROM {_q(name)} WHERE {_q(col)} = %s", (value,)) if cur.fetchone()[0] else pd.DataFrame()
        con.commit()
    with _lock:
        _cache[f"s:{name}:{col}:{value}"] = (time.time(), df)
    return df


def kv_get(key: str, default=None):
    hit = _cache.get("k:" + key)
    if hit and time.time() - hit[0] < CACHE_SECONDS:
        return hit[1]
    with connection() as con, con.cursor() as cur:
        ensure_kv(cur)
        cur.execute('SELECT value FROM "kv" WHERE key = %s', (key,))
        row = cur.fetchone()
        con.commit()
    val = row[0] if row else default
    with _lock:
        _cache["k:" + key] = (time.time(), val)
    return val


def kv_set(key: str, value, cur=None) -> None:
    if cur is None:
        with connection() as con, con.cursor() as c:
            return kv_set(key, value, c)
    ensure_kv(cur)
    cur.execute('INSERT INTO "kv"(key, value, updated_at) VALUES (%s, %s::jsonb, now()) '
                'ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()',
                (key, json.dumps(value, ensure_ascii=False, default=str)))
    _cache.pop("k:" + key, None)
