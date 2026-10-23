import datetime as dt

import pandas as pd
from fastapi.testclient import TestClient

from app import main, store


def test_api_no_data_and_errors():
    c = TestClient(main.app)  # no context manager -> auto-refresh thread not started
    assert c.get("/api/breadth20").status_code == 404              # no data yet -> explicit 404, never fake numbers
    assert c.get("/api/research").status_code == 404
    assert c.post("/api/reference", json={"date": "2024-01-02", "metric": "nope", "value": 1}).status_code == 400


def test_api_real_rows():
    d = [dt.date(2024, 1, 2) + dt.timedelta(days=i) for i in range(30)]
    store.upsert("breadth20", pd.DataFrame({"date": d, "bull": 1.0, "bear": range(30), "source": "yahoo"}), ["source", "date"])
    store.upsert("indices", pd.DataFrame({"date": d, "symbol": "^GSPC", "close": [100.0 + i for i in range(30)]}), ["symbol", "date"])
    c = TestClient(main.app)
    j = c.get("/api/breadth20").json()
    assert j["source"] == "yahoo" and len(j["rows"]) == 30
    r = c.get("/api/research?metric=bear&threshold=25").json()
    assert r["n_events"] == 5 and r["stats"]["1"]["n"] == 4
    assert c.get("/api/compare?metric=bear_pct").json()["series"] == {}       # no eligible counts -> no ratio
    assert c.get("/api/compare?metric=nope").status_code == 400
    day = c.get(f"/api/day?date={d[10]}").json()
    assert day["breadth20"]["yahoo"]["bear_chg5"] == 5 and "r1" not in str(day)  # no forward returns


def test_world_config_rejects_bad_text():
    c = TestClient(main.app)
    bad = rb'[{"symbol": "^GSPC", "name": "\udceb", "region": "x"}]'  # lone surrogate, as a cp949 pipe produces
    assert c.post("/api/world/config", content=bad, headers={"Content-Type": "application/json"}).status_code == 400
    assert c.post("/api/world/config", json=[{"symbol": " ", "name": "x"}]).status_code == 400


def test_password_gate(monkeypatch):
    import hashlib
    token = hashlib.sha256(b"pw:mb").hexdigest()
    monkeypatch.setattr(main, "_TOKEN", token)
    c = TestClient(main.app)
    assert c.get("/api/status").status_code == 401
    c.cookies.set("mb_auth", "wrong")
    assert c.get("/api/status").status_code == 401
    c.cookies.set("mb_auth", token)
    assert c.get("/api/status").status_code == 200


def test_login_endpoint(monkeypatch):
    import hashlib
    monkeypatch.setattr(main, "_PW", "pw")
    monkeypatch.setattr(main, "_TOKEN", hashlib.sha256(b"pw:mb").hexdigest())
    c = TestClient(main.app, follow_redirects=False)
    bad = c.post("/api/login", content="password=nope&next=/monitor", headers={"Content-Type": "application/x-www-form-urlencoded"})
    assert bad.status_code == 303 and bad.headers["location"].startswith("/login?error=1") and "mb_auth" not in bad.cookies
    ok = c.post("/api/login", content="password=pw&next=//evil.com", headers={"Content-Type": "application/x-www-form-urlencoded"})
    assert ok.status_code == 303 and ok.headers["location"] == "/" and ok.cookies.get("mb_auth") == main._TOKEN


def test_cdn_cache_headers(monkeypatch):
    """Deployed site: successful GETs are CDN-cacheable per auth cookie; 401s, visits and writes are not."""
    import hashlib
    token = hashlib.sha256(b"pw:mb").hexdigest()
    monkeypatch.setattr(main, "_TOKEN", token)
    monkeypatch.setattr(main.remote, "ON", True)
    monkeypatch.setattr(main.usage, "record_visit", lambda r: None)
    if not any(getattr(rt, "path", "") == "/api/_cdn_probe" for rt in main.app.routes):
        main.app.add_api_route("/api/_cdn_probe", lambda: {"ok": True})  # no store access (remote.ON would hit Supabase)
    c = TestClient(main.app)
    key = {"X-Mb-Key": token}
    assert c.get("/api/_cdn_probe", headers=key).status_code == 401  # key without cookie: no data from the origin
    c.cookies.set("mb_auth", token)
    r = c.get("/api/_cdn_probe")  # cookie only: served, not cacheable, readable key cookie handed out
    assert r.status_code == 200 and "Vercel-CDN-Cache-Control" not in r.headers and "mb_key" in r.headers.get("set-cookie", "")
    assert "Vercel-CDN-Cache-Control" not in c.get("/api/_cdn_probe", headers={"X-Mb-Key": "wrong"}).headers
    r = c.get("/api/_cdn_probe", headers=key)
    assert r.headers["Vercel-CDN-Cache-Control"].startswith("max-age=60") and r.headers["Vary"] == "X-Mb-Key"
    assert "set-cookie" not in r.headers  # a Set-Cookie would make it uncacheable
    assert "Vercel-CDN-Cache-Control" not in c.get("/api/visit", headers=key).headers


def test_new_endpoints_empty_and_stock():
    c = TestClient(main.app)
    assert c.get("/api/flows").json()["dates"] == []
    assert c.get("/api/dart").json()["rows"] == []
    assert c.get("/api/stock?ticker=NOPE").status_code == 404
    store.write("sector_map", pd.DataFrame({"market": "kospi", "ticker": ["005930", "000660"], "name": ["삼성전자", "SK하이닉스"],
                                            "exchange": "KOSPI", "sector": "반도체", "industry": "", "size": [3.0, 1.0], "close": 1.0,
                                            "r1d": [1.0, 2.0], "r1w": None, "r1m": None, "r3m": None, "r1y": None, "ytd": None,
                                            "date": dt.date(2026, 10, 23)}))
    assert [h["ticker"] for h in c.get("/api/stock/search?q=삼성").json()] == ["005930"]
    d = c.get("/api/stock?ticker=005930").json()
    assert d["ranks"]["r1d"] == {"rank": 2, "of": 2, "mkt_pctile": 50.0} and len(d["peers"]) == 2 and d["flow"] == {"dates": []}


def test_leadlag_endpoint():
    d = [dt.date(2024, 1, 1) + dt.timedelta(days=i) for i in range(120)]
    store.upsert("market_monitor_daily", pd.DataFrame({"date": d, "source": "yahoo", "t2108": [float(i % 30) for i in range(120)]}), ["source", "date"])
    store.upsert("indices", pd.DataFrame({"date": d, "symbol": "^GSPC", "close": [100.0 + (i % 17) for i in range(120)]}), ["symbol", "date"])
    c = TestClient(main.app)
    j = c.get("/api/research/leadlag?source=yahoo&metric=t2108&days=0").json()
    assert j["lags"][0] == -20 and len(j["corr"]) == 41 and len(j["roll"]["r0"]) == len(j["dates"])
    assert c.get("/api/research/leadlag?source=yahoo&metric=nope").status_code == 400


def test_remote_decimals_handles_all_null_columns():
    from decimal import Decimal

    from app import remote
    df = remote._decimals(pd.DataFrame({"a": [None, None], "b": [Decimal("1.5"), None], "c": ["x", "y"]}))
    assert df["b"].tolist()[0] == 1.5 and df["a"].isna().all() and df["c"].tolist() == ["x", "y"]
