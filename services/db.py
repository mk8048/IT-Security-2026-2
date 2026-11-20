"""web 서비스와 honeypot 서비스가 공유하는 SQLite 스키마 및 초기화 모듈.

이 모듈에는 스키마, 연결 헬퍼, 초기 데이터만 둔다.
의도적으로 취약한 쿼리(또는 매개변수화된 수정 쿼리)는 이 모듈이 아니라
각 기능 코드에 작성한다.
"""
import sqlite3

DB_PATH = "/data/app.sqlite3"
FILES_DIR = "/files"

SCHEMA = """
CREATE TABLE IF NOT EXISTS infrastructure (
    service TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE,
    password      TEXT NOT NULL,   -- 취약 버전은 평문 저장, 패치 시 해시로 변경
    name          TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('student', 'professor', 'admin')),
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS courses (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    code          TEXT NOT NULL UNIQUE,
    title         TEXT NOT NULL,
    professor_id  INTEGER NOT NULL REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS grades (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id    INTEGER NOT NULL REFERENCES users(id),
    course_id     INTEGER NOT NULL REFERENCES courses(id),
    score         INTEGER NOT NULL CHECK (score BETWEEN 0 AND 100),
    updated_at    TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (student_id, course_id)
);

-- 변조된 성적을 복구할 수 있도록 모든 성적 변경을 기록한다.
CREATE TABLE IF NOT EXISTS grade_history (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    grade_id      INTEGER NOT NULL REFERENCES grades(id),
    changed_by    INTEGER REFERENCES users(id),   -- 변경 주체를 알 수 없으면 NULL
    old_score     INTEGER,
    new_score     INTEGER NOT NULL,
    source_ip     TEXT,
    changed_at    TEXT NOT NULL DEFAULT (datetime('now')),
    restored_at   TEXT                            -- 복구(롤백)된 시각
);
CREATE INDEX IF NOT EXISTS idx_grade_history_grade ON grade_history(grade_id);

CREATE TABLE IF NOT EXISTS posts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    author_id     INTEGER NOT NULL REFERENCES users(id),
    title         TEXT NOT NULL,
    content       TEXT NOT NULL, 
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 세션 토큰은 해시값만 저장한다(원본 토큰은 보관하지 않음).
CREATE TABLE IF NOT EXISTS sessions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    token_hash    TEXT NOT NULL UNIQUE,
    user_id       INTEGER NOT NULL REFERENCES users(id),
    source_ip     TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at    TEXT NOT NULL,
    revoked_at    TEXT,
    revoked_by    INTEGER REFERENCES users(id),
    revoke_reason TEXT
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);

-- /files 에서 제공하는 실습용 파일. 여기에는 파일 이름만 저장한다.
CREATE TABLE IF NOT EXISTS files (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    filename      TEXT NOT NULL UNIQUE,
    description   TEXT,
    uploaded_by   INTEGER REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS ip_blocks (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ip            TEXT NOT NULL,
    reason        TEXT,
    blocked_by    INTEGER REFERENCES users(id),
    blocked_at    TEXT NOT NULL DEFAULT (datetime('now')),
    released_at   TEXT,
    released_by   INTEGER REFERENCES users(id)
);
CREATE INDEX IF NOT EXISTS idx_ip_blocks_ip ON ip_blocks(ip);
"""


def connect(timeout=2):
    conn = sqlite3.connect(DB_PATH, timeout=timeout)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def seed(conn):
    """더미 계정과 데이터를 최초 1회만 삽입한다. 모든 값은 가상의 실습 데이터이다."""
    if conn.execute("SELECT 1 FROM users").fetchone():
        return
    users = [
        ("admin", "admin-pass", "관리자", "admin"),
        ("prof1", "prof-pass", "김교수", "professor"),
        ("stu1", "stu1-pass", "학생A", "student"),
        ("stu2", "stu2-pass", "학생B", "student"),
    ]
    for username, pw, name, role in users:
        conn.execute(
            "INSERT INTO users (username, password, name, role) VALUES (?, ?, ?, ?)",
            (username, pw, name, role),
        )
    uid = {r["username"]: r["id"] for r in conn.execute("SELECT id, username FROM users")}

    conn.execute("INSERT INTO courses (code, title, professor_id) VALUES (?, ?, ?)",
                 ("SEC101", "정보보호 및 보안", uid["prof1"]))
    cid = conn.execute("SELECT id FROM courses WHERE code = 'SEC101'").fetchone()["id"]

    for student, score in (("stu1", 85), ("stu2", 72)):
        cur = conn.execute(
            "INSERT INTO grades (student_id, course_id, score) VALUES (?, ?, ?)",
            (uid[student], cid, score))
        conn.execute(
            "INSERT INTO grade_history (grade_id, changed_by, old_score, new_score) "
            "VALUES (?, ?, NULL, ?)", (cur.lastrowid, uid["prof1"], score))

    conn.execute("INSERT INTO files (filename, description, uploaded_by) VALUES (?, ?, ?)",
                 ("syllabus.txt", "강의계획서", uid["prof1"]))
    conn.execute("INSERT INTO posts (author_id, title, content) VALUES (?, ?, ?)",
             (uid["prof1"], "공지",
              '중간고사 일정 안내입니다.<br>'
              '<a href="/files/download?name=syllabus.txt">강의계획서 다운로드</a>'))


# files 테이블 시드와 짝을 이루는 실습용 파일 (파일명 -> 내용). 모두 가상의 더미 내용이다.
SEED_FILES = {
    "syllabus.txt": "정보보호 및 보안 강의계획서 (실습용 더미 파일)\n"
                    "- 과목코드: SEC101\n- 중간고사 일정은 게시판 공지를 참고하세요.\n",
}


def seed_files():
    """실습용 파일을 /files 에 만든다. 이미 있는 파일은 덮어쓰지 않는다."""
    for filename, content in SEED_FILES.items():
        try:
            # "x" 모드: 파일이 없을 때만 생성 (복원된 볼륨의 파일을 보존)
            with open(f"{FILES_DIR}/{filename}", "x", encoding="utf-8") as f:
                f.write(content)
        except FileExistsError:
            pass


def init_db(service):
    """테이블을 만들고 초기 데이터를 넣는다. 서비스 시작 시마다 호출해도 안전하다."""
    with connect() as conn:
        conn.executescript(SCHEMA)
        if not conn.execute("SELECT 1 FROM infrastructure").fetchone():
            conn.execute("INSERT INTO infrastructure VALUES (?)", (service,))
        seed(conn)
    seed_files()


def reset_db(service):
    """실습용 DB를 초기 시드 상태로 되돌린다. /files는 보존한다."""
    with connect() as conn:
        conn.executescript("""
        DROP TABLE IF EXISTS ip_blocks;
        DROP TABLE IF EXISTS sessions;
        DROP TABLE IF EXISTS files;
        DROP TABLE IF EXISTS posts;
        DROP TABLE IF EXISTS grade_history;
        DROP TABLE IF EXISTS grades;
        DROP TABLE IF EXISTS courses;
        DROP TABLE IF EXISTS users;
        DROP TABLE IF EXISTS infrastructure;
        """)
    init_db(service)
