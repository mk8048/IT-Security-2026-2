# 보안 팀 프로젝트 — 새 VM의 에이전트용 인계

작성일: 2026-11-12. 기존 최초 구축 요청용 인계 문서를 대체한다.
목적은 **현재 프로젝트의 맥락·코드·실행 데이터·운영 경계를 이어받아 새 VM에서 복원하고 검증하는 것**이다.
문서를 읽었다는 이유만으로 이전을 실행하거나 기존 VM을 중지하지 않는다. 이번 문서 작성 시 실제 이전은 수행하지 않았다.

## 1. 먼저 읽을 문서와 정보의 우선순위

1. [AGENTS.md](AGENTS.md): 프로젝트 작업 경계와 보안 원칙.
2. [제안서](docs/proposal.md): 최종 프로젝트 목표.
3. 이 문서: 인계 시점의 현재 상태·다음 작업.
4. [VM 이전 가이드](docs/vm-migration-guide.md): 백업·복원·전환 명령과 검증 기준.
5. [운영 방법](docs/runbook.md), [기존 실제 검증 기록](docs/infra-status.md).

사용자의 최신 지시와 새 VM의 실제 상태를 우선하고, 문서의 과거 확인값을 현재값으로 단정하지 않는다.
[중간보고서 초안](docs/infra-status-report.md)은 외부 접근을 공인 IP 방식으로 가정한 비공식 문서다.
**실제 운영 설계는 Tailscale 직접 연결이며, 보고서의 가정을 VM 설정에 적용하지 않는다.**

## 2. 프로젝트 맥락과 구현 상태

가상의 성적관리 웹서비스에서 SQL Injection 인증 우회·성적 변조, 저장형 XSS, Path Traversal을 재현한 뒤
코드 패치·세션 폐기·성적 복구·WAF·허니팟 기반 재공격 탐지를 검증하는 대학 수업 프로젝트다.
가상 데이터만 사용하고 실험 대상은 팀 프로젝트 VM과 앱으로 한정한다.

현재 완료한 것은 1단계 기초 인프라다.

- Docker Compose 서비스 4개: `nginx`, `gateway`, `web`, `honeypot`.
- 정상 앱 `/`: `Hello World!` HTML과 임시 앱 안내, `/healthz` 링크.
- 허니팟 `/`: 서비스 식별 JSON. 두 앱은 Flask·Gunicorn으로 실행.
- gateway: 고정된 `web` 또는 `honeypot`으로 전달하는 WSGI 골격, 기본 대상 `web`.
- 독립 네트워크·볼륨, 상태 점검, 제한된 JSON 요청 로그와 회전.
- 정상·허니팟 경로, 장애 시 502, 헤더 처리, 통신·데이터 분리, 앱·Docker 재시작 검증.
- 기존 VM에 대한 사용자 PC의 HTTP 접속과 로그 요청 ID 대조 완료. Hello World 변경 후 브라우저 화면의 직접 증빙은 기존 기록에서 미확인.

로그인·성적·게시판·파일 다운로드·서버 세션, 실제 취약/패치 버전, WAF 규칙·자동 재공격 전환,
관리자 화면·사고 대응은 미구현이다. 인프라 이전 요청을 전체 앱 개발로 확장하지 않는다.

## 3. 인계 시점의 참고 환경

| 항목 | 기존 VM에서 확인한 값 |
| --- | --- |
| VM·프로젝트 경로 | `team-security`, `/home/ubuntu/security-lab` |
| OS·자원 | Ubuntu 24.04.5 x86_64, vCPU 4, RAM 약 8GB, 루트 디스크 약 58GiB |
| 도구 | Docker 29.9.3, Compose 5.7.1, Tailscale 1.104.6 |
| 앱 | Nginx 1.30.6, Python 3.13.18, Flask 3.1.3, Gunicorn 27.0.0, SQLite 3.40.1 |
| 기존 웹 주소 | `http://100.102.19.44:8080/` — 새 VM의 주소가 아님 |
| 호스트 MTU | ens3 1442. 새 VM에서 다시 확인할 것 |
| 저장소 | `https://github.com/mk8048/IT-Security-2026-2.git` |
| 문서 갱신 전 원격 기준 커밋 | `91e485926f3279286c86e6325b660c052f83075c` |

