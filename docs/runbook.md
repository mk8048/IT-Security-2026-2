# 1단계 인프라 운영 방법

프로젝트 루트: `/home/ubuntu/security-lab`.
실제 상태와 검증 범위는 [infra-status.md](infra-status.md)를 참조한다.
VM 변경 시에는 [VM 이전 가이드](vm-migration-guide.md)와 [에이전트 인계](../handoff.md)를 따른다. 소스 clone만으로 데이터와 호스트 설정이 이전되지는 않는다.
현재 앱은 **인프라 임시 앱**이다. 로그인·성적·게시판·파일 다운로드·실제 WAF·자동 재공격 전환은 미구현이다.

## 접속

- 팀원 PC 주소: **http://100.102.19.44:8080/**
- 준비 상태: **http://100.102.19.44:8080/healthz**
- PC에서 Tailscale을 켜고 이 VM에 접근 가능한 tailnet 계정으로 연결한다.
- `/`는 `Hello World!`와 임시 앱 안내가 있는 HTML 페이지를 반환한다. 브라우저에서 위 접속 주소를 열면 된다.
- `/healthz`의 200 응답은 게이트웨이 및 두 백엔드의 상태 점검을 통과했다는 뜻이다.

PC 터미널에서 실행한다. Windows PowerShell에서는 필요하면 `curl.exe`를 사용한다.

```sh
tailscale ping 100.102.19.44
curl --max-time 10 -i http://100.102.19.44:8080/
curl --max-time 10 -i http://100.102.19.44:8080/healthz
curl --max-time 10 -i -H "X-Forwarded-For: 203.0.113.99" -H "X-Request-ID: pc-spoof-test" http://100.102.19.44:8080/
```

마지막 응답의 `X-Request-ID`는 새 32자리 16진수여야 한다. VM에서 아래 로그를 확인하여
동일 ID가 nginx/gateway/web에 연결되고, 출발지가 위조 값 대신 PC의 실제 관측 Tailscale IP인지 확인한다.
VM 자체에서 성공한 curl은 PC 접속 검증을 대신하지 않는다.

Tailscale 관리자 정책에서는 팀원 계정/그룹에서 이 VM의 TCP 8080으로만 필요한 웹 접근을 허용한다.
기존 광범위 허용 규칙도 함께 검토해야 하며, 좁은 규칙을 추가하는 것만으로 넓은 허용이 취소되지는 않는다.
SSH 관리 권한은 기존 정책을 보존하고 별도로 관리한다. 이 작업에서 원격 ACL이나 OpenStack 보안 그룹은 변경하지 않았다.
Tailscale 직접 터널 경로와 일반 사설 IP 경로는 다르므로 사설 IP의 8080을 외부로 열지 않는다.

## 시작·중지·재빌드

호스트 Docker 그룹은 변경하지 않았다. 아래 명령을 프로젝트 루트에서 일반 사용자로 실행한다.

```sh
cd /home/ubuntu/security-lab
sudo docker compose config --quiet
sudo docker compose up -d --build --wait --wait-timeout 120
sudo docker compose ps
sudo docker compose logs --tail 100 -f
```

중지 및 재시작:

```sh
sudo docker compose stop
sudo docker compose up -d --wait --wait-timeout 120
```

`stop`은 볼륨과 컨테이너를 보존한다. `down`도 기본적으로 명명된 볼륨을 보존하지만 컨테이너와 프로젝트 네트워크를 제거한다.
`down -v`, 볼륨 삭제, `docker system prune`는 데이터 삭제 작업이므로 일반 운영 절차로 실행하지 않는다.
프로세스 종료는 `unless-stopped`로 재시작하지만 unhealthy만으로 자동 재시작하지는 않는다. 의도적으로 `stop`한 서비스는 명시적으로 시작한다.

코드/Dockerfile/requirements 변경은 위의 `up -d --build`를 사용한다.
Nginx 설정 변경 후 `sudo docker compose exec -T nginx nginx -t`로 검사하고
`sudo docker compose restart nginx`로 적용한다. `.env` 변경은 `restart`만으로 반영되지 않으므로 `up -d`로 재생성한다.

## 설정과 통신 경계

`.env`는 버전 관리에서 제외했고 권한은 600이다. `.env.example`은 안전한 localhost 예시다.

| 설정 | 현재 값 | 의미 |
| --- | --- | --- |
| `HOST_BIND_IP` | `100.102.19.44` | Nginx의 유일한 호스트 웹 포트 8080 바인딩 |
| `GATEWAY_TARGET` | `web` | 고정된 실험 대상. `web` 또는 `honeypot`만 허용 |

Tailscale이 준비되지 않은 새 VM에서는 `HOST_BIND_IP=127.0.0.1`로 시작한다.
`tailscale status`, `tailscale ip -4`로 연결을 확인한 후 실제 IP를 명시한다.
인증/장치 승인은 사용자가 Tailscale 화면에서 수행하며 비밀값을 채팅에 붙여 넣지 않는다.
기존 VM의 Tailscale 재등록이나 `tailscale down`은 필요 없다.
IP가 없어져도 전체 인터페이스로 자동 전환하지 않는다. `.env` IP가 바뀌면 해당 값과 바인딩을 갱신한다.

