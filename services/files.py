import mimetypes
import sqlite3

from flask import Blueprint, Response, abort, g, redirect, render_template, request

from auth import get_db, login_required, role_required
from db import FILES_DIR

files_bp = Blueprint("files", __name__)


# ---------- 목록 ----------
@files_bp.route("/files")
@login_required
def file_list():
    rows = get_db().execute(
        """SELECT f.id, f.filename, f.description, u.name AS uploader
           FROM files f LEFT JOIN users u ON u.id = f.uploaded_by
           ORDER BY f.id"""
    ).fetchall()
    return render_template("files.html", rows=rows)


# ---------- 다운로드 ----------
@files_bp.route("/files/download")
@login_required
def file_download():
    name = request.args.get("name", "")
    if not name:
        abort(400)

    # [의도적 취약점] Path Traversal: 경로를 검증 없이 이어붙임
    path = FILES_DIR + "/" + name
    try:
        with open(path, "rb") as f:
            data = f.read()
    except FileNotFoundError:
        abort(404)
    except OSError as e:
        # [의도적 취약점] 에러와 실제 경로 노출
        return f"파일을 읽을 수 없습니다: {e}\n경로: {path}", 500

    # [의도적 취약점] 확장자 기반 Content-Type으로 inline 서빙
    # → 업로드한 .html/.svg가 사이트 도메인에서 실행됨(저장형 XSS)
    mime = mimetypes.guess_type(name)[0] or "text/plain"
    return Response(data, mimetype=mime)

# ---------- 업로드 ----------
@files_bp.route("/files", methods=["POST"])
@role_required("professor", "admin")
def file_upload():
    f = request.files.get("file")
    description = request.form.get("description", "")
    if f is None or not f.filename:
        abort(400)

    # [의도적 취약점] 파일명·확장자 검증 없음, 덮어쓰기 허용, 경로 이어붙임
    filename = f.filename
    path = FILES_DIR + "/" + filename

    conn = get_db()
    try:
        f.save(path)
        # [의도적 취약점] SQL Injection: 파일명과 설명을 이어붙임
        conn.execute(
            f"INSERT OR IGNORE INTO files (filename, description, uploaded_by) "
            f"VALUES ('{filename}', '{description}', {g.user['id']})"
        )
        conn.commit()
    except (OSError, sqlite3.Error) as e:
        conn.rollback()
        # [의도적 취약점] 에러 노출
        return f"업로드 실패: {e}", 500
    return redirect("/files")