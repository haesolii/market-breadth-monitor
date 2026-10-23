import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

# Vercel functions can only write to /tmp (the deployed API keeps no data files anyway).
DATA = Path(os.getenv("DATA_DIR") or ("/tmp/data" if os.getenv("VERCEL") else ROOT / "data"))
DATA.mkdir(parents=True, exist_ok=True)

MASSIVE_API_KEY = os.getenv("MASSIVE_API_KEY", "").strip()
MASSIVE_RATE_PER_MIN = float(os.getenv("MASSIVE_RATE_PER_MIN", "5"))
MASSIVE_START = os.getenv("MASSIVE_START", "2024-11-01")
YAHOO_SCANNER = os.getenv("YAHOO_SCANNER", "1") == "1"
KR_SCANNER = os.getenv("KR_SCANNER", "1") == "1"
CRYPTO_SCANNER = os.getenv("CRYPTO_SCANNER", "1") == "1"
YAHOO_HISTORY = os.getenv("YAHOO_HISTORY", "5y")
REFRESH_INTERVAL_MIN = float(os.getenv("REFRESH_INTERVAL_MIN", "15"))
DART_API_KEY = os.getenv("DART_API_KEY", "").strip()  # opendart.fss.or.kr (free): 잠정실적 disclosures
