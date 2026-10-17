"""Who used the deployed dashboard: daily unique visitors and login attempts (Supabase).

Visitors are an anonymous hash of IP + user agent (no raw IPs stored). Recording is
best-effort: it never breaks a request, and only runs on the deployed site (remote.ON).
"""
import datetime as dt
import hashlib
import os
import threading
import time

from . import remote

SALT = os.getenv("USAGE_SALT", "mb-usage")
_seen: dict[tuple[str, str], float] = {}  # (day, visitor) -> last write, per server instance
_lock = threading.Lock()
_ready = False

DDL = [
    'CREATE TABLE IF NOT EXISTS "usage_visits" (day date, visitor text, first_seen timestamptz DEFAULT now(), '
    "last_seen timestamptz DEFAULT now(), ua text, PRIMARY KEY (day, visitor))",
    'CREATE TABLE IF NOT EXISTS "usage_logins" (ts timestamptz DEFAULT now(), ok boolean, visitor text, ua text)',
]


def visitor_id(ip: str, ua: str) -> str:
    return hashlib.sha256(f"{SALT}|{ip}|{ua}".encode()).hexdigest()[:12]


def client(request) -> tuple[str, str]:
    ip = (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "")).split(",")[0].strip()
    ua = request.headers.get("user-agent", "")[:200]
    return visitor_id(ip, ua), ua


def _exec(sql: str, params: tuple) -> None:
    global _ready
    with remote._connect() as con, con.cursor() as cur:
        if not _ready:
            for d in DDL:
                cur.execute(d)
            _ready = True
        cur.execute(sql, params)
        con.commit()


def record_visit(request) -> None:
    """At most one write per visitor per 10 minutes per instance (the status bar polls every 20s)."""
    if not remote.ON:
        return
    vid, ua = client(request)
    day = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date().isoformat()  # KST day
    with _lock:
        if time.time() - _seen.get((day, vid), 0) < 600:
            return
        _seen[(day, vid)] = time.time()
    try:
        _exec('INSERT INTO "usage_visits"(day, visitor, ua) VALUES (%s, %s, %s) '
              "ON CONFLICT (day, visitor) DO UPDATE SET last_seen = now()", (day, vid, ua))
    except Exception as e:  # noqa: BLE001 - analytics must never break the dashboard
        print(f"[warn] usage: {e}")


def record_login(request, ok: bool) -> None:
    if not remote.ON:
        return
    vid, ua = client(request)
    try:
        _exec('INSERT INTO "usage_logins"(ok, visitor, ua) VALUES (%s, %s, %s)', (ok, vid, ua))
    except Exception as e:  # noqa: BLE001
        print(f"[warn] usage: {e}")
