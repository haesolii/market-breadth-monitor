"""Community board (DC-style): members (fixed nickname) and guests (nickname + password, shown with
the first two parts of their IP), posts, threaded comments, likes, search, reports and admin tools.

Storage: Postgres (Supabase) on the deployed API, a local SQLite file otherwise — same SQL with %s
placeholders (translated for SQLite). Members sign in with their own username / password (scrypt);
the session is a signed cookie (no session table). Guests edit / delete with their post password.

Abuse controls: per-IP rate limits, guests cannot post links or messenger IDs, a hidden honeypot field,
banned words, IP / member bans, reports. The full IP and time of every post and comment is kept
server-side (never shown) for abuse handling and lawful requests.
"""
import base64
import datetime as dt
import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import threading
import time

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

from . import remote
from .config import DATA

BOARDS = {"free": "자유", "market": "시장 토론", "stock": "종목 토론", "journal": "매매 일지", "notice": "공지"}
ADMIN_ONLY = {"notice"}
PAGE = 20
SECRET = (os.getenv("BOARD_SECRET") or os.getenv("DASHBOARD_PASSWORD") or "local-dev-secret").encode()
ADMINS = {x.strip() for x in os.getenv("BOARD_ADMINS", "").split(",") if x.strip()}
SESSION_DAYS = 30
# (seconds between, max per hour) per IP; members get the lighter limits
LIMITS = {("post", False): (60, 10), ("post", True): (30, 30), ("comment", False): (10, 60), ("comment", True): (5, 200)}
RESERVED = ("운영자", "관리자", "운영진", "admin", "administrator", "moderator")  # nicknames only admins may use
BANNED_WORDS = ["리딩방", "무료 리딩", "수익 보장", "원금 보장", "카톡방", "오픈채팅"]
LINK = re.compile(r"(https?://|www\.|t\.me/|open\.kakao|discord\.gg|bit\.ly|"
                  r"(카톡|카카오톡|텔레|텔레그램|라인|디코)\s*(아이디|id|ID)?\s*[:：]?\s*[A-Za-z0-9_.@-]{3,})", re.I)
TICKER = re.compile(r"\$([A-Za-z]{1,6}(?:\.[A-Z])?|\d{6})\b")
_local = threading.local()
_ready = False

ID = "BIGSERIAL PRIMARY KEY" if remote.ON else "INTEGER PRIMARY KEY AUTOINCREMENT"
SCHEMA = [
    f"""CREATE TABLE IF NOT EXISTS board_users (id {ID}, username TEXT UNIQUE NOT NULL, nickname TEXT UNIQUE NOT NULL,
        pw TEXT NOT NULL, created_at TEXT NOT NULL, banned SMALLINT NOT NULL DEFAULT 0)""",
    f"""CREATE TABLE IF NOT EXISTS board_posts (id {ID}, board TEXT NOT NULL, title TEXT NOT NULL, body TEXT NOT NULL,
        user_id BIGINT, nick TEXT NOT NULL, pw TEXT, ip TEXT NOT NULL, ip_prefix TEXT NOT NULL, created_at TEXT NOT NULL,
        updated_at TEXT, views BIGINT NOT NULL DEFAULT 0, likes BIGINT NOT NULL DEFAULT 0, comments BIGINT NOT NULL DEFAULT 0,
        tickers TEXT NOT NULL DEFAULT '', deleted SMALLINT NOT NULL DEFAULT 0)""",
    "CREATE INDEX IF NOT EXISTS board_posts_list ON board_posts (board, deleted, id)",
    f"""CREATE TABLE IF NOT EXISTS board_comments (id {ID}, post_id BIGINT NOT NULL, parent_id BIGINT, body TEXT NOT NULL,
        user_id BIGINT, nick TEXT NOT NULL, pw TEXT, ip TEXT NOT NULL, ip_prefix TEXT NOT NULL, created_at TEXT NOT NULL,
        deleted SMALLINT NOT NULL DEFAULT 0)""",
    "CREATE INDEX IF NOT EXISTS board_comments_post ON board_comments (post_id, id)",
    "CREATE TABLE IF NOT EXISTS board_likes (post_id BIGINT NOT NULL, voter TEXT NOT NULL, PRIMARY KEY (post_id, voter))",
    f"""CREATE TABLE IF NOT EXISTS board_reports (id {ID}, kind TEXT NOT NULL, target_id BIGINT NOT NULL, reason TEXT NOT NULL,
        ip TEXT NOT NULL, created_at TEXT NOT NULL, handled SMALLINT NOT NULL DEFAULT 0)""",
    "CREATE TABLE IF NOT EXISTS board_bans (target TEXT PRIMARY KEY, until_at TEXT NOT NULL, reason TEXT NOT NULL)",
]


