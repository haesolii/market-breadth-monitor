"""Exchange trading calendars (holidays, early closes, DST) via pandas_market_calendars."""
import datetime as dt
import functools
import threading
import warnings
from zoneinfo import ZoneInfo

import pandas_market_calendars as mcal

ET = ZoneInfo("America/New_York")
# calendar -> (exchange timezone, local hour after which today's session counts as final).
# Close is 16:00 ET / 15:30 KST; the buffer covers late prints and provider publishing lag.
CALENDARS = {"NYSE": (ET, 18), "XKRX": (ZoneInfo("Asia/Seoul"), 18)}
FINAL_HOUR_ET = 18
OPEN = {"NYSE": (9, 30), "XKRX": (9, 0)}  # local regular-session open
# pandas_market_calendars builds holidays lazily and is not thread-safe on first use
# (concurrent API requests on a cold server crashed with '_holidays' AttributeError).
_lock = threading.Lock()
# 24/7 markets: every UTC day is a session, final at 00:00 UTC (+10 min for the exchange's
# daily bar). Deliberately not in CALENDARS: it is never "live", so the intraday loop
# (which runs while any CALENDARS market is open) does not spin forever on it.
CRYPTO = "CRYPTO"


@functools.lru_cache(maxsize=None)
def _cal(name: str):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # XKRX: "break_start discontinued" notice
        return mcal.get_calendar(name)


def sessions(start: dt.date, end: dt.date, cal: str = "NYSE") -> list[dt.date]:
    if cal == CRYPTO:
        return [start + dt.timedelta(days=i) for i in range((end - start).days + 1)]
    with _lock:
        days = _cal(cal).valid_days(start, end)
    return [d.date() for d in days]


def session_elapsed(now: dt.datetime | None = None, cal: str = "NYSE") -> float:
    """Share (0..1] of today's regular session that has elapsed (early closes included); 1 outside it."""
    if cal == CRYPTO:
        return 1.0
    now = now or dt.datetime.now(dt.timezone.utc)
    day = now.astimezone(CALENDARS[cal][0]).date()
    with _lock:
        s = _cal(cal).schedule(day, day)
    if s.empty:
        return 1.0
    o, c = s["market_open"].iloc[0], s["market_close"].iloc[0]
    return float(min(1.0, max((now - o) / (c - o), 0.05)))  # floor: first minutes would blow up 20x+


def latest_complete_session(now: dt.datetime | None = None, cal: str = "NYSE") -> dt.date:
    if cal == CRYPTO:
        return ((now or dt.datetime.now(dt.timezone.utc)).astimezone(dt.timezone.utc) - dt.timedelta(minutes=10)).date() - dt.timedelta(days=1)
    tz, final_hour = CALENDARS[cal]
    now = (now or dt.datetime.now(dt.timezone.utc)).astimezone(tz)
    days = sessions(now.date() - dt.timedelta(days=14), now.date(), cal)
    if days[-1] == now.date() and now.hour < final_hour:
        return days[-2]
    return days[-1]


def live_session(now: dt.datetime | None = None, cal: str = "NYSE") -> dt.date | None:
    """Today's session while it is open or not yet final (open .. final hour), else None."""
    if cal == CRYPTO:
        return None
    tz, final_hour = CALENDARS[cal]
    now = (now or dt.datetime.now(dt.timezone.utc)).astimezone(tz)
    if sessions(now.date(), now.date(), cal) and OPEN[cal] <= (now.hour, now.minute) and now.hour < final_hour:
        return now.date()
    return None
