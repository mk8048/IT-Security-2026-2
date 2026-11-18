from flask import Blueprint, Response, abort, render_template, request

from auth import get_db, login_required
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
    # (send_from_directory / secure_filename을 쓰지 않는다)
    path = FILES_DIR + "/" + name
    try:
        with open(path, "rb") as f:
            data = f.read()
    except FileNotFoundError:
        abort(404)
    except OSError as e:
        # [의도적 취약점] 에러와 실제 경로 노출
        return f"파일을 읽을 수 없습니다: {e}\n경로: {path}", 500

    return Response(data, mimetype="text/plain; charset=utf-8")