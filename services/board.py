import os
import sqlite3
from urllib.parse import quote

from flask import Blueprint, abort, g, redirect, render_template, request

from db import FILES_DIR
from auth import get_db, login_required

board_bp = Blueprint("board", __name__)


# ---------- 목록 ----------
@board_bp.route("/board")
@login_required
def board_list():
    rows = get_db().execute(
        """SELECT p.id, p.title, u.name AS author, p.created_at
           FROM posts p JOIN users u ON u.id = p.author_id
           ORDER BY p.id DESC"""
    ).fetchall()
    return render_template("board.html", rows=rows)


# ---------- 상세 ----------
@board_bp.route("/board/<int:post_id>")
@login_required
def board_detail(post_id):
    post = get_db().execute(
        """SELECT p.id, p.title, p.content, u.name AS author, p.created_at
           FROM posts p JOIN users u ON u.id = p.author_id
           WHERE p.id = ?""",
        (post_id,),
    ).fetchone()
    if post is None:
        abort(404)
    return render_template("post.html", post=post)


# ---------- 작성 ----------
@board_bp.route("/board/write", methods=["GET", "POST"])
@login_required
def board_write():
    if request.method == "GET":
        return render_template("board_write.html")

    title = request.form.get("title", "").strip()
    content = request.form.get("content", "").strip()
    if not title or not content:
        return render_template("board_write.html", title = title, content = content,
                               error="제목과 내용을 입력하세요."), 400

    attach_html = ""
    saved_path = None
    f = request.files.get("file")
    if f is not None and f.filename:
        # [의도적 취약점] 파일명·확장자 검증 없음, 경로 이어붙임, 덮어쓰기 허용
        original = f.filename
        saved_path = FILES_DIR + "/" + original
        try:
            f.save(saved_path)
        except OSError as e:
            return render_template("board_write.html", title=title, content=content,
                                   error=f"업로드 실패: {e}"), 500
        # [의도적 취약점] 파일명을 이스케이프 없이 본문에 삽입
        attach_html = (f'<br><br>첨부파일: '
                       f'<a href="/files/download?name={quote(original)}">{original}</a>')

    conn = get_db()
    try:
        # 저장은 매개변수 바인딩으로 안전하게 (취약점은 출력 쪽에만 둔다)
        cur = conn.execute(
            "INSERT INTO posts (author_id, title, content) VALUES (?, ?, ?)",
            (g.user["id"], title, content + attach_html),
        )
        conn.commit()
    except sqlite3.Error:
        if saved_path:
            os.remove(saved_path)   # DB 기록 실패 시 파일도 되돌림
        raise
    return redirect(f"/board/{cur.lastrowid}")