요청은 `PC → Tailscale → nginx → gateway → web 또는 honeypot` 순서다.

| 네트워크 | 연결·주소 | 설정 |
| --- | --- | --- |
| frontnet | nginx `172.29.240.2`, gateway `172.29.240.3` | `172.29.240.0/24`, MTU 1442 |
| appnet | gateway `172.29.241.2`, web `172.29.241.3` | internal + isolated, `172.29.241.0/24` |
| honeynet | gateway `172.29.242.2`, honeypot `172.29.242.3` | internal + isolated, `172.29.242.0/24` |

고정 IP는 신뢰 프록시와 리스닝 경계를 위해 사용한다. 전달 목적지는 IP 대신 서비스명으로 해석한다.
서브넷 변경 시 Compose 주소·게이트웨이 bind/신뢰 주소·앱 신뢰 주소·Nginx 진입 제한 규칙·검사 스크립트를 함께 바꿔야 한다.
web과 honeypot에는 호스트 포트가 없고, gateway는 frontnet 주소의 8000에서만 수신한다.
두 내부 네트워크의 isolated 모드는 브리지의 호스트 주소를 없앤다. 컨테이너는 완전한 VM 수준 격리가 아니며 호스트 관리자·Docker 소켓 접근자는 신뢰 경계 밖이다.

## 호스트에 추가한 설정

- Docker 공식 apt 키와 저장소: `/etc/apt/keyrings/docker.asc`, `/etc/apt/sources.list.d/docker.sources`.
- `/etc/docker/daemon.json`: MTU 1442 및 새 bridge 네트워크 MTU 기본값. 빌드 컨테이너의 TLS 멈춤 현상을 해결했다.
- `/usr/local/sbin/security-lab-ingress`, `/etc/systemd/system/security-lab-ingress.service`:
  `DOCKER-USER`에서 **목적지 172.29.240.2의 TCP 80**에 대한 전달 트래픽 중 `tailscale0` 외 인터페이스의 유입만 차단한다.
  호스트 자체 OUTPUT 경로는 허용되어 VM 내부 검사가 가능하다. 기존 SSH·Tailscale 규칙은 유지한다.
  이 규칙은 이 프로젝트의 고정 IP를 전제로 하므로 프로젝트 네트워크를 다른 용도로 재사용하지 않는다.

Docker의 IP 바인딩만으로 수신 인터페이스가 제한되지는 않는다. 위 규칙을 함께 유지한다.
설치 원본은 `infra/security-lab-ingress*`이며 재설치는 다음과 같다.

```sh
sudo install -m 0755 infra/security-lab-ingress /usr/local/sbin/security-lab-ingress
sudo install -m 0644 infra/security-lab-ingress.service /etc/systemd/system/security-lab-ingress.service
sudo systemctl daemon-reload
sudo systemctl enable --now security-lab-ingress.service
sudo systemctl status security-lab-ingress.service --no-pager
sudo iptables -S DOCKER-USER
```

서비스는 Docker 시작·재시작에 연동된다. 방화벽 전체 초기화나 기존 규칙 저장본의 통째 복원은 하지 않는다.
호스트 Docker 설정 변경/재시작은 다른 프로젝트가 추가되면 그 영향도 확인해야 한다.
Docker 설치 중 기존 Ubuntu Nova 미러가 응답하지 않아 Docker 저장소만 대상으로 apt update를 수행했다.
원래 Ubuntu sources 파일은 수정하지 않았으므로 OS 패키지 갱신 시 미러 상태를 별도로 확인한다.

## 저장소와 백업

| 볼륨 | 컨테이너 경로 | 소유 서비스 |
| --- | --- | --- |
| `security-lab_web-data` | `/data/app.sqlite3` 등 | web |
| `security-lab_web-files` | `/files` | web |
| `security-lab_honeypot-data` | `/data/app.sqlite3` 등 | honeypot |
| `security-lab_honeypot-files` | `/files` | honeypot |
| `security-lab_gateway-data` | `/data` | gateway |

현재 DB는 서비스 식별용 인프라 메타데이터만 담는다. 계정·세션과 WAF 상태 데이터는 아직 없다.
비밀키가 필요한 인증 기능을 구현할 때 정상 앱과 허니팟에 서로 다른 키를 공급한다.
소스 공유 이미지를 사용하지만 프로세스·DB·파일·데이터 볼륨은 분리되어 있다.

SQLite만 백업하는 예시다. Python SQLite 백업 API를 사용하며 실행 중 DB 파일을 무작정 복사하지 않는다.
프로젝트 루트에서 서비스별로 실행한다.