# ---- storage -----------------------------------------------------------------------
class _Tx:
    """One connection + cursor per request; commit on success. SQL uses %s placeholders."""

    def __enter__(self):
        if remote.ON:
            self.con = remote._connect()
        else:
            self.con = sqlite3.connect(DATA / "board.db", timeout=10)
            self.con.row_factory = sqlite3.Row
        self.cur = self.con.cursor()
        return self

    def q(self, sql: str, params=()) -> list[dict]:
        self.cur.execute(sql if remote.ON else sql.replace("%s", "?"), params)
        if self.cur.description is None:
            return []
        cols = [d[0] for d in self.cur.description]
        return [dict(zip(cols, r)) for r in self.cur.fetchall()]

    def one(self, sql: str, params=()) -> dict | None:
        rows = self.q(sql, params)
        return rows[0] if rows else None

    def __exit__(self, exc, *_):
        try:
            if exc is None:
                self.con.commit()
            else:
                self.con.rollback()
        finally:
            self.con.close()


def tx() -> _Tx:
    global _ready
    if not _ready:
        with _Tx() as t:
            for s in SCHEMA:
                t.q(s)
        _ready = True
    return _Tx()


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


# ---- passwords, sessions, IPs -------------------------------------------------------------
def hash_pw(pw: str) -> str:
    salt = secrets.token_bytes(16)
    h = hashlib.scrypt(pw.encode(), salt=salt, n=2**14, r=8, p=1)
    return base64.b64encode(salt + h).decode()


def check_pw(pw: str, stored: str | None) -> bool:
    if not stored:
        return False
    raw = base64.b64decode(stored)
    return hmac.compare_digest(hashlib.scrypt(pw.encode(), salt=raw[:16], n=2**14, r=8, p=1), raw[16:])


def session_token(uid: int, days: int = SESSION_DAYS) -> str:
    body = f"{uid}.{int(time.time()) + days * 86400}"
    return body + "." + hmac.new(SECRET, body.encode(), hashlib.sha256).hexdigest()[:32]


def session_uid(token: str | None) -> int | None:
    try:
        uid, exp, sig = (token or "").split(".")
        ok = hmac.compare_digest(sig, hmac.new(SECRET, f"{uid}.{exp}".encode(), hashlib.sha256).hexdigest()[:32])
        return int(uid) if ok and int(exp) > time.time() else None
    except ValueError:
        return None


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-real-ip") or (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    return fwd or (request.client.host if request.client else "0.0.0.0")


def ip_prefix(ip: str) -> str:
    """DC-style public hint: first two IPv4 octets / first two IPv6 groups."""
    parts = ip.split(".") if "." in ip else ip.split(":")
    return (".".join if "." in ip else ":".join)(parts[:2])


# ---- content rules ------------------------------------------------------------------
def guest_clean(text: str) -> str:
    """Guests cannot post links or messenger IDs (the usual spam / 리딩방 invitation)."""
    return LINK.sub("[링크 제한]", text)


def tickers_of(text: str) -> str:
    """',NVDA,005930,' for $NVDA / $005930 mentions (LIKE-searchable)."""
    found = sorted({m.upper() for m in TICKER.findall(text)})
    return ("," + ",".join(found) + ",") if found else ""


