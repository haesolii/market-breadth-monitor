"""Self-computed universes: which stocks, which exchange calendar, which
thresholds, which benchmark. The indicator formulas are identical for all of
them; only the money/volume thresholds are adapted per market (see
docs/indicator-definitions.md, "다른 시장 적용").
"""
from dataclasses import asdict, dataclass

from .collectors import crypto, korea, yahoo


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
    # 24/7 markets: a longer gap in a ticker's daily bars is a halt (often a redenomination).
    max_gap_days: int | None = None
    # Coins have no meaningful share count: when set, the 4% scans need day turnover (C*V) >= [0]
    # and the 20% study a 3-preceding-day minimum turnover > [1], instead of the share-volume line.
    min_turnover: tuple[float, float] | None = None


# TC2000 v12.4 values from the original scans.
US = Params(5, 100_000, 250_000, "USD")
# Korea adaptation (not part of the original): $5 -> ₩1,000 "동전주" line (₩7,000 at
# ₩1,400/$ would drop roughly half of KOSDAQ), share-volume line kept at 100,000,
# $250k dollar volume -> ₩350M at ₩1,400/$.
KR = Params(1_000, 100_000, 350_000_000, "KRW", daily_limit=0.30)
# Crypto adaptation: no price floor or share-count line (a coin's unit is arbitrary: 1 BTC vs
# 1 PEPE); 20-day turnover >= 1M USDT (4x the US $250k: 24/7 trading). The share-volume line
# becomes a turnover line set so the same share of moves passes as in the US (2026-10, 60 sessions:
# US 100k shares keeps 76% of 4% moves / 67% of 20% candidates; 500k / 300k USDT keep 79% / 64%).
CRYPTO = Params(0, 0, 1_000_000, "USDT", max_gap_days=2, min_turnover=(500_000, 300_000))

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
    # Binance spot USDT pairs; delisted pairs keep their history (delisted_history).
    "crypto": {"label": "크립토 (바이낸스 USDT 현물, 상장폐지 포함)", "short": "크립토", "cal": "CRYPTO", "params": CRYPTO,
               "benchmark": "BTC-USD", "etf": "BTC-USD", "load": crypto.universe, "fetch": crypto.fetch,
               "delisted_history": True, "bars": "bars_crypto"},
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
