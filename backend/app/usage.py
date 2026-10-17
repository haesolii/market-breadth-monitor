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


LEVELS = [3, 5, 10, 20, 50, 100, 200, 500, 1000]
FAIL_BURST = 5  # failed logins within one hour


def surge_level(today: int, avg7: float, alerted: int) -> int | None:
    """Highest newly crossed visitor level worth alerting, or None. A level counts only
    when today is at least 3x the recent daily average (so a busy normal day stays quiet)."""
    crossed = [lv for lv in LEVELS if today >= lv > alerted]
    return crossed[-1] if crossed and today >= 3 * avg7 else None


def _notify(text: str) -> None:
    """Telegram message from the deployed API (chat id saved by the daily report)."""
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.getenv("TELEGRAM_CHAT_ID", "").strip() or remote.kv_get("telegram_chat_id")
    if not token or not chat:
        return
    import requests

    requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                  json={"chat_id": chat, "text": text, "parse_mode": "HTML"}, timeout=10)


def _exec(sql: str, params: tuple, fetch: bool = False):
    global _ready
    with remote._connect() as con, con.cursor() as cur:
        if not _ready:
            for d in DDL:
                cur.execute(d)
            _ready = True
        cur.execute(sql, params)
        rows = cur.fetchall() if fetch else None
        con.commit()
    return rows


def _check_surge(day: str) -> None:
    today = _exec('SELECT count(*) FROM "usage_visits" WHERE day = %s', (day,), fetch=True)[0][0]
    prev = _exec('SELECT count(*) FROM "usage_visits" WHERE day >= (%s::date - 7) AND day < %s::date', (day, day), fetch=True)[0][0]
    key = f"surge:{day}"
    level = surge_level(today, prev / 7, int(remote.kv_get(key) or 0))
    if level:
        remote.kv_set(key, level)
        _notify(f"📈 <b>방문자 급증</b>\n오늘 방문자 {today}명 (최근 7일 하루 평균 {prev / 7:.1f}명)\n"
                "https://market-breadth-monitor.vercel.app")


def _check_fail_burst() -> None:
    n = _exec("SELECT count(*) FROM \"usage_logins\" WHERE NOT ok AND ts >= now() - interval '1 hour'", (), fetch=True)[0][0]
    key = "failburst:" + dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H")
    if n >= FAIL_BURST and not remote.kv_get(key):
        remote.kv_set(key, n)
        _notify(f"🚨 <b>로그인 실패 급증</b>\n최근 1시간 비밀번호 틀림 {n}회 — 비밀번호를 모르는 누군가의 시도일 수 있습니다.")


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
        new = _exec('INSERT INTO "usage_visits"(day, visitor, ua) VALUES (%s, %s, %s) '
                    "ON CONFLICT (day, visitor) DO UPDATE SET last_seen = now() RETURNING (xmax = 0)",
                    (day, vid, ua), fetch=True)
        if new and new[0][0]:  # first visit of this visitor today
            _check_surge(day)
    except Exception as e:  # noqa: BLE001 - analytics must never break the dashboard
        print(f"[warn] usage: {e}")


def record_login(request, ok: bool) -> None:
    if not remote.ON:
        return
    vid, ua = client(request)
    try:
        _exec('INSERT INTO "usage_logins"(ok, visitor, ua) VALUES (%s, %s, %s)', (ok, vid, ua))
        if not ok:
            _check_fail_burst()
    except Exception as e:  # noqa: BLE001
        print(f"[warn] usage: {e}")