def check_words(text: str) -> None:
    hit = next((w for w in BANNED_WORDS if w in text.replace(" ", "") or w in text), None)
    if hit:
        raise HTTPException(400, f"금지어가 포함되어 있습니다: {hit}")


def check_nick(nick: str, admin: bool) -> None:
    n = re.sub(r"[\s._-]", "", nick).lower()
    if not admin and any(r in n for r in RESERVED):
        raise HTTPException(400, "운영자·관리자로 보이는 닉네임은 쓸 수 없습니다")


def check_rate(t: _Tx, kind: str, ip: str, member: bool) -> None:
    gap, per_hour = LIMITS[(kind, member)]
    table = "board_posts" if kind == "post" else "board_comments"
    hour_ago = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=1)).isoformat(timespec="seconds")
    rows = t.q(f"SELECT created_at FROM {table} WHERE ip = %s AND created_at >= %s ORDER BY created_at DESC", (ip, hour_ago))
    if len(rows) >= per_hour:
        raise HTTPException(429, "한 시간에 쓸 수 있는 개수를 넘었습니다. 잠시 후 다시 시도하세요.")
    if rows and (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(rows[0]["created_at"])).total_seconds() < gap:
        raise HTTPException(429, f"{gap}초에 한 번만 쓸 수 있습니다.")


def check_ban(t: _Tx, ip: str, uid: int | None) -> None:
    targets = [f"ip:{ip}"] + ([f"user:{uid}"] if uid else [])
    for b in t.q(f"SELECT * FROM board_bans WHERE target IN ({','.join(['%s'] * len(targets))})", targets):
        if b["until_at"] > now():
            raise HTTPException(403, f"이용이 제한되었습니다 ({b['until_at'][:10]}까지): {b['reason']}")


# ---- request context ---------------------------------------------------------------------
class Who:
    def __init__(self, t: _Tx, request: Request):
        self.ip = client_ip(request)
        uid = session_uid(request.cookies.get("bd_session"))
        self.user = t.one("SELECT id, username, nickname, banned FROM board_users WHERE id = %s", (uid,)) if uid else None
        self.uid = self.user["id"] if self.user else None
        self.admin = bool(self.user and self.user["username"] in ADMINS)


def _public(row: dict, who: Who | None = None) -> dict:
    """Never expose full IPs or password hashes; guests are shown with their IP prefix."""
    out = {k: v for k, v in row.items() if k not in ("ip", "pw")}
    out["member"] = row.get("user_id") is not None
    if who is not None:
        out["mine"] = bool(who.uid and row.get("user_id") == who.uid)
        if who.admin:
            out["ip"] = row.get("ip")
    return out


# ---- API ----------------------------------------------------------------------------
router = APIRouter(prefix="/api/board")


class SignupIn(BaseModel):
    username: str = Field(min_length=4, max_length=20, pattern=r"^[A-Za-z0-9_]+$")
    nickname: str = Field(min_length=2, max_length=12)
    password: str = Field(min_length=8, max_length=100)
    website: str = ""  # honeypot: humans never see it


class LoginIn(BaseModel):
    username: str
    password: str


class PostIn(BaseModel):
    board: str
    title: str = Field(min_length=1, max_length=100)
    body: str = Field(min_length=1, max_length=20000)
    nick: str = Field("", max_length=12)
    password: str = Field("", max_length=100)
    website: str = ""


class CommentIn(BaseModel):
    body: str = Field(min_length=1, max_length=2000)
    parent_id: int | None = None
    nick: str = Field("", max_length=12)
    password: str = Field("", max_length=100)
    website: str = ""


class PwIn(BaseModel):
    password: str = ""


class ReportIn(BaseModel):
    kind: str = Field(pattern="^(post|comment)$")
    target_id: int
    reason: str = Field(min_length=1, max_length=300)


