from fastapi.testclient import TestClient

from app import board, main


def _c(ip="1.2.3.4"):
    c = TestClient(main.app)
    c.headers["x-real-ip"] = ip
    return c


def test_guest_post_links_hidden_and_password_edit(monkeypatch):
    monkeypatch.setattr(board, "LIMITS", {k: (0, 1000) for k in board.LIMITS})
    c = _c()
    r = c.post("/api/board/posts", json={"board": "free", "title": "첫 글 $NVDA", "body": "텔레그램 아이디: abcd1234 https://x.y 보세요",
                                        "nick": "개미", "password": "1234"})
    pid = r.json()["id"]
    p = c.get(f"/api/board/posts/{pid}").json()["post"]
    assert "[링크 제한]" in p["body"] and "https" not in p["body"] and p["ip_prefix"] == "1.2" and "ip" not in p and "pw" not in p
    assert c.get("/api/board/posts?ticker=NVDA").json()["total"] == 1
    assert c.post(f"/api/board/posts/{pid}/delete", json={"password": "wrong"}).status_code == 403
    assert c.post(f"/api/board/posts/{pid}/delete", json={"password": "1234"}).status_code == 200
    assert c.get(f"/api/board/posts/{pid}").status_code == 404


def test_member_comments_likes_and_limits(monkeypatch):
    monkeypatch.setattr(board, "LIMITS", {k: (0, 1000) for k in board.LIMITS})
    m = _c("5.6.7.8")
    assert m.post("/api/board/signup", json={"username": "trader1", "nickname": "고정닉", "password": "password1"}).status_code == 200
    assert m.post("/api/board/signup", json={"username": "trader2", "nickname": "고정닉", "password": "password1"}).status_code == 409
    assert m.get("/api/board/me").json()["user"]["nickname"] == "고정닉"
    pid = m.post("/api/board/posts", json={"board": "market", "title": "시장 이야기", "body": "링크 https://ok.example"}).json()["id"]
    post = m.get(f"/api/board/posts/{pid}").json()["post"]
    assert post["member"] and post["mine"] and "https://ok.example" in post["body"]       # members may link
    assert m.post(f"/api/board/posts/{pid}/like").json()["likes"] == 1
    assert m.post(f"/api/board/posts/{pid}/like").status_code == 409                       # one vote each
    g = _c("9.9.9.9")
    assert g.post(f"/api/board/posts/{pid}/comments", json={"body": "동의", "nick": "유동", "password": "9999"}).status_code == 200
    assert g.post(f"/api/board/posts/{pid}/comments", json={"body": "익명", "nick": "", "password": ""}).status_code == 400
    d = g.get(f"/api/board/posts/{pid}").json()
    assert d["post"]["comments"] == 1 and d["comments"][0]["nick"] == "유동" and not d["post"]["mine"]
    assert m.post("/api/board/posts", json={"board": "notice", "title": "공지", "body": "x"}).status_code == 403  # admins only
    assert g.post("/api/board/posts", json={"board": "free", "title": "무료 리딩방 모집", "body": "x", "nick": "광고", "password": "1234"}).status_code == 400
    monkeypatch.setattr(board, "LIMITS", {k: (60, 1000) for k in board.LIMITS})
    assert g.post(f"/api/board/posts/{pid}/comments", json={"body": "또", "nick": "유동", "password": "9999"}).status_code == 429


def test_session_token_tamper():
    tok = board.session_token(7)
    assert board.session_uid(tok) == 7
    assert board.session_uid(tok.replace("7.", "8.", 1)) is None and board.session_uid("x") is None


def test_reserved_nicknames(monkeypatch):
    monkeypatch.setattr(board, "LIMITS", {k: (0, 1000) for k in board.LIMITS})
    monkeypatch.setattr(board, "ADMINS", {"boss1"})
    c = _c("7.7.7.7")
    assert c.post("/api/board/signup", json={"username": "fake01", "nickname": "운영 자", "password": "password1"}).status_code == 400
    assert c.post("/api/board/posts", json={"board": "free", "title": "t", "body": "b", "nick": "관리자봇", "password": "1234"}).status_code == 400
    assert c.post("/api/board/signup", json={"username": "boss1", "nickname": "운영자", "password": "password1"}).status_code == 200
    assert c.get("/api/board/me").json()["admin"] is True


