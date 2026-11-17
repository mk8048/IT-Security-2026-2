import hashlib
import os
import re
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import (Blueprint, abort, g, make_response, redirect,
                   render_template, request)

import db

auth_bp = Blueprint("auth", __name__)

TRUSTED_GATEWAY = os.environ["TRUSTED_GATEWAY"]
COOKIE_NAME = "session_token"
SESSION_HOURS = 2


def get_db():
    """요청당 하나의 연결을 g에 보관한다."""
    if "db" not in g:
        g.db = db.connect()
    return g.db


@auth_bp.teardown_app_request
def close_db(exc=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _now() -> str:
    # SQLite datetime('now')와 같은 형식(UTC)이라 문자열 비교가 가능하다.
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def client_ip() -> str:
    # 앱은 gateway 뒤에 있으므로 remote_addr은 gateway IP이다.
    # nginx가 X-Forwarded-For를 $remote_addr 단일 값으로 덮어쓰고 gateway가
    # 클라이언트 제공 값을 제거하므로, 신뢰하는 gateway에서 온 요청에 한해 이 값을 쓴다.
    if request.remote_addr == TRUSTED_GATEWAY:
        forwarded = request.headers.get("X-Forwarded-For", "").strip()
        if forwarded:
            return forwarded
    return request.remote_addr or ""


# ---------- 세션 검증 (모든 요청 전에 실행) ----------
@auth_bp.before_app_request
def load_user():
    g.user = None
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return
    # 세션 검증은 매개변수 바인딩으로 안전하게 구현
    g.user = get_db().execute(
        """SELECT u.id, u.username, u.name, u.role
           FROM sessions s JOIN users u ON u.id = s.user_id
           WHERE s.token_hash = ?
             AND s.revoked_at IS NULL
             AND s.expires_at > ?""",
        (_hash(token), _now()),
    ).fetchone()


# ---------- 데코레이터 ----------
def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            return redirect("/login")
        return view(*args, **kwargs)
    return wrapped


def role_required(*roles):
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            # 역할은 DB(users.role)에서 읽은 g.user 기준으로만 판단
            if g.user["role"] not in roles:
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


# ---------- 로그인 ----------
@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")

    username = request.form.get("username", "")
    password = request.form.get("password", "")
    conn = get_db()

    # [의도적 취약점] SQL Injection: 문자열 이어붙이기 + 평문 비밀번호 비교
    query = (f"SELECT id, username, role FROM users "
             f"WHERE username='{username}' AND password='{password}'")
    try:
        user = conn.execute(query).fetchone()
    except sqlite3.Error as e:
        # [의도적 취약점] DB 에러와 쿼리를 그대로 노출 (error-based 실습용)
        return render_template("login.html", error=f"DB error: {e}\n{query}"), 500

    if user is None:
        return render_template("login.html",
                               error="아이디 또는 비밀번호가 올바르지 않습니다."), 401

    # 세션 발급: 원본 토큰은 쿠키에만, DB에는 해시만 저장
    token = secrets.token_urlsafe(32)
    expires = (datetime.now(timezone.utc) + timedelta(hours=SESSION_HOURS)).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        "INSERT INTO sessions (token_hash, user_id, source_ip, expires_at) "
        "VALUES (?, ?, ?, ?)",
        (_hash(token), user["id"], client_ip(), expires),
    )
    conn.commit()

    resp = make_response(redirect("/"))
    resp.set_cookie(COOKIE_NAME, token, httponly=True, samesite="Lax",
                    max_age=SESSION_HOURS * 3600)
    return resp


# ---------- 회원가입 ----------
USERNAME_RE = re.compile(r"[A-Za-z0-9_]{3,20}")


@auth_bp.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "GET":
        return render_template("signup.html")

    username = request.form.get("username", "")
    password = request.form.get("password", "")
    name = request.form.get("name", "").strip()

    error = None
    if not USERNAME_RE.fullmatch(username):
        error = "아이디는 영문·숫자·밑줄 3~20자여야 합니다."
    elif not 4 <= len(password) <= 72:
        error = "비밀번호는 4~72자여야 합니다."
    elif not 1 <= len(name) <= 30:
        error = "이름은 1~30자여야 합니다."
    if error:
        return render_template("signup.html", error=error), 400

    conn = get_db()
    try:
        # 역할은 요청값을 받지 않고 서버에서 student로 고정한다(권한 상승 방지).
        # 교수·관리자 계정은 시드 데이터나 관리자 기능으로만 만든다.
        conn.execute(
            "INSERT INTO users (username, password, name, role) VALUES (?, ?, ?, 'student')",
            (username, password, name),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        return render_template("signup.html", error="이미 사용 중인 아이디입니다."), 409
    return redirect("/login")


# ---------- 로그아웃 ----------
@auth_bp.route("/logout", methods=["POST"])
def logout():
    token = request.cookies.get(COOKIE_NAME)
    if token and g.user is not None:
        conn = get_db()
        conn.execute(
            "UPDATE sessions SET revoked_at=?, revoked_by=?, revoke_reason='logout' "
            "WHERE token_hash=? AND revoked_at IS NULL",
            (_now(), g.user["id"], _hash(token)),
        )
        conn.commit()
    resp = make_response(redirect("/login"))
    resp.delete_cookie(COOKIE_NAME)
    return resp