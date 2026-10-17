import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


def http_session(pool: int = 16) -> requests.Session:
    """Session with retries + exponential backoff on 429/5xx and connection errors."""
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (breadth personal research)"
    retry = Retry(total=4, backoff_factor=1.5, status_forcelist=(429, 500, 502, 503, 504),
                  allowed_methods=("GET",), respect_retry_after_header=True)
    s.mount("https://", HTTPAdapter(max_retries=retry, pool_maxsize=pool))
    return s
