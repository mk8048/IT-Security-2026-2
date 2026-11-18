import sqlite3

from flask import Blueprint, abort, g, redirect, render_template, request

from auth import client_ip, get_db, role_required

grades_bp = Blueprint("grades", __name__)


def _snapshot(conn):
    return {r["id"]: r["score"] for r in conn.execute("SELECT id, score FROM grades")}


# ---------- 학생: 본인 성적 ----------
@grades_bp.route("/grades")
@role_required("student")
def my_grades():
    rows = get_db().execute(
        """SELECT gr.id, c.code, c.title, gr.score, gr.updated_at
           FROM grades gr JOIN courses c ON c.id = gr.course_id
           WHERE gr.student_id = ?""",
        (g.user["id"],),
    ).fetchall()
    return render_template("grades.html", rows=rows)

# ---------- 교수: 담당 과목 목록 ----------
@grades_bp.route("/courses")
@role_required("professor")
def course_index():
    if not g.nav_courses:
        return render_template("course_grades.html", course=None, rows=[])
    return redirect(f"/courses/{g.nav_courses[0]['id']}/grades")

# ---------- 교수: 담당 과목 성적 목록 ----------
@grades_bp.route("/courses/<int:course_id>/grades")
@role_required("professor")
def course_grades(course_id):
    conn = get_db()
    course = conn.execute(
        "SELECT id, code, title FROM courses WHERE id = ? AND professor_id = ?",
        (course_id, g.user["id"]),
    ).fetchone()
    if course is None:
        abort(403)   # 담당 과목이 아니면 거부

    rows = conn.execute(
        """SELECT gr.id, u.username, u.name, gr.score, gr.updated_at
           FROM grades gr JOIN users u ON u.id = gr.student_id
           WHERE gr.course_id = ?""",
        (course_id,),
    ).fetchall()
    return render_template("course_grades.html", course=course, rows=rows)


# ---------- 교수: 성적 수정 ----------
@grades_bp.route("/grades/<int:grade_id>", methods=["POST"])
@role_required("professor")
def update_grade(grade_id):
    conn = get_db()

    # 담당 과목의 성적인지 확인 (이 검사는 안전하게 구현)
    target = conn.execute(
        """SELECT gr.id, gr.course_id
           FROM grades gr JOIN courses c ON c.id = gr.course_id
           WHERE gr.id = ? AND c.professor_id = ?""",
        (grade_id, g.user["id"]),
    ).fetchone()
    if target is None:
        abort(403)

    score = request.form.get("score", "")
    before = _snapshot(conn)

    # [의도적 취약점] SQL Injection: score를 검증 없이 이어붙임
    sql = (f"UPDATE grades SET score = {score}, updated_at = datetime('now') "
           f"WHERE id = {grade_id}")
    try:
        conn.execute(sql)

        # 실제로 바뀐 모든 행을 이력에 기록 (주입으로 여러 행이 바뀌어도 남도록)
        after = _snapshot(conn)
        for gid, new_score in after.items():
            if before.get(gid) != new_score:
                conn.execute(
                    """INSERT INTO grade_history
                       (grade_id, changed_by, old_score, new_score, source_ip)
                       VALUES (?, ?, ?, ?, ?)""",
                    (gid, g.user["id"], before.get(gid), new_score, client_ip()),
                )
        conn.commit()
    except sqlite3.Error as e:
        conn.rollback()
        # [의도적 취약점] 에러와 쿼리 노출
        return f"DB error: {e}\n{sql}", 500

    return redirect(f"/courses/{target['course_id']}/grades")