"""Exchange trading calendars (holidays, early closes, DST) via pandas_market_calendars."""
import datetime as dt
import functools
import warnings
from zoneinfo import ZoneInfo

import pandas_market_calendars as mcal

ET = ZoneInfo("America/New_York")
# calendar -> (exchange timezone, local hour after which today's session counts as final).
# Close is 16:00 ET / 15:30 KST; the buffer covers late prints and provider publishing lag.
CALENDARS = {"NYSE": (ET, 18), "XKRX": (ZoneInfo("Asia/Seoul"), 18)}
FINAL_HOUR_ET = 18


@functools.lru_cache(maxsize=None)
def _cal(name: str):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # XKRX: "break_start discontinued" notice
        return mcal.get_calendar(name)


def sessions(start: dt.date, end: dt.date, cal: str = "NYSE") -> list[dt.date]:
    return [d.date() for d in _cal(cal).valid_days(start, end)]


def latest_complete_session(now: dt.datetime | None = None, cal: str = "NYSE") -> dt.date:
    tz, final_hour = CALENDARS[cal]
    now = (now or dt.datetime.now(dt.timezone.utc)).astimezone(tz)
    days = sessions(now.date() - dt.timedelta(days=14), now.date(), cal)
    if days[-1] == now.date() and now.hour < final_hour:
        return days[-2]
    return days[-1]
