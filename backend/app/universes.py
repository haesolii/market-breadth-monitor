"""Self-computed universes: which stocks, which exchange calendar, which
thresholds, which benchmark. The indicator formulas are identical for all of
them; only the money/volume thresholds are adapted per market (see
docs/indicator-definitions.md, "다른 시장 적용").
"""
from dataclasses import asdict, dataclass

from .collectors import korea, yahoo


@dataclass(frozen=True)
class Params:
    price_floor: float      # C >= x (20% study), C20 >= x (month scans)
    min_volume: float       # shares: V >= x (4% scans), MINV3.1 > x (20% study)
    min_dollar_vol: float   # AVGC20 * AVGV20 >= x (quarter / month / 34-day scans)
    currency: str
    # Exchange daily price limit. A larger close-to-close move can only be an
    # unadjusted corporate action (e.g. Yahoo misses many KRX 액면병합/감자), so the
    # ticker's history before it is dropped from calculations.
    daily_limit: float | None = None


# TC2000 v12.4 values from the original scans.
US = Params(5, 100_000, 250_000, "USD")
# Korea adaptation (not part of the original): $5 -> ₩1,000 "동전주" line (₩7,000 at
# ₩1,400/$ would drop roughly half of KOSDAQ), share-volume line kept at 100,000,
# $250k dollar volume -> ₩350M at ₩1,400/$.
KR = Params(1_000, 100_000, 350_000_000, "KRW", daily_limit=0.30)

UNIVERSES = {
    "yahoo": {"label": "미국 전체 보통주 (현재 상장 종목)", "short": "미국 전체 (현재 상장)", "cal": "NYSE", "params": US,
              "benchmark": "^GSPC", "etf": "SPY", "load": yahoo.universe, "bars": "bars_yahoo"},
    # Nasdaq Composite basis: every NASDAQ-listed common stock in the US universe (ADRs excluded,
    # unlike the official index). Computed from the US bars, no separate download.
    "nasdaq": {"label": "나스닥 상장 보통주 (종합지수 기준)", "short": "나스닥", "cal": "NYSE", "params": US,
               "benchmark": "^IXIC", "etf": "QQQ", "derived_from": "yahoo", "exchange": "NASDAQ", "bars": "bars_yahoo"},
    "kospi": {"label": "코스피 상장 보통주", "short": "코스피", "cal": "XKRX", "params": KR,
              "benchmark": "^KS11", "etf": "069500.KS", "load": lambda: korea.universe("kospi"), "bars": "bars_kospi"},
    "kosdaq": {"label": "코스닥 상장 보통주", "short": "코스닥", "cal": "XKRX", "params": KR,
               "benchmark": "^KQ11", "etf": "229200.KS", "load": lambda: korea.universe("kosdaq"), "bars": "bars_kosdaq"},
}
# Provider-based sources that are always US / NYSE.
SOURCE_CAL = {"public_repo": "NYSE", "massive": "NYSE", **{k: v["cal"] for k, v in UNIVERSES.items()}}


def cal_of(source: str) -> str:
    return SOURCE_CAL.get(source, "NYSE")


def params_of(source: str) -> Params:
    return UNIVERSES[source]["params"] if source in UNIVERSES else US


def benchmark_of(source: str) -> str:
    return UNIVERSES[source]["benchmark"] if source in UNIVERSES else "^GSPC"


def describe() -> dict:
    return {k: {"label": v["label"], "short": v["short"], "cal": v["cal"], "benchmark": v["benchmark"], "etf": v["etf"],
                "params": asdict(v["params"])} for k, v in UNIVERSES.items()}
