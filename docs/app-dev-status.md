# 애플리케이션 개발 현황 (취약 버전)

작성일: **2026-11-18**. 1단계 인프라 이후 진행한 웹 애플리케이션(로그인·성적·게시판·파일) 개발 내용을 팀원이 확인하도록 정리한 문서다.
인프라 구성은 [infra-status.md](infra-status.md), 운영 방법은 [runbook.md](runbook.md)를 따른다.

**현재 코드는 취약점 재현용 "취약 버전" 하나뿐이다.** 패치 버전과 `APP_MODE` 분기는 아직 없다(아래 TODO 참고).

## 1. 검증 환경과 범위

- 개발·검증은 **개인 PC의 로컬 Docker Desktop**(Windows)에서 `127.0.0.1:8080`으로 수행했다.
  프로젝트 VM(`team-security`), Tailscale 경로, 다른 팀원 PC에서는 **아직 검증하지 않았다.**
- 검증은 `curl`과 Flask 테스트 클라이언트로 응답 코드·본문·DB를 확인한 수동 검사다. 자동화된 테스트 스크립트는 추가하지 않았다.
- 브라우저 화면 모양은 일부(XSS `alert` 실행)만 직접 확인했고, 나머지는 응답 HTML로 확인했다.

## 2. 구현 현황

| 단계 | 내용 | 커밋 |
| --- | --- | --- |
| 1 | SQLite 스키마·시드, 회원가입, 서버 측 세션 로그인, 역할 검사 | `eb0f087`, `2d199de` |
| 2 | 성적 조회(학생)·목록/수정(교수), 변경 이력 기록 | `20c217b` |
| 3 | 게시판 (저장형 XSS 재현) | `b9ff8e8` |
| 4 | 파일 조회/다운로드 (Path Traversal 재현) | `365b8cf` |
| 5 | 역할별 메뉴·홈 화면, 교수용 과목 목록 | `b8246a5` |
| 추가 | 자료 등록: 게시판 첨부(학생·전체), 자료실 업로드(교수·관리자) | `4b5adc7` |

### 라우트와 권한

| 경로 | 메서드 | 권한 | 설명 |
| --- | --- | --- | --- |
| `/` | GET | 로그인 | 홈. 비로그인은 `/login`으로 이동 |
| `/login`, `/signup` | GET/POST | 공개 | 가입은 **학생 역할로만** 생성(요청값으로 역할 지정 불가) |
| `/logout` | POST | 로그인 | 세션 폐기 기록 |
| `/grades` | GET | 학생 | 본인 성적만 조회 |
| `/courses` | GET | 교수 | 담당 과목의 성적 화면으로 이동 |
| `/courses/<id>/grades` | GET | 교수 | 담당 과목만 허용(아니면 403) |
| `/grades/<id>` | POST | 교수 | 점수 수정, 변경 이력 기록 |
| `/board`, `/board/<id>` | GET | 로그인 | 목록·상세 |
| `/board/write` | GET/POST | 로그인 | 글쓰기, 파일 첨부(선택) |
| `/files` | GET | 로그인 | 자료실 목록 |
| `/files` | POST | 교수·관리자 | 자료 업로드 |
| `/files/download?name=` | GET | 로그인 | 다운로드 |
| `/healthz` | GET | 내부 | 상태 점검(기존) |

관리자(`admin`) 전용 화면은 아직 없다. 로그인하면 게시판·자료실만 보인다.

### 시드 계정 (가상 데이터, 새 DB를 만들 때 한 번만 삽입)

| 아이디 | 비밀번호 | 역할 |
| --- | --- | --- |
| `admin` | `admin-pass` | 관리자 |
| `prof1` | `prof-pass` | 교수 (과목 SEC101 담당) |
| `stu1` | `stu1-pass` | 학생 (점수 85) |
| `stu2` | `stu2-pass` | 학생 (점수 72) |

시드는 `users` 테이블이 비어 있을 때만 실행된다. 이미 만들어진 볼륨에는 다시 적용되지 않는다.

## 3. 의도적 취약점과 재현 방법

취약점은 **기능마다 한 곳에만** 두었다. 그 외 권한 검사·세션·저장 쿼리는 안전하게 작성했다(결과 분석이 섞이지 않게 하기 위함).
코드에는 `[의도적 취약점]` 주석으로 표시했다.

