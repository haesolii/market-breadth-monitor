"""Data health: which sources are failing or not advancing, for a Telegram alert when a problem starts
and a note when it clears (many sources are unofficial endpoints that can change without notice).

A source has a problem when
  - its last attempt failed (last_error set after the last success), or
  - a timed source (refresh.PERIODIC) has not succeeded for STALE_X x its interval, or
  - a session-based source's latest date is 2+ completed sessions behind its market.
"""
import datetime as dt
import time

from . import refresh, store, universes
from .market_calendar import latest_complete_session, sessions

STALE_X = 4


def _age_h(ts: str | None) -> float | None:
    return None if not ts else (time.time() - dt.datetime.fromisoformat(ts).timestamp()) / 3600


def issues() -> dict[str, str]:
    st = store.status()["sources"]
    out = {}
    for s in refresh.enabled_sources():
        x = st.get(s, {})
        ok, err = x.get("last_success"), x.get("last_error")
        if err and (not ok or (x.get("last_error_at") or "") > ok):
            out[s] = f"갱신 실패: {str(err)[:140]}"
            continue
        if s in refresh.PERIODIC:
            age = _age_h(ok)
            if age is None or age > refresh.PERIODIC[s] * STALE_X / 3600:
                out[s] = f"{'한 번도 성공 못 함' if age is None else f'{age:.0f}시간째 갱신 안 됨'} (주기 {refresh.PERIODIC[s] // 60}분)"
            continue
        ld = refresh.latest_date(s)
        cal = universes.cal_of(s)
        target = latest_complete_session(cal=cal)
        if ld is None:
            out[s] = "데이터 없음"
        elif len(sessions(ld, target, cal=cal)) > 2:  # ld and target included: 2+ sessions missing
            out[s] = f"최신 데이터 {ld}, 기대 {target}"
    return out


def changes() -> list[str]:
    """Telegram lines for problems that started or cleared since the last check (remembered in status)."""
    now = issues()
    prev = store.status()["sources"].get("_health", {}).get("open") or {}
    lines = [f"• ⚠️ <b>{s}</b>: {msg}" for s, msg in now.items() if s not in prev]
    lines += [f"• ✅ <b>{s}</b>: 정상으로 돌아옴" for s in prev if s not in now]
    store.set_source("_health", open=now, checked=store.now_utc())
    return lines
