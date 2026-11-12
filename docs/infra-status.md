# 1단계 인프라 구축·검증 결과

검증일: **2026-11-12**, 최종 통합 검사 **10:01 KST / 01:01 UTC**.
실행 위치는 프로젝트 Nova VM `team-security`, 사용자 `ubuntu`, 경로 `/home/ubuntu/security-lab`이다.
VM/컨테이너 검사는 직접 실행했고, PC 접속은 사용자가 제공한 Windows curl 결과와 VM 로그를 대조했다.

## 결과

**4개 서비스가 모두 healthy이고 기본 web 경로로 실행 중이다.**
VM 내부에서 `http://100.102.19.44:8080/`와 `/healthz`의 200 응답을 확인했다.
허니팟 전달, 장애 시 502와 폴백 금지, 네트워크·데이터 분리, 재시작 보존, 로그 보호 검사를 통과했다.
사용자 PC에서의 Tailscale HTTP 접속도 **10:30 KST / 01:30 UTC**에 확인했다.
원격 접근 정책 전체와 다른 팀원 PC의 접속 여부는 별도 확인 대상이다.

### Hello World 페이지 추가 (10:33 KST)

사용자 요청으로 정상 앱 `/`를 JSON 대신 `services/templates/index.html`의 Hello World 페이지로 변경했다.
서비스 식별자와 임시 앱 안내, `/healthz` 링크를 표시한다. 허니팟의 JSON 응답과 상태 점검 경로는 유지한다.
Dockerfile에 템플릿 복사를 추가하고 기존 검증 스크립트의 정상 앱 응답 검사를 HTML 기준으로 맞췄다.
재빌드·기동 후 4개 서비스 healthy, VM에서 HTML 200·제목·서비스 식별·상태 링크·임시 안내 및
`/healthz` 200 ready, 게이트웨이에서 허니팟 JSON 응답을 확인했다. Python/shell 구문 검사도 통과했다.
아래 초기 구축 기록과 10:30 PC curl 기록은 HTML 변경 전의 결과다.
이번 변경 후 PC 브라우저의 실제 렌더링 확인은 사용자 확인 대상으로 남긴다.

## 실제 환경

| 항목 | 확인 결과 |
| --- | --- |
| OS / 아키텍처 | Ubuntu 24.04.5 LTS / x86_64 |
| 커널 | 6.8.0-147-generic |
| 자원 | vCPU 4, RAM 7.8GiB, swap 없음 |
| 루트 디스크 | 58GiB, 작업 전 약 52GiB 여유 |
| 일반 사설 IPv4 | `10.10.10.158` / ens3 MTU 1442 |
| Tailscale | 기존 설치 1.104.6, BackendState Running, SelfOnline true, Health 빈 배열 |
| Tailscale IPv4 | `100.102.19.44` |
| Docker 전 상태 | docker/compose 및 충돌 패키지 미설치, 기존 컨테이너 없음, 8080 비어 있음 |
| 권한 | 일반 사용자 ubuntu, 비대화형 sudo 가능, Docker 그룹 미추가 |
| 저장소 | 최초 문서 3개만 존재, Git 저장소 미초기화 |
| 기존 방화벽 | UFW inactive, 기존 Tailscale iptables 규칙 존재 |
| 작업 전 보존 대상 | SSH, Tailscale 로그인·설정·키, AGENTS.md, handoff.md, docs/proposal.md |

Tailscale 장치 전체 목록·로그인 토큰은 수집 문서에 복사하지 않았다.
호스트 외의 Controller/Compute, 다른 VM, 학교 서비스나 네트워크에는 변경·시험을 수행하지 않았다.

## 설치·고정 버전

Docker 공식 Ubuntu apt 저장소로 새로 설치했다. 기존 패키지 제거·OS 업그레이드·호스트 재부팅은 하지 않았다.

| 구성 | 실제 버전 |
| --- | --- |
| Docker Engine / CLI | 29.9.3 |
| Docker Compose | 5.7.1 |
| containerd.io | 2.4.2 |
| Buildx | 0.38.1 |
| Nginx | 1.30.6 |
| Python | 3.13.18 |
| Flask / Gunicorn | 3.1.3 / 27.0.0 |
| SQLite 런타임 | 3.40.1 |
| 기타 Python 의존성 | blinker 1.9.0, click 8.5.1, itsdangerous 2.2.0, Jinja2 3.1.6, MarkupSafe 3.0.4, Werkzeug 3.1.9 |