위 커밋은 보고서 추가 시점의 참고값이다. 이 새 인계·이전 가이드의 커밋과 백업 시점의 실제 HEAD는 별도로 확인한다.
문서가 미커밋이면 새 VM의 clone에는 없으므로 먼저 커밋하거나 두 문서를 별도 전달한다.
현재 checkout을 무조건 원격 main으로 초기화하지 않는다. 미커밋 변경과 추가 커밋을 먼저 확인한다.

## 4. 유지할 통신·데이터 경계

실제 경로: `PC → Tailscale → nginx → gateway → web 또는 honeypot`.
호스트 웹 포트는 Nginx의 8080 하나다. `.env`의 `HOST_BIND_IP`는 새 VM의 실제 Tailscale IPv4를 사용한다.
준비 전에는 `127.0.0.1`, 기본 `GATEWAY_TARGET=web`. 공인 IP나 `0.0.0.0`로 자동 대체하지 않는다.

| 네트워크 | 주소·연결 | 설정 |
| --- | --- | --- |
| frontnet | `172.29.240.0/24`, nginx `.2`, gateway `.3` | gateway는 이 주소에서만 8000 수신 |
| appnet | `172.29.241.0/24`, gateway `.2`, web `.3` | internal + isolated |
| honeynet | `172.29.242.0/24`, gateway `.2`, honeypot `.3` | internal + isolated |

Compose의 MTU는 현재 세 네트워크 모두 1442다. 주소·MTU는 새 VM의 기존 네트워크와 비교한다.
서브넷을 변경하면 Compose 주소·bind·healthcheck·TRUSTED_GATEWAY, `services/gateway.py`의 신뢰·bind 주소,
`infra/security-lab-ingress`와 검사 스크립트의 대상 주소를 함께 갱신한다.
gateway의 양쪽 백엔드 연결은 신뢰 경계다. 범용 목적지 프록시나 허니팟→정상 서비스 폴백을 추가하지 않는다.

데이터 볼륨은 아래 5개다. 각 앱은 자기 `/data`와 `/files`만 사용한다.

```text
security-lab_web-data        → web:/data (app.sqlite3)
security-lab_web-files       → web:/files
security-lab_honeypot-data   → honeypot:/data (app.sqlite3)
security-lab_honeypot-files  → honeypot:/files
security-lab_gateway-data    → gateway:/data
```

프로세스 UID/GID는 `10001:10001`. 현재 DB는 서비스 식별용 메타데이터만 담는다.
데이터가 적다는 이유로 볼륨을 버리거나 복원 전에 앱을 기동하여 빈 DB를 만들지 않는다.

## 5. Git에 없는 항목과 호스트 설정

- `.env`, DB·앱 파일·향후 세션·분기 상태는 별도 이전 대상이다. 가이드는 정지 후 볼륨 5개를 백업한다.
- Docker stdout 로그는 데이터 볼륨과 별개다. 보존 필요 시 별도 내보낸다.
- `.env`·키·로그·백업은 Git과 채팅에 넣지 않는다. 앱 컨테이너에 SSH 키·에이전트 인증·Docker 소켓을 마운트하지 않는다.
- GitHub 인증은 기존 VM의 저장소 전용 SSH deploy key로 준비되어 있지만 새 VM으로 자동 이전되지 않는다.
  새 VM에서 push가 필요하면 전용 키를 새로 등록하고 쓰기 권한을 확인한다. 작성자 정보는 작업자에게 확인한다.