| 취약점 | 위치 | 재현 예시 |
| --- | --- | --- |
| SQL Injection (인증 우회) | `auth.py` `login()` | 아이디 `admin'--`, 비밀번호 임의 → 관리자로 로그인. 오류 시 쿼리가 화면에 노출됨 |
| SQL Injection (성적 변조) | `grades.py` `update_grade()` | 교수로 로그인 후 `score`에 `100 WHERE 1=1 --` → 전체 학생 점수 변경, `grade_history`에는 행마다 기록 |
| 저장형 XSS | `post.html` | 게시글 본문에 `<script>alert(1)</script>` → 글을 여는 모든 사용자에게 실행. 제목·목록은 이스케이프됨 |
| Path Traversal (읽기) | `files.py` `file_download()` | `/files/download?name=../etc/passwd`, `../data/app.sqlite3`(평문 비밀번호 포함), `../app/auth.py` |
| 업로드 취약점 | `files.py` `file_upload()`, `board.py` `board_write()` | 파일명·확장자 검증 없음, 덮어쓰기 허용, 경로 이탈(`../data/...`), `.html` 업로드 시 `text/html`로 응답(저장형 XSS), 설명·파일명이 INSERT에 그대로 이어붙음(SQLi) |

![SQLi 재현 스크린샷](<스크린샷 2026-11-18 232834.png>)
![저장형 XSS 재현 스크린샷](<스크린샷 2026-11-18 211033.png>)
![Path Traversal 재현 스크린샷](<스크린샷 2026-11-18 214852.png>)

## 4. 구조와 설계 결정

- 구성: `services/app.py`(조립) + `auth.py`, `grades.py`, `board.py`, `files.py`(Blueprint) + `db.py`(스키마·시드) + `templates/`.
  Dockerfile이 `services/*.py`를 `/app/`에 평평하게 복사하므로 **import는 `from auth import ...` 형식**이어야 한다(`services.auth` 불가).
- `web`과 `honeypot`은 같은 이미지·같은 `app.py`를 쓰고 `SERVICE_NAME`만 다르다. DB와 `/files`는 서비스별 볼륨이라 파일 자체는 분리된다.
- 세션: 토큰은 `secrets.token_urlsafe(32)`, DB에는 **SHA-256 해시만** 저장. 쿠키는 `HttpOnly`, `SameSite=Lax`. 만료 2시간.
  쿠키가 `HttpOnly`이므로 XSS로 `document.cookie`를 읽을 수 없다. XSS 재현은 스크립트 실행 자체를 증거로 삼는다.
- 역할은 쿠키가 아니라 DB의 `users.role`로만 판단한다. 출발지 IP는 gateway가 전달한 `X-Forwarded-For`를 신뢰 gateway에서 온 요청에 한해 사용한다.
- 비밀번호는 취약 버전 방침으로 **평문 저장**이다. 패치 시 해시로 바꾼다.
- `grade_history`(변경 전후 점수·변경자·IP)는 12주차 성적 복구의 기반이다. 성적이 한 번에 여러 행 바뀌어도 행마다 기록한다.
- `sessions`의 `revoked_at/by/reason`, `ip_blocks` 테이블은 스키마만 준비했고 관리자 기능은 아직 없다.
- 실습 파일 `syllabus.txt`는 `db.seed_files()`가 `/files`에 만든다(이미 있으면 덮어쓰지 않음).

## 5. 로컬 실행 시 참고

- 같은 이미지 이름을 `gateway`·`web`·`honeypot`이 병렬로 빌드하면 `image already exists`로 실패할 수 있다.
  `docker compose build web` 후 `docker compose up -d --no-build --wait`로 기동하면 해결된다.
- 코드를 바꾸면 이미지를 다시 빌드해야 반영된다. 로컬 DB·파일은 Docker 볼륨에 남는다.
- `down -v`와 볼륨 삭제는 데이터 삭제이므로 일반 절차로 쓰지 않는다([runbook.md](runbook.md) 참고).
- 로컬 볼륨에는 테스트 흔적이 남아 있다: `grade_history` 테스트 기록, 테스트 게시글, 테스트 가입 계정(`newstu`, `evil1`, `xssname1`). 가상 데이터이며 공유되지 않는다.

## 6. 알려진 한계