class BanIn(BaseModel):
    target: str = Field(pattern=r"^(ip|user):.+$")
    days: int = Field(7, ge=1, le=3650)
    reason: str = Field("운영 정책 위반", max_length=200)


def _session(res: Response, uid: int | None) -> None:
    if uid is None:
        res.delete_cookie("bd_session")
    else:
        res.set_cookie("bd_session", session_token(uid), max_age=SESSION_DAYS * 86400, httponly=True, samesite="lax",
                       secure=bool(os.getenv("VERCEL")))


@router.get("/me")
def me(request: Request):
    with tx() as t:
        w = Who(t, request)
        return {"user": w.user and {"username": w.user["username"], "nickname": w.user["nickname"]}, "admin": w.admin,
                "boards": BOARDS, "admin_only": sorted(ADMIN_ONLY)}


@router.post("/signup")
def signup(body: SignupIn, request: Request, response: Response):
    if body.website:
        raise HTTPException(400, "잘못된 요청")
    nick = body.nickname.strip()
    check_words(nick)
    check_nick(nick, body.username in ADMINS)
    with tx() as t:
        check_ban(t, client_ip(request), None)
        if t.one("SELECT id FROM board_users WHERE username = %s OR nickname = %s", (body.username, nick)):
            raise HTTPException(409, "이미 쓰는 아이디 또는 닉네임입니다")
        row = t.one("INSERT INTO board_users (username, nickname, pw, created_at) VALUES (%s, %s, %s, %s) RETURNING id",
                    (body.username, nick, hash_pw(body.password), now()))
    _session(response, row["id"])
    return {"ok": True, "nickname": nick}


@router.post("/login")
def login(body: LoginIn, response: Response):
    with tx() as t:
        u = t.one("SELECT id, pw, banned FROM board_users WHERE username = %s", (body.username,))
    if not u or not check_pw(body.password, u["pw"]):
        raise HTTPException(401, "아이디 또는 비밀번호가 맞지 않습니다")
    if u["banned"]:
        raise HTTPException(403, "이용이 정지된 계정입니다")
    _session(response, u["id"])
    return {"ok": True}


@router.post("/logout")
def logout(response: Response):
    _session(response, None)
    return {"ok": True}


