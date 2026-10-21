"""Daily Telegram report (run by GitHub Actions after publishing).

    python -m app.report               # usage + data status + headline numbers
    python -m app.report --alert TEXT  # immediate alert (e.g. the refresh job failed)

TELEGRAM_BOT_TOKEN is required. The chat id comes from TELEGRAM_CHAT_ID, or is found
once from the last message sent to the bot (getUpdates) and remembered in Supabase.
"""
import argparse
import datetime as dt
import html
import os

import pandas as pd
import requests

from . import remote, store
from .market_calendar import latest_complete_session

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
KST = dt.timezone(dt.timedelta(hours=9))
API = "https://api.telegram.org/bot{token}/{method}"


def _tg(method: str, **params) -> dict:
    r = requests.post(API.format(token=TOKEN, method=method), json=params, timeout=20)
    r.raise_for_status()
    return r.json()


def chat_id() -> str:
    cid = os.getenv("TELEGRAM_CHAT_ID", "").strip() or (remote.kv_get("telegram_chat_id") if remote.DB_URL else None)
    if cid:
        return str(cid)
    updates = _tg("getUpdates").get("result", [])
    chats = [u["message"]["chat"]["id"] for u in updates if "message" in u]
    if not chats:
        raise SystemExit("봇에게 아무 메시지나 먼저 보내 주세요 (chat id를 찾을 수 없음)")
    cid = str(chats[-1])
    if remote.DB_URL:
        remote.kv_set("telegram_chat_id", cid)
    return cid


def send(text: str) -> None:
    _tg("sendMessage", chat_id=chat_id(), text=text, parse_mode="HTML", disable_web_page_preview=True)


def _query(sql: str) -> list[tuple]:
    try:
        with remote._connect() as con, con.cursor() as cur:
            cur.execute(sql)
            return cur.fetchall()
    except Exception:  # noqa: BLE001 - tables appear after the first visit
        return []


def usage_lines() -> list[str]:
    if not remote.DB_URL:
        return ["👥 이용 기록: (Supabase 미설정)"]
    today = dt.datetime.now(KST).date()
    rows = _query('SELECT day, count(*), max(last_seen) FROM "usage_visits" '
                  f"WHERE day >= DATE '{today - dt.timedelta(days=6)}' GROUP BY day")
    by_day = {r[0]: r[1] for r in rows}
    last = max((r[2] for r in rows), default=None)
    week = _query('SELECT count(DISTINCT visitor) FROM "usage_visits" '
                  f"WHERE day >= DATE '{today - dt.timedelta(days=6)}'")
    logins = _query('SELECT ok, count(*) FROM "usage_logins" WHERE ts >= now() - interval \'24 hours\' GROUP BY ok')
    ok = sum(n for flag, n in logins if flag)
    bad = sum(n for flag, n in logins if not flag)
    lines = [
        f"👥 방문자: 오늘 {by_day.get(today, 0)}명 · 어제 {by_day.get(today - dt.timedelta(days=1), 0)}명 · "
        f"최근 7일 {week[0][0] if week else 0}명",
        f"🕒 마지막 접속: {last.astimezone(KST).strftime('%m-%d %H:%M') if last else '없음'}",
        f"🔐 로그인(24시간): 성공 {ok} · 실패 {bad}" + (" ⚠️ 모르는 시도일 수 있음" if bad else ""),
    ]
    return lines


def data_lines() -> list[str]:
    st = store.status().get("sources", {})
    names = {"public_repo": "미국(상장폐지 포함)", "yahoo": "미국(현재 상장)", "kospi": "코스피", "kosdaq": "코스닥",
             "crypto": "크립토", "indices": "세계 지수", "macro": "매크로"}
    expected = {"kospi": latest_complete_session(cal="XKRX"), "kosdaq": latest_complete_session(cal="XKRX"),
                "crypto": latest_complete_session(cal="CRYPTO")}
    us = latest_complete_session()
    out = []
    b = store.read("breadth20")
    for k, label in names.items():
        s = st.get(k, {})
        if k in ("indices", "macro"):
            latest = (s.get("result") or {}).get("latest_date")
            ok = not s.get("last_error")
        else:
            d = b.loc[b["source"] == k, "date"] if len(b) else pd.Series(dtype=object)
            latest = str(max(d)) if len(d) else None
            ok = latest == str(expected.get(k, us)) and not s.get("last_error")
        out.append(f"{'✅' if ok else '⚠️'} {label}: {latest or '없음'}" + (f" (오류: {html.escape(str(s.get('last_error'))[:80])})" if s.get("last_error") else ""))
    return out


def headline_lines() -> list[str]:
    b = store.read("breadth20")
    mm = store.read("market_monitor_daily")
    out = []
    for src, label in (("public_repo", "미국"), ("kospi", "코스피"), ("kosdaq", "코스닥")):
        r = b[b["source"] == src].sort_values("date").tail(1) if len(b) else b
        if len(r):
            out.append(f"{label} 20% 급등 {int(r.bull.iloc[0])} / 급락 {int(r.bear.iloc[0])}")
    r = mm[mm["source"] == "yahoo"].sort_values("date").tail(1) if len(mm) else mm
    if len(r) and pd.notna(r.t2108.iloc[0]):
        out.append(f"미국 40일선 위 종목 비율 {r.t2108.iloc[0]:.1f}% · 4% 상승 {int(r.up4.iloc[0])} / 하락 {int(r.down4.iloc[0])}")
    return out


def daily() -> str:
    today = dt.datetime.now(KST).strftime("%Y-%m-%d")
    parts = [f"<b>📊 시장 폭 모니터 · {today}</b>", "", *usage_lines(), "", "<b>데이터</b>", *data_lines()]
    head = headline_lines()
    if head:
        parts += ["", "<b>오늘의 수치</b>", *head]
    parts += ["", "https://market-breadth-monitor.vercel.app"]
    return "\n".join(parts)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--alert")
    ap.add_argument("--print", action="store_true", help="print instead of sending")
    a = ap.parse_args()
    text = f"🚨 <b>시장 폭 모니터</b>\n{html.escape(a.alert)}" if a.alert else daily()
    if a.print or not TOKEN:
        print(text)
    else:
        send(text)