def test_list_cache_cleared_by_writes(monkeypatch):
    monkeypatch.setattr(board, "LIMITS", {k: (0, 1000) for k in board.LIMITS})
    c = _c("8.8.8.8")
    before = c.get("/api/board/posts?board=journal").json()["total"]
    c.post("/api/board/posts", json={"board": "journal", "title": "일지", "body": "b", "nick": "기록", "password": "1234"})
    assert c.get("/api/board/posts?board=journal").json()["total"] == before + 1     # not the cached page


def test_admin_tools_only_for_admins(monkeypatch):
    monkeypatch.setattr(board, "LIMITS", {k: (0, 1000) for k in board.LIMITS})
    monkeypatch.setattr(board, "ADMINS", {"boss2"})
    guest, member, admin = _c("3.3.3.1"), _c("3.3.3.2"), _c("3.3.3.3")
    member.post("/api/board/signup", json={"username": "plain1", "nickname": "일반", "password": "password1"})
    admin.post("/api/board/signup", json={"username": "boss2", "nickname": "운영자2", "password": "password1"})
    pid = member.post("/api/board/posts", json={"board": "free", "title": "t", "body": "b"}).json()["id"]
    for c in (guest, member):
        assert c.get("/api/board/admin/reports").status_code == 403
        assert c.post("/api/board/admin/ban", json={"target": "ip:1.2.3.4"}).status_code == 403
        assert "ip" not in c.get(f"/api/board/posts/{pid}").json()["post"]                 # full IPs never shown
    assert admin.get("/api/board/admin/reports").status_code == 200 and admin.get("/api/board/me").json()["admin"]
    assert admin.get(f"/api/board/posts/{pid}").json()["post"]["ip"] == "3.3.3.2"


def test_ids_and_nicknames_unique_ignoring_case_and_spaces(monkeypatch):
    monkeypatch.setattr(board, "LIMITS", {k: (0, 1000) for k in board.LIMITS})
    c = _c("4.4.4.4")
    s = lambda u, n: c.post("/api/board/signup", json={"username": u, "nickname": n, "password": "password1"}).status_code  # noqa: E731
    assert s("Trader9", "주식왕") == 200
    assert s("TRADER9", "다른닉") == 409 and s("trader10", "주식 왕") == 409               # case / spaces don't make a new name
    assert c.post("/api/board/login", json={"username": "trader9", "password": "password1"}).status_code == 200
    g = _c("4.4.4.5")
    r = g.post("/api/board/posts", json={"board": "free", "title": "t", "body": "b", "nick": "주식 왕", "password": "1234"})
    assert r.status_code == 400                                                              # guests can't wear a member's name


def test_owner_only_changes_on_deployed_site(monkeypatch):
    """On the public deployed API a visitor cannot change shared settings or anyone's watchlist."""
    from app import main, remote
    monkeypatch.setattr(remote, "ON", True)
    monkeypatch.setattr(board, "member", lambda request: (None, False))
    c = _c("6.6.6.6")
    assert c.post("/api/watchlist", json=[]).status_code == 401
    assert c.post("/api/reference", json={"date": "2024-01-02", "metric": "bear", "value": 1}).status_code == 403
    assert c.delete("/api/reference?date=2024-01-02&metric=bear").status_code == 403
    assert c.post("/api/world/config", json=[]).status_code == 403
    assert c.get("/api/watchlist").json()["who"] == "guest"
    assert c.get("/api/news/watch").json() == []
    monkeypatch.setattr(board, "member", lambda request: (None, True))
    assert main._is_owner(None) is True


def test_members_have_their_own_watchlists():
    board.watch_set(101, [{"ticker": "NVDA", "market": "yahoo", "name": "NVIDIA"}])
    board.watch_set(102, [{"ticker": "005930", "market": "kospi", "name": "삼성전자"}, {"ticker": "AAPL", "market": "yahoo", "name": "Apple"}])
    assert [x["ticker"] for x in board.watch_get(101)] == ["NVDA"]
    assert [x["ticker"] for x in board.watch_get(102)] == ["005930", "AAPL"]          # order kept, lists separate
    board.watch_set(101, [])
    assert board.watch_get(101) == [] and len(board.watch_get(102)) == 2