@router.get("/posts")
def posts(board: str = "", q: str = "", ticker: str = "", page: int = Query(1, ge=1, le=10000), best: bool = False):
    where, args = ["deleted = 0"], []
    if board:
        where.append("board = %s")
        args.append(board)
    if q.strip():
        where.append("(LOWER(title) LIKE %s OR LOWER(body) LIKE %s OR LOWER(nick) LIKE %s)")
        args += [f"%{q.strip().lower()}%"] * 3
    if ticker:
        where.append("tickers LIKE %s")
        args.append(f"%,{ticker.upper()},%")
    if best:
        where.append("likes >= 5")
    w = " AND ".join(where)
    with tx() as t:
        total = t.one(f"SELECT COUNT(*) AS n FROM board_posts WHERE {w}", args)["n"]
        rows = t.q(f"SELECT id, board, title, user_id, nick, ip_prefix, created_at, views, likes, comments FROM board_posts "
                   f"WHERE {w} ORDER BY id DESC LIMIT %s OFFSET %s", [*args, PAGE, (page - 1) * PAGE])
        notices = [] if board == "notice" or q or ticker else t.q(
            "SELECT id, board, title, user_id, nick, ip_prefix, created_at, views, likes, comments FROM board_posts "
            "WHERE board = 'notice' AND deleted = 0 ORDER BY id DESC LIMIT 3")
    return {"total": int(total), "page": page, "pages": max(1, -(-int(total) // PAGE)),
            "rows": [_public(r) for r in rows], "notices": [_public(r) for r in notices]}


@router.post("/posts")
def create_post(body: PostIn, request: Request):
    if body.website:
        raise HTTPException(400, "잘못된 요청")
    if body.board not in BOARDS:
        raise HTTPException(400, "없는 게시판입니다")
    with tx() as t:
        w = Who(t, request)
        check_ban(t, w.ip, w.uid)
        if body.board in ADMIN_ONLY and not w.admin:
            raise HTTPException(403, "관리자만 쓸 수 있는 게시판입니다")
        if not w.user and (len(body.nick.strip()) < 2 or len(body.password) < 4):
            raise HTTPException(400, "비회원은 닉네임(2자 이상)과 비밀번호(4자 이상)를 입력하세요")
        if not w.user:
            check_nick(body.nick, False)
        check_rate(t, "post", w.ip, bool(w.user))
        title, text = body.title.strip(), body.body.strip()
        if not w.user:
            title, text = guest_clean(title), guest_clean(text)
        check_words(title + "\n" + text)
        row = t.one("INSERT INTO board_posts (board, title, body, user_id, nick, pw, ip, ip_prefix, created_at, tickers) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
                    (body.board, title, text, w.uid, w.user["nickname"] if w.user else body.nick.strip(),
                     None if w.user else hash_pw(body.password), w.ip, ip_prefix(w.ip), now(), tickers_of(title + " " + text)))
    return {"id": row["id"]}


@router.get("/posts/{pid}")
def get_post(pid: int, request: Request):
    with tx() as t:
        w = Who(t, request)
        p = t.one("SELECT * FROM board_posts WHERE id = %s AND deleted = 0", (pid,))
        if not p:
            raise HTTPException(404, "삭제되었거나 없는 글입니다")
        t.q("UPDATE board_posts SET views = views + 1 WHERE id = %s", (pid,))
        cs = t.q("SELECT * FROM board_comments WHERE post_id = %s ORDER BY id", (pid,))
        liked = bool(t.one("SELECT 1 AS x FROM board_likes WHERE post_id = %s AND voter = %s", (pid, _voter(w))))
    p["views"] += 1
    comments = [_public(c, w) if not c["deleted"] else {"id": c["id"], "parent_id": c["parent_id"], "deleted": 1} for c in cs]
    return {"post": _public(p, w), "comments": comments, "liked": liked, "admin": w.admin}


def _owned(t: _Tx, table: str, rid: int, w: Who, password: str) -> dict:
    row = t.one(f"SELECT * FROM {table} WHERE id = %s AND deleted = 0", (rid,))
    if not row:
        raise HTTPException(404, "삭제되었거나 없는 글입니다")
    ok = w.admin or (row["user_id"] is not None and row["user_id"] == w.uid) or (row["user_id"] is None and check_pw(password, row["pw"]))
    if not ok:
        raise HTTPException(403, "본인 글이 아니거나 비밀번호가 맞지 않습니다")
    return row


@router.put("/posts/{pid}")
def edit_post(pid: int, body: PostIn, request: Request):
    with tx() as t:
        w = Who(t, request)
        row = _owned(t, "board_posts", pid, w, body.password)
        title, text = body.title.strip(), body.body.strip()
        if row["user_id"] is None:
            title, text = guest_clean(title), guest_clean(text)
        check_words(title + "\n" + text)
        t.q("UPDATE board_posts SET title = %s, body = %s, updated_at = %s, tickers = %s WHERE id = %s",
            (title, text, now(), tickers_of(title + " " + text), pid))
    return {"ok": True}


@router.post("/posts/{pid}/delete")
def delete_post(pid: int, body: PwIn, request: Request):
    with tx() as t:
        _owned(t, "board_posts", pid, Who(t, request), body.password)
        t.q("UPDATE board_posts SET deleted = 1 WHERE id = %s", (pid,))
    return {"ok": True}


def _voter(w: Who) -> str:
    return f"user:{w.uid}" if w.uid else f"ip:{w.ip}"


@router.post("/posts/{pid}/like")
def like(pid: int, request: Request):
    with tx() as t:
        w = Who(t, request)
        if not t.one("SELECT id FROM board_posts WHERE id = %s AND deleted = 0", (pid,)):
            raise HTTPException(404, "없는 글입니다")
        if t.one("SELECT 1 AS x FROM board_likes WHERE post_id = %s AND voter = %s", (pid, _voter(w))):
            raise HTTPException(409, "이미 추천했습니다")
        t.q("INSERT INTO board_likes (post_id, voter) VALUES (%s, %s)", (pid, _voter(w)))
        t.q("UPDATE board_posts SET likes = likes + 1 WHERE id = %s", (pid,))
        n = t.one("SELECT likes FROM board_posts WHERE id = %s", (pid,))["likes"]
    return {"likes": int(n)}


@router.post("/posts/{pid}/comments")
def add_comment(pid: int, body: CommentIn, request: Request):
    if body.website:
        raise HTTPException(400, "잘못된 요청")
    with tx() as t:
        w = Who(t, request)
        check_ban(t, w.ip, w.uid)
        if not t.one("SELECT id FROM board_posts WHERE id = %s AND deleted = 0", (pid,)):
            raise HTTPException(404, "삭제되었거나 없는 글입니다")
        if body.parent_id and not t.one("SELECT id FROM board_comments WHERE id = %s AND post_id = %s", (body.parent_id, pid)):
            raise HTTPException(400, "답글 대상 댓글이 없습니다")
        if not w.user and (len(body.nick.strip()) < 2 or len(body.password) < 4):
            raise HTTPException(400, "비회원은 닉네임(2자 이상)과 비밀번호(4자 이상)를 입력하세요")
        if not w.user:
            check_nick(body.nick, False)
        check_rate(t, "comment", w.ip, bool(w.user))
        text = body.body.strip() if w.user else guest_clean(body.body.strip())
        check_words(text)
        t.q("INSERT INTO board_comments (post_id, parent_id, body, user_id, nick, pw, ip, ip_prefix, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (pid, body.parent_id, text, w.uid, w.user["nickname"] if w.user else body.nick.strip(),
             None if w.user else hash_pw(body.password), w.ip, ip_prefix(w.ip), now()))
        t.q("UPDATE board_posts SET comments = comments + 1 WHERE id = %s", (pid,))
    return {"ok": True}


@router.post("/comments/{cid}/delete")
def delete_comment(cid: int, body: PwIn, request: Request):
    with tx() as t:
        row = _owned(t, "board_comments", cid, Who(t, request), body.password)
        t.q("UPDATE board_comments SET deleted = 1 WHERE id = %s", (cid,))
        t.q("UPDATE board_posts SET comments = comments - 1 WHERE id = %s", (row["post_id"],))
    return {"ok": True}


@router.post("/report")
def report(body: ReportIn, request: Request):
    with tx() as t:
        t.q("INSERT INTO board_reports (kind, target_id, reason, ip, created_at) VALUES (%s, %s, %s, %s, %s)",
            (body.kind, body.target_id, body.reason.strip(), client_ip(request), now()))
    return {"ok": True}


def _admin(t: _Tx, request: Request) -> Who:
    w = Who(t, request)
    if not w.admin:
        raise HTTPException(403, "관리자만 할 수 있습니다")
    return w


@router.get("/admin/reports")
def admin_reports(request: Request):
    with tx() as t:
        _admin(t, request)
        return t.q("SELECT * FROM board_reports WHERE handled = 0 ORDER BY id DESC LIMIT 200")


@router.post("/admin/reports/{rid}/done")
def admin_report_done(rid: int, request: Request):
    with tx() as t:
        _admin(t, request)
        t.q("UPDATE board_reports SET handled = 1 WHERE id = %s", (rid,))
    return {"ok": True}


@router.post("/admin/ban")
def admin_ban(body: BanIn, request: Request):
    until = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=body.days)).isoformat(timespec="seconds")
    with tx() as t:
        _admin(t, request)
        t.q("DELETE FROM board_bans WHERE target = %s", (body.target,))
        t.q("INSERT INTO board_bans (target, until_at, reason) VALUES (%s, %s, %s)", (body.target, until, body.reason))
    return {"ok": True, "until": until}