```sh
mkdir -p backups
chmod 700 backups
stamp=$(date -u +%Y%m%dT%H%M%SZ)
for service in web honeypot; do
  backup_file="backups/${service}-${stamp}.sqlite3"
  if sudo docker compose exec -T "$service" python -c 'import os,sqlite3; src=sqlite3.connect("/data/app.sqlite3"); dst=sqlite3.connect("/tmp/snapshot.sqlite3"); src.backup(dst); dst.close(); src.close(); os.chmod("/tmp/snapshot.sqlite3",0o600)'; then
    if sudo docker compose exec -T "$service" python -c 'import sys; sys.stdout.buffer.write(open("/tmp/snapshot.sqlite3","rb").read())' > "$backup_file.tmp"; then
      mv "$backup_file.tmp" "$backup_file"
      chmod 600 "$backup_file"
      sudo docker compose exec -T "$service" python -c 'import os; os.unlink("/tmp/snapshot.sqlite3")'
    else
      echo "Backup copy failed: $service" >&2
      break
    fi
  else
    echo "SQLite backup failed: $service" >&2
    break
  fi
done
```

DB와 파일의 동일 시점 백업이 필요하면 gateway/web/honeypot을 먼저 중지하고,
`docker volume inspect`로 확인한 이 프로젝트의 5개 볼륨 경로를 각각 tar로 보관한다.
중지 중에도 볼륨을 삭제하지 않는다. 백업은 `backups/`처럼 접근 권한을 제한한 경로에 보관하고 Git에 넣지 않는다.
복원은 해당 서비스를 중지한 상태에서 수행하고 컨테이너 UID/GID `10001:10001`의 쓰기 권한을 유지한다.
복원은 기존 데이터를 덮어쓰므로 별도 작업으로 검토하고, 원본 백업을 먼저 확보한다.

## 로깅과 프록시 범위

요청 이벤트는 UTC 시각·request_id·service·event_type·source_ip·method·길이 200자의 path·status·result만 JSON stdout에 남긴다.
쿼리, 본문, Authorization, Cookie/Set-Cookie, 비밀번호, 원본 세션 토큰은 기본 수집하지 않는다.
URL 경로 자체에도 비밀값을 넣지 않는다. Nginx는 새 ID와 실제 연결 IP로 프록시 헤더를 설정하고,
gateway는 Nginx의 고정 주소만, 앱은 각 네트워크의 gateway 주소만 신뢰한다.
로컬 및 내부 readiness 요청은 사용자 요청 ID가 없을 수 있다. Gunicorn/이미지의 시작·종료 진단은 일반 텍스트다.
Docker 로그는 서비스별 `10MB × 3개`로 회전한다. 조회는 호스트 관리자/sudo 권한으로 제한되며 웹 관리자 로그 화면·JSONL/SQLite 이벤트 검색은 후속 구현이다.
향후 관리자 화면에서는 저장된 의심 입력에도 출력 인코딩을 적용해야 한다.

게이트웨이는 메서드·원본 쿼리·본문·상태·중복 Set-Cookie를 보존하고 hop-by-hop 헤더와 Connection이 지정한 헤더를 제거한다.
업스트림 타임아웃은 5초, 요청 상한은 1MiB, 버퍼링 응답 상한은 4MiB이다. Nginx도 요청을 1MiB로 제한한다.
백엔드 오류는 502로 반환하며 다른 서비스로 폴백하지 않는다.
대용량 스트리밍·WebSocket·실제 WAF 검사·사용자 지정 프록시 목적지는 지원하지 않는다.

## 재검증

```sh
sudo docker compose config --quiet
sudo docker compose exec -T nginx nginx -t
sudo docker compose exec -T gateway python < scripts/test_gateway.py
python3 scripts/check_infra.py
bash scripts/check_routes.sh
```

`check_infra.py`는 앱을 재시작해 보존을 검사하므로 잠깐 요청이 실패할 수 있다.
`check_routes.sh`는 고정 대상을 허니팟으로 임시 변경하고 각 백엔드를 중지하여 장애 응답을 검사한다.
점검 시간에만 실행한다. 종료 시 기본 web 경로·서비스를 복원하며 `.env`는 변경하지 않는다.
검사 중 연결이 끊기거나 강제 종료되면 `sudo docker compose up -d --wait --wait-timeout 120`으로 기본값을 복원한다.

PC 접속 실패 시 VM에서 `tailscale status`, `tailscale ip -4`, `sudo docker compose ps`,
`ss -lnt 'sport = :8080'`, `sudo systemctl status security-lab-ingress --no-pager`,
`sudo docker compose logs --tail 100`을 확인한다. 사용자 PC 연결·원격 ACL·장치 승인 문제는 VM 내부 curl로 확정하지 않는다.

## 참고

- [Docker Ubuntu 설치](https://docs.docker.com/engine/install/ubuntu/)
- [Docker 포트 게시·isolated 네트워크·다른 인터페이스 라우팅](https://docs.docker.com/engine/network/port-publishing/)
- [Docker daemon MTU와 기본 네트워크 옵션](https://docs.docker.com/reference/cli/dockerd/)
