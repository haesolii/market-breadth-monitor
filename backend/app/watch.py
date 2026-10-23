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
FLOW_X = 3.0          # a flow event: one day's net buying / selling >= FLOW_X x the stock's own 60-day mean |net|
FLOW_MIN_PCT = 0.01   # ...and at least this % of market value (thin names move a lot in relative terms)
MAX_ALERTS = 30       # Telegram lines per message; scheduled / filing events first
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
    dart_, earn, ir = store.read("dart_prelim"), store.read("earnings"), store.read("kr_ir")
    # per-stock flows from the DB on the deployed API: the whole table is ~300k rows
    flow = None if remote.ON else store.read("kr_flow")
    dev = store.read("dart_events")
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
        f = (remote.select("kr_flow", "ticker", t) if flow is None else flow[flow["ticker"] == t] if len(flow) else flow) if kr else None
        if kr and f is not None and len(f) and len(me):
            for d, who, v, x in big_flows(f, float(me["size"].iloc[0]), since):
                label = "외국인" if who == "foreign" else "기관"
                add(it, d, "수급", f"{label} {'순매수' if v > 0 else '순매도'} {v / 1e8:+,.0f}억 (평소의 {x:.1f}배, 시총의 {v / me['size'].iloc[0] * 100:+.2f}%)", f"{who}:{d}")
        if kr and len(dart_):
            for r in _recent(dart_[dart_["code"] == t], since).itertuples():
                react = "" if pd.isna(r.react) else f" · 반응 {r.react:+.1f}%"
                add(it, r.date, "잠정실적", f"{r.title}{react}", r.rcept_no)
        if kr and len(dev):
            for r in _recent(dev[dev["code"] == t], since).itertuples():
                react = "" if pd.isna(r.react) else f" · 반응 {r.react:+.1f}%"
                add(it, r.date, "공시", f"[{r.category}] {r.title}{react}", r.rcept_no)
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


def big_flows(f: pd.DataFrame, size: float, since: dt.date) -> list[tuple]:
    """(date, investor, net value, multiple of normal) for days since `since` whose foreign or institutional
    net value is >= FLOW_X x the mean |net| of the 60 sessions before it and >= FLOW_MIN_PCT of market value."""
    f = f.sort_values("date")
    out = []
    for who in ("foreign", "inst"):
        a = f[who].abs()
        normal = a.shift(1).rolling(60, min_periods=20).mean()
        x = a / normal
        hit = (x >= FLOW_X) & (a / size * 100 >= FLOW_MIN_PCT) & (pd.to_datetime(f["date"]).dt.date >= since)
        out += [(d, who, float(v), float(m)) for d, v, m in zip(f["date"][hit], f[who][hit], x[hit])]
    return out


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
    due = [e for e in events(load(), today) if e["key"] not in sent and (not e["upcoming"] or _d(e["date"]) <= today + dt.timedelta(days=1))]
    rank = {"실적": 0, "IR": 0, "잠정실적": 1, "공시": 1, "리포트": 2, "ETF": 3, "급등락": 4, "수급": 5}
    for e in sorted(due, key=lambda e: rank.get(e["kind"], 9))[:MAX_ALERTS]:  # the rest wait for the next message
        new.append(e["key"])
        lines.append(f"• <b>{html.escape(e['name'])}</b> [{e['kind']}] {e['date']}: {html.escape(e['text'])}")
    if new:
        store.set_source("_watch", sent=(list(sent) + new)[-2000:])
    return lines