기준일에 공식 배포원에서 받아 실제 실행한 버전이며 Python 의존성은 `services/requirements.txt`에서 고정했다.
Python 3.13의 slim Debian 이미지와 Nginx stable Alpine 이미지를 사용하고 다음 digest를 고정했다.
웹 프레임워크와 프로세스 서버 외 별도 프록시·DB 라이브러리는 추가하지 않았다.

- Python: `sha256:a5a7017efc5969e00ae2b91c8eb0631049a569652aa4ffc4501769049ae45c72`
- Nginx: `sha256:583b7f2fce1cdb8da5ad5c39ebd3c33b98b87d493190e548bdee1fa8c619c311`

## 변경한 파일과 호스트 설정

프로젝트에 추가:

- `compose.yaml`, `.env.example`, `.env`(600, 버전 관리 제외), `.gitignore`, `.dockerignore`
- `infra/nginx/nginx.conf`, `infra/nginx/default.conf`
- `infra/security-lab-ingress`, `infra/security-lab-ingress.service`
- `services/Dockerfile`, `services/requirements.txt`, `services/app.py`, `services/gateway.py`, `services/audit.py`
- `scripts/test_gateway.py`, `scripts/check_infra.py`, `scripts/check_routes.sh`
- `docs/runbook.md`, `docs/infra-status.md`

기존 세 문서는 수정하지 않았다. Git 초기화나 원격 저장소 생성은 하지 않았다.

호스트에 추가:

- `/etc/apt/keyrings/docker.asc`, `/etc/apt/sources.list.d/docker.sources`
- `/etc/docker/daemon.json`: 새 Docker의 기본 bridge 및 새 사용자 bridge MTU 1442
- `/usr/local/sbin/security-lab-ingress`, `/etc/systemd/system/security-lab-ingress.service` 및 enable 링크
- Docker/containerd 패키지·systemd 서비스와 Docker가 관리하는 네트워크/iptables 규칙

방화벽 초기화·SSH 설정 변경·Tailscale 재등록·전역 Docker 정리·기존 데이터 볼륨 삭제는 하지 않았다.
Docker 재시작과 이 프로젝트 컨테이너/네트워크 재생성은 아래 검증을 위해 수행했으며 명명된 데이터 볼륨은 보존했다.

## 실행·검증 근거

명령은 프로젝트 루트에서 실행했다. sudo Docker를 일관되게 사용했으며 전체 Compose 설정이나 원본 요청 덤프를 보고서에 복사하지 않았다.