- Tailscale은 새 VM을 새 장치로 연결하고 사용자에게 인증·승인 단계를 맡긴다. 기존 로그인 상태 파일을 복제하지 않는다.
- Docker 공식 apt 저장소와 `/etc/docker/daemon.json`의 MTU 설정은 clone되지 않는다. 기존 새 VM 설정을 보존·병합한다.
- `infra/security-lab-ingress*`를 `/usr/local/sbin` 및 `/etc/systemd/system`에 설치해야 한다.
  `DOCKER-USER`에서 Nginx `172.29.240.2:80`로 향하는 비Tailscale 전달 트래픽만 차단하고 Docker 시작·재시작에 연동한다.
  다른 방화벽 백엔드나 기존 동명 파일을 발견하면 먼저 영향을 확인한다. UFW만으로 게시 포트를 보호한다고 가정하지 않는다.

과거 장애는 MTU 불일치에 따른 컨테이너 TLS timeout, 기본 Nginx 로그의 쿼리 노출,
Gunicorn 제어 소켓의 read-only 오류, internal 네트워크의 호스트 브리지 접근이었다.
현재 MTU 설정, 전용 nginx.conf, `--no-control-socket`, isolated 모드를 이유 없이 제거하지 않는다.

## 6. 다음 에이전트의 실행 순서

실제 이전 요청을 받으면 아래 정보를 먼저 확인한다. 연결된 소스에서 확인할 수 있으면 사용자에게 반복 질문하지 않는다.

| 필요한 정보 | 확인 내용 |
| --- | --- |
| 작업 위치 | 현재 실행기가 기존 VM인지 새 VM인지, 실제 프로젝트 루트 |
| 원본 보존 | 기존 VM 존속 여부, 서비스 정지 가능한 점검 시간 |
| 복원 원본 | 백업 경로·시점·체크섬·코드 커밋, 미커밋 파일 보존 여부 |
| 새 VM | OS·아키텍처·자원·권한·기존 서비스·Docker·포트·주소 충돌 |
| 인증 | 새 장치 승인, 실제 사용자 PC 접속 가능 여부, 필요 시 GitHub 쓰기 인증 |

1. 상태 점검 후 기존 설정·키·SSH 접속과 다른 프로젝트를 보존한다.
2. [가이드](docs/vm-migration-guide.md)에 따라 기존 앱 쓰기를 중지하고 DB·파일을 함께 백업한다.
3. 백업을 별도 위치로 전송하고 새 VM에서 무결성을 확인한다.
4. 백업과 일치하는 코드를 준비하고 실행 도구·MTU·접근 경계를 구성한다.
5. `build`와 `create`까지만 실행한 뒤, 정지된 빈 볼륨에 복원한다.
6. 기동 전 아카이브 비교·SQLite 무결성을 확인하고, 이후 서비스·격리·로그·영속성을 검증한다.
7. 새 주소를 사용자에게 전달하고 실제 PC에서 확인한다. 두 VM이 동시에 쓰기를 받지 않도록 전환한다.
8. 결과를 문서화하고 새로운 현재 상태로 이 인계와 운영 문서를 갱신한다.

이전 실행 시 필요한 설치·프로젝트 기동·검증은 진행하되, 비밀번호나 토큰은 채팅에 요구하지 않는다.
기존 VM·볼륨 삭제, 네트워크 전체 초기화, 무단 재부팅은 수행하지 않는다.
새 VM에서 쓰기가 생겼다면 기존 백업으로 단순 복귀하지 말고 변경분을 먼저 보존한다.

## 7. 완료 보고에 필요한 증빙

- 소스 커밋·백업 시점·체크섬과 복원 대상 볼륨, 데이터 대조·SQLite 무결성 결과.
- 새 VM OS·도구 버전·실제 IP와 호스트 웹 포트, 4개 healthy 상태.
- `config --quiet`, Nginx 설정 검사, gateway 단위 검사, 경로·격리·로그·재시작 검사 결과.
- 사용자 PC에서의 실제 접속 결과와 요청 ID 로그 대조. 불가능하면 미확인으로 명시.
- 복귀 방법, 기존 VM 보존 상태, 실패·미확인 항목과 사용자 직접 작업.

새 VM 이전·호스트 재부팅·전체 백업 복원은 이 인계 작성 시 검증하지 않았다.
에이전트는 실행 결과와 계획을 구분하고, 기존 VM의 통과 결과를 새 VM의 통과 결과로 재사용하지 않는다.
