from flask import Blueprint, abort, g, redirect, render_template, request

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
@board_bp.route("/board", methods=["POST"])
@login_required
def board_create():
    title = request.form.get("title", "").strip()
    content = request.form.get("content", "").strip()
    if not title or not content:
        abort(400)

    conn = get_db()
    # 저장은 매개변수 바인딩으로 안전하게 (취약점은 출력 쪽에만 둔다)
    cur = conn.execute(
        "INSERT INTO posts (author_id, title, content) VALUES (?, ?, ?)",
        (g.user["id"], title, content),
    )
    conn.commit()
    return redirect(f"/board/{cur.lastrowid}")