| 검사 | 명령·실행 위치 | 실제 결과 |
| --- | --- | --- |
| Compose 구성 | VM: `sudo docker compose config --quiet` | 성공 |
| 빌드·기동 | VM: `sudo docker compose up -d --build --wait --wait-timeout 120` | 성공, nginx/gateway/web/honeypot 모두 healthy |
| Nginx 설정 | 컨테이너: `sudo docker compose exec -T nginx nginx -t` | syntax/test successful |
| 기본 경로 | VM: `curl http://100.102.19.44:8080/`, 통합 스크립트 | 200, `service=web`, 임시 인프라 앱 표시 |
| Readiness | 각 healthcheck + Nginx `/healthz` | gateway가 두 앱의 실제 health와 저장소 상태 확인, 200 |
| 허니팟 경로 | VM: `bash scripts/check_routes.sh` | 환경 기반 고정 대상을 honeypot으로 바꿔 실제 응답 확인, 최종 web 복원 |
| 백엔드 장애 | 같은 스크립트가 각 선택 백엔드를 실제 stop | 각각 502, 다른 앱으로 자동 폴백 없음, 최종 모두 복원 |
| 프록시 전송 | gateway 컨테이너: `python < scripts/test_gateway.py` | 3개 unittest 성공. 컨테이너 내부의 임시 HTTP 서버로 POST·쿼리·본문·쿠키·중복 Set-Cookie·201·hop-by-hop 제거·chunked WSGI 입력 검사 |
| 입력·오류 경계 | 같은 unittest | 잘못된/초과 Content-Length 및 제어문자 target 거부, 업스트림 I/O 오류 502, 비신뢰 소스 403 |
| 포트 | VM: `ss -lntp 'sport = :8080'`, Compose 구성 확인 | `100.102.19.44:8080`만 게시, 나머지 서비스 포트 없음 |
| 사설 IP 노출 | VM에서 TCP `10.10.10.158:8080` 접속 | refused(111), 해당 IP로 바인딩되지 않음 |
| 비Tailscale 유입 | 임시 기본 bridge Python 컨테이너에서 `100.102.19.44:8080` 접속 | 진입 제한 전 성공 재현, 제한 후 timeout/실패 확인 |
| 헤더·로그 보호 | VM: `python3 scripts/check_infra.py` | nginx/gateway/web의 동일 새 요청 ID 연결. 위조 XFF 무시. 쿼리·본문·Authorization·Cookie의 고유 테스트 마커가 로그에 없음 |
| 출발지 관측 | VM 자체 요청 및 사용자 PC 요청 로그 대조 | VM 요청은 `100.102.19.44`, PC 요청은 세 서비스 모두 `100.98.140.95` |
| 허니팟 TCP 격리 | honeypot에서 DNS가 아닌 실제 IP/포트 접속 | web `172.29.241.3:8000`, gateway의 세 네트워크 주소 `:8000`, nginx `172.29.240.2:80`, VM Tailscale `:8080`, 내부 브리지 `.1:8080` 모두 접속 실패 |
| 호스트 브리지 경계 | honeypot에서 `172.29.242.1:22` | 일반 internal에서는 성공 재현, isolated 적용 후 실패. 호스트 SSH 자체 서비스는 계속 active |
| 네트워크 설정 | `docker network inspect` | appnet/honeynet internal=true, gateway_mode_ipv4=isolated, MTU=1442 |
| 데이터·파일 분리 | 통합 스크립트: 두 서비스의 `/data`·`/files`에 같은 이름의 고유 임시 마커 생성 | 각 서비스 값이 서로 덮어쓰이지 않음 |
| 영속성 | 같은 스크립트가 web/honeypot 재시작 후 마커 재조회 | 유지 확인, 검사 후 자기 마커만 삭제 |
| 비루트·볼륨 권한 | 컨테이너에서 UID와 os.access 확인 | 앱·gateway UID 10001, 각 /data 쓰기 가능, 앱 /files readiness 정상 |
| Docker 재시작 | VM: `sudo systemctl restart docker`, 이후 `up -d --wait` | 4개 healthy 복원, 진입 제한 서비스 active 및 규칙 복원 |
| 기존 접속 서비스 | VM: `systemctl is-active tailscaled ssh` | 둘 다 active, Tailscale IPv4 유지 |
| 최종 통합 | Docker 재시작 후 unittest + `python3 -u scripts/check_infra.py` | 전 항목 PASS, 테스트 마커 정리, 기본 대상 web |
| 사용자 PC 접근 | 사용자 제공 Windows curl 결과, VM의 동일 요청 ID 로그 대조 | `/`와 `/healthz` 모두 200, 각각 web 임시 앱과 gateway ready 응답 확인 |

진입 제한은 `DOCKER-USER`의 프로젝트 Nginx 목적지 `172.29.240.2:80`만 대상으로 한다.
재적용을 두 번 수행해도 규칙이 한 개만 남는 것을 확인했고, Docker 재시작 후에도 한 개로 복원됐다.
전체 규칙 세트 교체나 UFW 활성화는 하지 않았다. 사용자 PC에서의 실제 Tailscale 웹 접속도 확인했다.

### 사용자 PC 검증 추가 기록

- 사용자 제공 응답 시각: 2026-11-12 10:30:38 KST(`/`), 10:30:40 KST(`/healthz`).
- `/` 응답 ID: `90024c9609b39fe95814ddf3c808f7af`.
- VM에서 `docker compose logs --no-color --since 2026-11-12T01:30:30Z --until 2026-11-12T01:30:50Z`를 조회하여
  해당 ID의 nginx/gateway/web 이벤트를 대조했다. 모두 상태 200, 출발지 `100.98.140.95`로 일치했다.
- 이 결과는 해당 PC의 접속과 요청 추적을 확인한다. 다른 팀원 권한이나 ACL의 최소 권한 설정까지 입증하지는 않는다.

## 발견한 문제와 적용한 수정

1. **원래 Ubuntu Nova apt 미러 응답 없음:** 시작한 apt update를 중단하고 Docker sources만 대상으로 갱신하여 설치했다.
   Ubuntu sources 파일은 그대로이므로 일반 OS 패키지 갱신에는 이 문제가 남아 있다.
2. **컨테이너 TLS handshake timeout:** ens3 MTU 1442와 Docker 기본 1500의 차이를 확인했다.
   임시 1442 네트워크의 동일 PyPI 요청은 200이었다. 새 Docker 기본 MTU와 프로젝트 네트워크를 1442로 맞춘 뒤 기본 bridge 요청·pip 빌드가 성공했다.