- CSRF 방어 없음, 로그인 시도 횟수 제한 없음, 쿠키 `Secure` 미설정(HTTP 환경), 만료된 세션 정리 로직 없음.
- 점수가 0~100을 벗어나거나 비어 있으면 DB 제약 오류로 500이 난다(취약 버전이라 의도적으로 노출).
- 업로드는 **임의 위치 파일 쓰기**가 가능하다. `../data/app.sqlite3`를 덮어쓰면 DB가 바뀌어 실험 환경이 훼손될 수 있다.
- 자료실 업로드에서 파일명에 따옴표가 있으면 SQL 오류로 500이 나며, 이미 저장된 파일은 `/files`에 남는다(게시판 첨부는 롤백 시 삭제).
- 게시판 첨부 파일은 `files` 테이블에 등록되지 않아 자료실 목록에는 보이지 않고 글의 링크로만 접근된다.
- 같은 이름으로 업로드하면 기존 파일을 덮어쓴다(학생이 교수가 올린 파일을 덮어쓸 수 있음).
- 가입·성적·게시판·파일 라우트는 허니팟에도 동일하게 존재한다.

## 7. TODO

### 허니팟 작업 때
- `db.py` `seed()`를 `SERVICE`별로 분리해 허니팟에 **정상 서비스와 다른 미끼 계정·비밀번호·점수**를 넣는다([infra-status.md](infra-status.md)의 "정상/허니팟 인증을 공유해서는 안 된다" 요구).
  기존 `honeypot-data` 볼륨에는 시드가 다시 적용되지 않으므로 새 볼륨이 필요하다.
- 허니팟에 노출할 라우트(가입·업로드 등)와 응답 형식을 정한다. `/`는 이제 로그인으로 리다이렉트되고 예전 서비스 식별 JSON은 없다.
- **`/` 응답 변경으로 기존 점검 스크립트가 맞지 않는다:** `scripts/check_infra.py:40`(`data-service="web"` 기대),
  `scripts/check_routes.sh:11`(허니팟 JSON `service=="honeypot"` 기대), `:20`(web HTML `data-service="web"` 기대). 허니팟 작업 때 함께 수정한다.
- `services/templates/index.html`은 더 이상 쓰이지 않는다.

### 패치(12주차) 작업 때
- **패치 전에 현재 취약 버전을 git 태그/브랜치(예: `vulnerable-v1`)로 보존**한다(AGENTS.md 요구).
- `APP_MODE`(`vulnerable`/`secure`) 환경변수로 로그인 쿼리·비밀번호 저장 방식 등을 분기한다. 요청 헤더·쿠키·쿼리로 바꿀 수 없는 고정 설정이어야 한다.
  `compose.yaml`과 `.env.example`은 이때 수정한다. 모드를 바꾸면 시드 형식(평문/해시)이 달라지므로 새 DB가 필요하다.
- 패치 대상에 **업로드 취약점(파일명 검증, 경로 이탈, 확장자·Content-Type, INSERT 이어붙임)**도 포함할지 정한다.

### 사고 대응·보안 기능
- 6단계 **감사 로그 연결**: 현재 `audit.py`는 HTTP 요청 요약만 기록한다. 로그인 성공·실패, 성적 변경, 접근 거부, 세션 폐기 이벤트를 추가한다(비밀번호·세션 토큰 원문은 기록 금지).
- 관리자 화면: 세션 강제 폐기(`sessions.revoked_*`), 성적 복구(`grade_history.restored_at`), IP 차단·해제(`ip_blocks`), 보안 이벤트 조회.
- WAF·재공격 전환·허니팟 로그 연계(제안서 범위).

### 결정이 필요한 것
- 업로드의 DB 덮어쓰기(`../data/app.sqlite3`)까지 허용할지, 쓰기 가능한 경로를 `/files` 내부로 제한할지.
- 게시판 첨부를 자료실 목록에도 등록할지.
- 점수 범위 밖 입력을 정상 오류 처리할지(현재는 500).

### 문서·검증
- VM(`team-security`)에 새 코드를 배포해 동일한 검증을 수행하고, 사용자 PC·Tailscale 경로에서도 확인한다.
- 아래 문서는 로그인·세션이 "미구현"이라거나 DB가 "서비스 식별용 메타데이터만 담는다"고 적혀 있어 현재와 다르다. 팀 합의 후 갱신한다.
  `handoff.md`(§2, §4), `README.md`, `docs/runbook.md`(상단, DB 설명), `docs/infra-status.md`(§애플리케이션), `docs/vm-migration-guide.md`(DB 설명).
- **VM 이전 시 주의:** 이제 앱이 시작할 때 `init_db()`가 테이블과 더미 계정을 자동으로 만든다. 복원 전에 앱을 먼저 기동해 빈 DB를 만들지 않는다는 이전 가이드의 규칙이 더 중요해졌다.
- 앱 기능(로그인·성적·게시판·파일) 점검을 `scripts/`에 자동 테스트로 추가한다.
