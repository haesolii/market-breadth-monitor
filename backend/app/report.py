"""Daily Telegram report (run by GitHub Actions after publishing).

    python -m app.report               # usage + data status + headline numbers
    python -m app.report --alert TEXT  # immediate alert (e.g. the refresh job failed)
    python -m app.report --signals     # breadth extremes newly reached on the latest final session

TELEGRAM_BOT_TOKEN is required. The chat id comes from TELEGRAM_CHAT_ID, or is found
once from the last message sent to the bot (getUpdates) and remembered in Supabase.
"""
import argparse
import datetime as dt
import html
import math
import os
import re

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
    for src, label in (("public_repo", "미국"), ("kospi", "코스피"), ("kosdaq", "코스닥"), ("crypto", "크립토")):
        r = b[b["source"] == src].sort_values("date").tail(1) if len(b) else b
        if len(r):
            out.append(f"{label} 20% 급등 {int(r.bull.iloc[0])} / 급락 {int(r.bear.iloc[0])}")
    r = mm[mm["source"] == "yahoo"].sort_values("date").tail(1) if len(mm) else mm
    if len(r) and pd.notna(r.t2108.iloc[0]):
        out.append(f"미국 40일선 위 종목 비율 {r.t2108.iloc[0]:.1f}% · 4% 상승 {int(r.up4.iloc[0])} / 하락 {int(r.down4.iloc[0])}")
    return out


# ---- breadth signal alerts ---------------------------------------------------------
US_N = 5000
# Calibrated count lines per market; mirrors CAL in frontend/lib/defs.ts (US universes scale by size).
CAL = {"kospi": {"down4": {1000: 225}, "bear": {100: 14}},
       "kosdaq": {"down4": {1000: 535}, "bear": {100: 55}},
       "crypto": {"down4": {1000: 320}, "bear": {100: 180}}}
# market label -> (table, source) pairs; the US Bear count comes from the survivorship-free series.
MARKETS = {"미국": [("breadth20", "public_repo"), ("market_monitor_daily", "yahoo")],
           "코스피": [("breadth20", "kospi"), ("market_monitor_daily", "kospi")],
           "코스닥": [("breadth20", "kosdaq"), ("market_monitor_daily", "kosdaq")],
           "크립토": [("breadth20", "crypto"), ("market_monitor_daily", "crypto")]}


# A "broad" reading needs at least this many stocks: a calibrated 1-3 is noise, not breadth.
MIN_N = 5


def cnt(base: int, key: str, market: str, n) -> int:
    lv = CAL.get(market, {}).get(key, {}).get(base)
    n = n if n and not pd.isna(n) else US_N
    return max(MIN_N, lv if lv is not None else math.ceil(base * min(1, n / US_N) - 1e-9))


def conditions(r: dict, market: str) -> dict[str, str]:
    """Signal code -> message for one row, at the dashboard's default extreme levels."""
    v = lambda k: r.get(k) if r.get(k) is not None and not pd.isna(r.get(k)) else None  # noqa: E731
    n, out = r.get("eligible_universe_count"), {}
    if v("bear") is not None and v("bear") >= (lv := cnt(100, "bear", market, n)):
        out["bear"] = f"20% 급락 {int(v('bear'))}종목 — 극단적 급락 (기준 {lv})"
    if v("down4") is not None and v("down4") >= (lv := cnt(1000, "down4", market, n)):
        out["down4"] = f"4% 하락 {int(v('down4'))}종목 — 극단적 투매 (기준 {lv})"
    if v("ratio10") is not None and v("ratio10") <= 0.5:
        out["ratio10_lo"] = f"10일 비율 {v('ratio10'):.2f} — 약세 신호 (≤ 0.5)"
    elif v("ratio10") is not None and v("ratio10") >= 2:
        out["ratio10_hi"] = f"10일 비율 {v('ratio10'):.2f} — 강한 매수세 (≥ 2)"
    if v("t2108") is not None and v("t2108") < 20:
        out["t2108_lo"] = f"40일선 위 종목 {v('t2108'):.1f}% — 극단적 과매도 (< 20%)"
    elif v("t2108") is not None and v("t2108") > 80:
        out["t2108_hi"] = f"40일선 위 종목 {v('t2108'):.1f}% — 과매수 (> 80%)"
    return out


def new_signals(rows: pd.DataFrame, market: str) -> tuple[str, list[str]] | None:
    """(latest date, messages) for conditions met on the latest row but not on the one before."""
    rows = rows.sort_values("date")
    if len(rows) < 2:
        return None
    cur, prev = (conditions(r, market) for r in rows.tail(2).iloc[::-1].to_dict("records"))
    return str(rows["date"].iloc[-1]), [m for k, m in cur.items() if k not in prev]


def signals() -> str | None:
    """Telegram text for newly reached extremes, once per (source, session); provisional
    (intraday) sources wait for the final values."""
    st = store.status().get("sources", {})
    sent = dict(st.get("_signals", {}).get("sent") or {})
    lines = []
    for label, pairs in MARKETS.items():
        for table, src in pairs:
            df = store.read(table)
            df = df[df["source"] == src] if len(df) else df
            if df.empty or st.get(src, {}).get("provisional"):
                continue
            hit = new_signals(df, src)
            if not hit or hit[0] <= sent.get(f"{table}:{src}", ""):
                continue
            sent[f"{table}:{src}"] = hit[0]
            lines += [f"• <b>{label}</b> {hit[0]}: {html.escape(m)}" for m in hit[1]]
    store.set_source("_signals", sent=sent)
    return "\n".join(["🔔 <b>시장 폭 신호</b> (기본 강조 기준, 매매 신호 아님)", *lines]) if lines else None


def brief_text() -> str | None:
    """Latest AI brief as Telegram HTML (headings bold; Telegram caps a message at 4096 chars)."""
    from . import brief

    rows = brief.latest(1)
    if not rows:
        return None
    body = re.sub(r"^#+\s*(.+)$", r"<b>\1</b>", html.escape(rows[0]["text"]), flags=re.M)
    body = re.sub(r"\*\*(.+?)\*\*", r"\1", body)
    head = f"🧠 <b>AI 시장 브리핑</b> · {rows[0]['date']} ({'미국 마감' if rows[0]['slot'] == 'us' else '한국 마감'})\n\n"
    return (head + body)[:4000]


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
    ap.add_argument("--signals", action="store_true")
    ap.add_argument("--brief", action="store_true", help="send the latest AI brief")
    ap.add_argument("--print", action="store_true", help="print instead of sending")
    a = ap.parse_args()
    text = f"🚨 <b>시장 폭 모니터</b>\n{html.escape(a.alert)}" if a.alert else signals() if a.signals else brief_text() if a.brief else daily()
    if not text:
        print("no new signals")
    elif a.print or not TOKEN:
        print(text)
    else:
        send(text)