3. **최초 Compose tmpfs 목록 구문:** 쉼표가 포함된 옵션을 따옴표로 묶어 마운트 오류를 수정했다.
4. **Nginx 기본 access log의 쿼리 기록:** 임의 테스트 마커가 기본 combined 로그에 남는 것을 검사에서 발견했다.
   별도 nginx.conf로 기본 로그를 제거하고 제한된 JSON 로그만 사용하도록 바꾼 뒤 재검사를 통과했다. 시험에는 가짜 마커만 사용했다.
5. **Gunicorn 제어 소켓의 read-only 오류:** 필요 없는 제어 소켓을 `--no-control-socket`으로 비활성화했다.
6. **IP 바인딩만으로 타 인터페이스 접근 가능:** 다른 Docker bridge에서 게시된 Tailscale IP로 접속 성공을 재현했다.
   프로젝트 Nginx에만 적용하는 인터페이스 제한과 systemd 재적용을 추가했다.
7. **internal 네트워크의 호스트 브리지 SSH 접근:** 실제 TCP 연결을 확인한 후 두 백엔드에 isolated 모드를 적용하여 차단했다.

## 미확인·후속 작업과 한계

- **PC 후속 검사:** 사용자 PC의 기본 접속·readiness·실제 출발지·요청 ID 연결은 확인했다.
  위조 헤더 검사는 VM 내부에서 통과했으며 PC에서의 동일 검사는 미수행이다. 다른 팀원 PC도 접속을 개별 확인한다. [명령](runbook.md#접속).
- **관리자 정책:** Tailscale ACL/grants의 팀원별 VM TCP 8080 권한·장치 승인·기존 광범위 허용 여부는 원격 관리자 화면에서 확인해야 한다.
  OpenStack 정책도 조회·변경하지 않았다. 공인 포워딩/Funnel/Serve는 추가하지 않았다.
- **호스트 재부팅:** 수행하지 않았다. Docker 데몬 재시작은 검증했으나 재부팅 시 Tailscale IP 준비 순서는 별도 확인 대상이다.
  부팅 후 포트 바인딩이 실패하면 Tailscale 준비 후 `docker compose up -d --wait`를 실행한다.
- **백업·복원:** 운영 문서에 SQLite backup API와 중지 기반 볼륨 백업 방법을 적었다. 실제 데이터의 백업 복원 훈련은 미수행이다.
- **애플리케이션:** 인증·권한·서버 세션·성적·게시판·파일 기능과 의도적 취약/패치 버전은 후속 단계다.
  아직 로그인·세션·비밀키가 없으며 정상/허니팟 인증을 공유해서는 안 된다.
- **보안 기능:** 실제 WAF 규칙·재공격 조건·자동 분기·차단 목록·관리자 화면·사고 대응은 미구현이다.
  gateway는 고정 목적지로 전달하는 WSGI 골격이고 탐지율·차단율·오탐률은 측정하지 않았다.
- **로그:** 현재는 회전되는 서비스별 Docker stdout이며 관리자 화면/JSONL/SQLite 이벤트 검색·장기 보존은 미구현이다.
  호스트 관리자에게 로그 접근 권한이 있으며 향후 UI는 별도 권한 검사·출력 인코딩이 필요하다.
- **격리:** 검증한 앱·네트워크·볼륨 경계만 주장한다. 컨테이너 탈출·호스트 관리자·커널 취약점 방어를 입증한 것은 아니다.
  gateway는 두 백엔드에 연결되는 신뢰 구성 요소이고, 임의 목적지 프록시나 정상 DB 마운트를 허니팟에 추가하면 안 된다.
- **전송 범위:** 요청 1MiB/응답 4MiB 버퍼링 HTTP 전달만 구현했다. 대용량 스트리밍·WebSocket·부하 성능은 검증하지 않았다.

## 근거 문서

- [Docker 공식 Ubuntu 설치](https://docs.docker.com/engine/install/ubuntu/)
- [Docker 포트 게시·라우팅·isolated 모드](https://docs.docker.com/engine/network/port-publishing/)
- [Docker daemon MTU/default-network-opts](https://docs.docker.com/reference/cli/dockerd/)
- [Flask 공식 PyPI 배포](https://pypi.org/project/Flask/), [Gunicorn 공식 PyPI 배포](https://pypi.org/project/gunicorn/)

기동·중지·설정 변경·재검증·백업 절차는 [runbook.md](runbook.md)를 따른다.
