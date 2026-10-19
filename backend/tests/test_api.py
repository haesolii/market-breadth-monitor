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
    assert "Vercel-CDN-Cache-Control" not in c.get("/api/_cdn_probe").headers  # 401
    c.cookies.set("mb_auth", token)
    r = c.get("/api/_cdn_probe")
    assert r.status_code == 200 and r.headers["Vercel-CDN-Cache-Control"].startswith("max-age=60") and r.headers["Vary"] == "Cookie"
    assert "Vercel-CDN-Cache-Control" not in c.get("/api/visit").headers
