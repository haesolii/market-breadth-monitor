"""Watchlist: the user's stocks, their latest numbers and every event the dashboard knows about
(broker reports, active-ETF trades, foreign / institutional flows, DART filings, earnings and IR
dates, big moves), plus Telegram alerts for events not sent before.

The list is user-owned: data/watchlist.json locally, kv "watchlist" on Supabase (edited on the
deployed site; the refresh job pulls it before computing alerts).
"""
import datetime as dt
import html
import json

import pandas as pd

from . import remote, store
from .config import DATA

FILE = DATA / "watchlist.json"
KR = ("kospi", "kosdaq")
MOVE = 5.0            # % one-day move worth an event
FLOW_PCT = 0.05       # foreign or institutional one-day net buying, % of market value
LOOKBACK = 7          # days of past events shown / alerted
AHEAD = 14            # days of scheduled earnings / IR shown


def load() -> list[dict]:
    if remote.ON:
        return remote.kv_get("watchlist") or []
    return json.loads(FILE.read_text("utf-8")) if FILE.exists() else []


def save(items: list[dict]) -> None:
    if remote.ON:
        remote.kv_set("watchlist", items)
    else:
        FILE.write_text(json.dumps(items, ensure_ascii=False, indent=1), "utf-8")


def _d(v) -> dt.date:
    return v if isinstance(v, dt.date) else pd.to_datetime(v).date()


def _recent(df: pd.DataFrame, since: dt.date, col: str = "date") -> pd.DataFrame:
    return df[pd.to_datetime(df[col]).dt.date >= since] if len(df) else df


def events(items: list[dict], today: dt.date | None = None) -> list[dict]:
    """Every known event for the watchlist stocks, newest first. key = stable id for alert de-duplication."""
    today = today or dt.date.today()
    since, until = today - dt.timedelta(days=LOOKBACK), today + dt.timedelta(days=AHEAD)
    sm = store.read("sector_map")
    rep, ch, fl = store.read("analyst_reports"), store.read("etf_changes"), store.read("etf_funds")
    flow, dart_, earn, ir = store.read("kr_flow"), store.read("dart_prelim"), store.read("earnings"), store.read("kr_ir")
    fund = dict(zip(fl["etf"], fl["name"])) if len(fl) else {}
    out = []

    def add(it, date, kind, text, key):
        out.append({"date": str(date), "ticker": it["ticker"], "name": it.get("name") or it["ticker"], "kind": kind, "text": text,
                    "key": f"{it['ticker']}:{kind}:{key}", "upcoming": _d(date) > today})

    for it in items:
        t, kr = it["ticker"], it.get("market") in KR
        me = sm[(sm["ticker"] == t) & (sm["market"] == it.get("market"))] if len(sm) else sm
        name = me["name"].iloc[0] if len(me) else it.get("name", t)
        if len(me) and pd.notna(me["r1d"].iloc[0]) and abs(me["r1d"].iloc[0]) >= MOVE:
            add(it, me["date"].iloc[0], "급등락", f"하루 {me['r1d'].iloc[0]:+.1f}%", me["date"].iloc[0])
        if kr and len(rep):
            for r in _recent(rep[rep["code"] == t], since).itertuples():
                chg = "" if pd.isna(r.goal_chg) else f" (목표가 {r.goal_chg:+.1f}%)"
                add(it, r.date, "리포트", f"{r.broker}: {r.title} · 목표가 {r.goal:,.0f}{chg}" if pd.notna(r.goal) else f"{r.broker}: {r.title}", r.nid)
        if len(ch):
            for r in _recent(ch[ch["name" if kr else "ticker"] == (name if kr else t)], since).itertuples():
                add(it, r.date, "ETF", f"{fund.get(r.etf, r.etf)} {r.kind}", f"{r.etf}:{r.date}")
        if kr and len(flow) and len(me):
            f = _recent(flow[flow["ticker"] == t], since)
            for r in f.itertuples():
                for who, label in (("foreign", "외국인"), ("inst", "기관")):
                    v = getattr(r, who)
                    if abs(v) / me["size"].iloc[0] * 100 >= FLOW_PCT:
                        add(it, r.date, "수급", f"{label} {'순매수' if v > 0 else '순매도'} {v / 1e8:+,.0f}억 (시총의 {v / me['size'].iloc[0] * 100:+.2f}%)", f"{who}:{r.date}")
        if kr and len(dart_):
            for r in _recent(dart_[dart_["code"] == t], since).itertuples():
                react = "" if pd.isna(r.react) else f" · 반응 {r.react:+.1f}%"
                add(it, r.date, "잠정실적", f"{r.title}{react}", r.rcept_no)
        if kr and len(ir):
            for r in ir[(ir["code"] == t) & (pd.to_datetime(ir["ir_date"]).dt.date >= since)].itertuples():
                if _d(r.ir_date) <= until:
                    add(it, r.ir_date, "IR", f"기업설명회 {r.ir_time or ''} · {r.summary}".strip(), r.rcept_no)
        if not kr and len(earn):
            for r in earn[(earn["symbol"] == t) & (pd.to_datetime(earn["date"]).dt.date >= since)].itertuples():
                if _d(r.date) > until:
                    continue
                done = pd.notna(r.eps)
                text = (f"실적 발표: EPS {r.eps:.2f} vs 예상 {r.eps_forecast:.2f}" + ("" if pd.isna(r.react) else f" · 반응 {r.react:+.1f}%")
                        if done and pd.notna(r.eps_forecast) else f"실적 발표 예정 ({ {'pre': '장전', 'after': '장후'}.get(r.time, '시각 미정') })")
                add(it, r.date, "실적", text, f"{r.date}:{done}")
    return sorted(out, key=lambda e: e["date"], reverse=True)


def overview() -> dict:
    items = load()
    sm = store.read("sector_map")
    rows = []
    for it in items:
        me = sm[(sm["ticker"] == it["ticker"]) & (sm["market"] == it.get("market"))] if len(sm) else sm
        r = me.iloc[0] if len(me) else None
        rows.append({**it, **({k: (None if pd.isna(r[k]) else (float(r[k]) if k != "name" and k != "sector" else r[k]))
                              for k in ("name", "sector", "close", "r1d", "r1w", "r1m", "ytd")} if r is not None else {})})
    return {"items": rows, "events": events(items)}


def alerts() -> list[str]:
    """Past (not scheduled) watchlist events not alerted before, as Telegram lines; scheduled ones
    are alerted the day before / on the day."""
    st = store.status()["sources"].get("_watch", {})
    sent = set(st.get("sent") or [])
    today = dt.date.today()
    lines, new = [], []
    for e in events(load(), today):
        due = not e["upcoming"] or _d(e["date"]) <= today + dt.timedelta(days=1)
        if e["key"] in sent or not due:
            continue
        new.append(e["key"])
        lines.append(f"• <b>{html.escape(e['name'])}</b> [{e['kind']}] {e['date']}: {html.escape(e['text'])}")
    if new:
        store.set_source("_watch", sent=(list(sent) + new)[-2000:])
    return lines
