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
