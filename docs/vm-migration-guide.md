# VM 이전 가이드

작성일: 2026-11-12. 현재 프로젝트를 다른 Linux VM으로 옮길 때 사용하는 실행 절차다.
**이 문서 작성 시 실제 VM 이전·전체 볼륨 복원은 수행하지 않았다. 아래 명령은 이전 시 환경을 확인한 뒤 실행한다.**
에이전트에게는 저장소 루트의 [handoff.md](../handoff.md)를 함께 전달한다.

## 1. 이전 대상과 완료 기준

| 구분 | 이전 방법 |
| --- | --- |
| 코드·Compose·템플릿·운영 문서 | GitHub에서 대상 커밋 checkout |
| 미커밋 코드 | 이전 전 확인 후 필요한 내용을 커밋하거나 별도 보존 |
| `.env` | 보안 경로로 별도 보존, 새 VM에서 새 IP로 재작성 |
| DB·앱 파일·게이트웨이 데이터 | 프로젝트 볼륨 5개를 정지 상태에서 백업·복원 |
| Docker 호스트 설정 | 새 VM에 맞춰 설치·병합·검증 |
| 진입 제한 서비스 | `infra/security-lab-ingress*`에서 설치 |
| GitHub·SSH·Tailscale·에이전트 인증 | 새 VM에서 별도 준비. 기존 VM의 키·장치 상태를 통째 복제하지 않음 |
| Docker stdout 로그 | 볼륨에 포함되지 않음. 보존 필요 시 별도 내보내기 |

이전 완료는 새 VM의 4개 서비스 healthy, 데이터 보존, 정상·허니팟 경로, 격리·로그 보호, 실제 PC 접속 확인을 기준으로 한다.
단순히 `docker compose up`이 성공한 것만으로 완료 처리하지 않는다.

실제 접근 설계는 Tailscale 직접 연결이다. `infra-status-report.md`의 공인 IP 가정은 배포 지시가 아니다.
현재 VM의 IP `100.102.19.44`와 경로 `/home/ubuntu/security-lab`는 참고값이며 새 VM에서 다시 확인한다.

## 2. 이전 전 준비 — 기존 VM

프로젝트 루트에서 다음 상태를 기록한다. 이 단계에서는 서비스를 중지하지 않는다.

```sh
git status --short --branch
git rev-parse HEAD
sudo docker compose ps
sudo docker version
sudo docker compose version
sudo docker volume ls --filter label=com.docker.compose.project=security-lab
```

필요한 미커밋 파일과 문서가 원격에 있는지 확인한다. 이전 대상 커밋을 기록하고, 복원은 우선 그 커밋으로 수행한다.
새 문서가 아직 로컬에만 있으면 별도 복사하거나 커밋·푸시한 뒤 clone해야 한다.

현재 데이터 볼륨 이름은 다음과 같다. 실제 이름·소유 프로젝트를 확인하고 다른 볼륨으로 대체하지 않는다.

```text
security-lab_web-data
security-lab_web-files
security-lab_honeypot-data
security-lab_honeypot-files
security-lab_gateway-data
```

앱 데이터는 UID/GID `10001:10001` 기준이다. 이후 앱 버전에서 볼륨·소유자·DB 구조가 바뀌면 해당 버전 기준으로 절차를 수정한다.
현재 DB는 인프라 메타데이터뿐이지만, 보존 여부를 임의로 판단하여 생략하지 않는다.

## 3. 데이터 백업 — 기존 VM, 점검 시간

아래 예시는 현재의 rootful Docker와 로컬 명명 볼륨을 전제로 한다. 원격 Docker·rootless Docker·다른 볼륨 드라이버라면 먼저 저장 방식을 확인한다.
**네 서비스를 정지하므로 점검 시간에 실행한다. 볼륨 삭제 명령은 사용하지 않는다.**

다음 블록은 프로젝트 루트의 하나의 Bash 세션에서 실행한다. `.env`가 존재하고 읽을 수 있어야 한다.

```bash
set -eu
umask 077
backup_dir="$PWD/backups/migration-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$backup_dir"
chmod 700 "$backup_dir"
git rev-parse HEAD > "$backup_dir/source-commit.txt"
git status --short > "$backup_dir/source-worktree.txt"
sudo docker compose stop

for suffix in web-data web-files honeypot-data honeypot-files gateway-data; do
  volume="security-lab_${suffix}"
  project_label=$(sudo docker volume inspect "$volume" --format '{{index .Labels "com.docker.compose.project"}}')
  test "$project_label" = security-lab
  test -z "$(sudo docker ps -q --filter "volume=$volume")"
  volume_path=$(sudo docker volume inspect "$volume" --format '{{.Mountpoint}}')
  test -n "$volume_path"
  sudo tar --numeric-owner -C "$volume_path" -czf - . > "$backup_dir/$volume.tar.gz.tmp"
  mv "$backup_dir/$volume.tar.gz.tmp" "$backup_dir/$volume.tar.gz"
done

install -m 0600 .env "$backup_dir/runtime.env"
(
  cd "$backup_dir"
  sha256sum ./*.tar.gz runtime.env source-commit.txt source-worktree.txt > SHA256SUMS
  sha256sum -c SHA256SUMS
  for archive in ./*.tar.gz; do tar -tzf "$archive" >/dev/null; done
)
printf 'Backup directory: %s\n' "$backup_dir"
```

다섯 볼륨을 모두 정지한 상태에서 복사하므로 SQLite DB 및 관련 파일과 앱 파일을 함께 보존한다.
아카이브에는 숫자 UID/GID가 보존된다. 모든 쓰기 프로세스가 정지되어 있는 것이 전제다.
실패하면 `.tmp` 파일을 완료 백업으로 사용하지 않는다. 위 블록은 오류 발생 시 자동으로 서비스를 재개하지 않는다.

Docker 로그도 보존해야 한다면 정지된 기존 컨테이너에서 `docker compose logs`로 별도 내보내고, 민감정보 포함 여부와 보관 권한을 확인한다.
이전 검증 동안 기존 VM은 정지 상태로 유지하는 것을 기본으로 한다.
백업 후 기존 VM을 다시 운영했다면 데이터가 바뀔 수 있으므로 전환 직전에 쓰기를 중지하고 최종 백업을 새로 만든다.

## 4. 백업 전송 및 무결성 확인

백업 디렉터리 전체를 SSH/SCP 등 인증된 경로로 새 VM 또는 관리 PC에 복사한다. 예시는 **관리 PC**에서 실행한다.
호스트·경로를 실제 값으로 바꾸고, SSH 호스트 키는 별도 확인한다. 호스트 키 검증을 끄지 않는다.

```sh
scp -r 'ubuntu@OLD_VM_SSH_HOST:/absolute/path/to/migration-backup' ./migration-backup
scp -r ./migration-backup 'ubuntu@NEW_VM_SSH_HOST:/absolute/path/to/backups/'
```

새 VM에서 백업 디렉터리 권한을 700으로 제한하고 파일은 600으로 보관한다. `sha256sum -c SHA256SUMS`로 전송 결과를 확인한다.
체크섬은 전송 오류를 확인하는 수단이며 출처가 불명확한 아카이브의 안전성을 보증하지 않는다. 직접 만든 신뢰 가능한 백업만 복원한다.
기존 VM 안에만 남은 백업은 VM 삭제에 대비한 백업이 아니므로 별도 위치의 복사본을 반드시 확보한다.
`.env`·DB·원본 로그·아카이브를 GitHub나 채팅에 올리지 않는다.

## 5. 새 VM 준비

### 5.1. 환경과 실행 도구

새 VM에서 기존 설정을 먼저 확인한다.

```sh
cat /etc/os-release
uname -m
nproc
free -h
df -h /
ip -brief address
ip route
ip -o link show
ss -lntp
sudo -n true
```

기준 환경은 Ubuntu 24.04, vCPU 4개, 메모리 약 8GB다. 기존에 설치된 Docker나 다른 프로젝트가 있다면 재사용 가능성을 확인한다.
Docker가 없으면 [공식 Ubuntu 설치 절차](https://docs.docker.com/engine/install/ubuntu/)로 Engine과 Compose 플러그인을 설치한다.
기존 검증 버전은 Engine 29.9.3 / Compose 5.7.1이다. 다른 버전은 isolated 모드와 Compose 옵션을 지원하는지 다시 검증한다.
구버전에서 오류가 난다고 isolated 설정을 제거하여 진행하지 않는다.

### 5.2. 저장소와 인증

기본 clone 주소는 다음과 같다. 비공개 저장소라면 먼저 해당 VM의 읽기 인증을 준비한다.

```sh
git clone https://github.com/mk8048/IT-Security-2026-2.git security-lab
cd security-lab
```

백업을 프로젝트의 `backups/` 아래로 옮긴 후 실제 디렉터리를 지정한다. 다음 단계에서도 같은 Bash 세션의 `backup_dir`를 사용한다.

```bash
set -eu
backup_dir="$PWD/backups/migration-YYYYMMDDTHHMMSSZ"
test -d "$backup_dir"
chmod 700 "$backup_dir"
(cd "$backup_dir" && sha256sum -c SHA256SUMS)
source_commit=$(cat "$backup_dir/source-commit.txt")
git switch -c migration-restore "$source_commit"
```

`migration-YYYYMMDDTHHMMSSZ`는 실제 디렉터리 이름으로 바꾼다.
대상 커밋이 없으면 먼저 원격에서 가져오고, 같은 브랜치가 이미 있으면 덮어쓰지 않고 상태를 확인한다.
백업 당시 미커밋 변경이 있으면 `source-worktree.txt`와 별도로 보존한 파일도 대조한다.

현재 VM의 Git 커밋 작성자는 `Lee mingi <mk8048@naver.com>`이다. 새 VM에서는 작업자의 정보를 확인한 뒤 저장소 로컬 설정에 적용한다.
기존 저장소는 전용 SSH deploy key로 push하도록 설정했지만, `.git/config`와 개인키는 clone에 포함되지 않는다.
push가 필요하면 새 VM 전용 키를 새로 만들고 GitHub의 해당 저장소 Deploy keys에 쓰기 권한을 포함해 등록한다.
개인키를 저장소·컨테이너에 넣거나 기존 VM의 SSH 설정 전체를 복사하지 않는다. clone만 필요하면 push 인증을 기다릴 필요는 없다.

### 5.3. MTU와 서브넷

기존 VM의 외부 인터페이스 MTU는 1442였으며 Compose의 세 네트워크에도 1442가 명시되어 있다.
새 VM의 실제 경로 MTU를 확인하고 컨테이너 HTTPS 연결을 검사한다. 기존 값이 모든 VM의 정답이라고 가정하지 않는다.
기본 bridge를 사용하는 이미지 빌드에도 영향을 주므로 필요하면 `/etc/docker/daemon.json`의 `mtu`와
`default-network-opts.bridge.com.docker.network.driver.mtu`를 조정한다.
기존 JSON을 보존·병합하고 `sudo dockerd --validate --config-file=/etc/docker/daemon.json`으로 검사한다.
Docker 재시작은 다른 컨테이너에 영향을 주므로 새 VM에서 그 영향을 확인한 뒤 수행한다.

다음 서브넷이 새 VM의 경로·기존 Docker 네트워크와 겹치지 않는지 확인한다.

```text
frontnet  172.29.240.0/24
appnet    172.29.241.0/24
honeynet  172.29.242.0/24
```

충돌이 없으면 내부 주소는 유지한다. 변경해야 하면 아래 파일을 함께 수정하고 신뢰 경계·통신 검사를 다시 수행한다.

- `compose.yaml`: 서브넷, 서비스 고정 주소, gateway bind·healthcheck, 앱 `TRUSTED_GATEWAY`.
- `services/gateway.py`: `NGINX`, `BIND`.
- `infra/security-lab-ingress`: Nginx 목적지 주소.
- `scripts/check_infra.py`: 실제 접속 검사 대상 주소.
- `scripts/test_gateway.py`의 주소와 `docs/runbook.md`, 인계 문서의 주소 설명도 대조.

### 5.4. 접근 주소와 호스트 진입 제한

Tailscale이 없다면 공식 설치·연결 절차로 새 VM을 별도 장치로 준비한다. 로그인·장치 승인은 사용자가 수행한다.
기존 VM의 장치 상태 파일을 복사하거나 기존 연결을 끊지 않는다. 새 장치의 접근 권한도 별도로 확인한다.

```sh
tailscale ip -4
```

`.env`가 없는 새 프로젝트에서 `install -m 0600 "$backup_dir/runtime.env" .env`로 보존된 설정을 가져올 수 있다.
그다음 `HOST_BIND_IP`를 **새 VM의 실제 Tailscale IPv4**로 수정하고 `GATEWAY_TARGET=web`인지 확인한다.
인증이 준비되지 않았으면 `HOST_BIND_IP=127.0.0.1`로 먼저 검증한다. 이미 `.env`가 있으면 덮어쓰기 전에 차이를 확인한다.
향후 추가된 앱 비밀키 등은 필요한 값을 보존하되 정상 앱·허니팟 간 공유하지 않는다. 값을 로그에 출력하지 않는다.

포트 게시 전에 프로젝트 진입 제한을 설치한다. 이 규칙은 `tailscale0`와 Nginx 고정 주소를 전제로 한다.

```sh
sudo install -m 0755 infra/security-lab-ingress /usr/local/sbin/security-lab-ingress
sudo install -m 0644 infra/security-lab-ingress.service /etc/systemd/system/security-lab-ingress.service
sudo systemctl daemon-reload
sudo systemctl enable --now security-lab-ingress.service
sudo systemctl is-active security-lab-ingress.service
sudo iptables -S DOCKER-USER
```

설치 대상 파일이나 같은 이름의 서비스가 이미 있으면 먼저 기존 내용을 확인한다.
Docker의 iptables 및 `DOCKER-USER` 체인을 사용하는 구성이 전제다. 다른 방화벽 백엔드는 그대로 통과시키지 말고 경계를 다시 설계한다.
웹 진입을 공인 IP·0.0.0.0·공개 터널로 자동 대체하지 않는다. 원격 접근 정책은 팀원의 새 VM TCP 8080 접근에 필요한 범위로 준비한다.

## 6. 볼륨 복원 — 새 VM, 앱 기동 전

먼저 대상 커밋의 이미지를 빌드하고 **기동하지 않은 채** 컨테이너와 볼륨만 만든다.

```sh
sudo docker compose config --quiet
sudo docker compose build
sudo docker compose create
```

데이터가 있는 기존 볼륨에 덮어쓰지 않는다. 다음 블록은 볼륨 5개의 소유 프로젝트·정지·빈 상태와 백업을
**모두 먼저 검사한 뒤** 복원한다. 빈 상태가 아니면 중단하고 별도 백업 및 복원 대상을 정한다.

```bash
set -eu
test -d "$backup_dir"
(cd "$backup_dir" && sha256sum -c SHA256SUMS)

for suffix in web-data web-files honeypot-data honeypot-files gateway-data; do
  volume="security-lab_${suffix}"
  project_label=$(sudo docker volume inspect "$volume" --format '{{index .Labels "com.docker.compose.project"}}')
  test "$project_label" = security-lab
  test -z "$(sudo docker ps -q --filter "volume=$volume")"
  volume_path=$(sudo docker volume inspect "$volume" --format '{{.Mountpoint}}')
  test -n "$volume_path"
  test -z "$(sudo ls -A "$volume_path")"
  test -f "$backup_dir/$volume.tar.gz"
  tar -tzf "$backup_dir/$volume.tar.gz" >/dev/null
done

for suffix in web-data web-files honeypot-data honeypot-files gateway-data; do
  volume="security-lab_${suffix}"
  volume_path=$(sudo docker volume inspect "$volume" --format '{{.Mountpoint}}')
  sudo tar --numeric-owner --same-owner -C "$volume_path" -xzf "$backup_dir/$volume.tar.gz"
done
```

복원 중 실패하면 기존 VM은 그대로 보존하고, 새 VM의 부분 복원 볼륨을 완료 상태로 취급하지 않는다.
같은 명령을 기존 데이터 위에 반복 실행하지 않는다. 실패 원인을 확인하고 새 빈 복원 대상을 준비한다.
전체 `/var/lib/docker`, Docker 소켓, 컨테이너 런타임 디렉터리를 복사하는 방식은 사용하지 않는다.

앱을 시작하기 전에 아카이브와 복원 파일을 비교하고 SQLite 무결성을 검사한다.

```bash
for suffix in web-data web-files honeypot-data honeypot-files gateway-data; do
  volume="security-lab_${suffix}"
  volume_path=$(sudo docker volume inspect "$volume" --format '{{.Mountpoint}}')
  sudo tar --compare --gzip --numeric-owner -C "$volume_path" -f "$backup_dir/$volume.tar.gz"
done

for service in web honeypot; do
  sudo docker compose run --rm --no-deps --entrypoint python "$service" -c 'import sqlite3; c=sqlite3.connect("file:/data/app.sqlite3?mode=ro",uri=True); assert c.execute("PRAGMA integrity_check").fetchall()==[("ok",)]; c.close(); print("SQLite integrity: ok")'
done
```

단순히 빈 DB가 정상 기동한 것을 복원 성공으로 오해하지 않는다. 새 앱을 먼저 실행하여 빈 DB를 만들었다면 위의 빈 볼륨 검사에서 중단되어야 한다.
데이터를 보존하지 않는 신규 구축을 원한다면 사용자에게 그 선택을 명확히 확인한 후 별도 절차로 진행한다.

## 7. 새 VM 기동·검증 및 전환

프로젝트 루트에서 다음 명령을 순서대로 실행한다. 뒤의 두 스크립트는 서비스 중지·재시작을 포함한다.

```sh
sudo docker compose up -d --wait --wait-timeout 120
sudo docker compose ps
sudo docker compose exec -T nginx nginx -t
sudo docker compose exec -T gateway python < scripts/test_gateway.py
bash scripts/check_routes.sh
python3 scripts/check_infra.py
```

현재 `scripts/check_infra.py`는 1단계 Hello World 앱, 고정 내부 IP와 현재 로그 필드를 전제로 한다.
향후 앱의 `/` 응답이나 주소가 달라졌다면 새 요구사항에 맞게 검사도 갱신한다. 기존 검사 실패를 무시하지 않는다.

| 검사 | 새 VM 통과 기준 |
| --- | --- |
| 서비스 상태 | 4개 healthy, 기본 `GATEWAY_TARGET=web` |
| 데이터 | 아카이브 비교·SQLite 무결성 성공, 필요한 기존 파일·기록 보존 |
| 저장소 | 앱·gateway UID 10001, 볼륨 쓰기 가능, web/honeypot 데이터 분리 |
| 포트 | Nginx의 지정 IP TCP 8080만 호스트 게시, 다른 인터페이스 바인딩 없음 |
| 경로 | 정상 앱 HTML과 상태 응답, 허니팟 전달, 장애 시 502·폴백 금지 |
| 네트워크 | 허니팟에서 정상 앱·호스트 게시 포트·gateway 우회·호스트 브리지 접근 제한 |
| 로그 | 새 요청 ID 연결, 위조 헤더 무시, 민감값 미기록 |
| 유지 | 프로젝트 진입 규칙 active, 재시작 후 필요한 데이터와 상태 유지 |
| 외부 PC | 실제 팀원 PC에서 새 VM URL로 HTTP 200 확인 |

새 VM에서 `tailscale ip -4`로 확인한 IP를 팀원에게 전달한다.
각 PC 브라우저에서 `http://새_VM_TAILSCALE_IP:8080/`를 열고, 터미널에서는 다음처럼 확인한다.

```sh
curl --max-time 10 -i http://NEW_VM_TAILSCALE_IP:8080/
curl --max-time 10 -i http://NEW_VM_TAILSCALE_IP:8080/healthz
```

위 주소의 자리표시자는 새 IP로 치환한다. VM 내부 curl은 외부 PC 확인을 대신하지 않는다.
PC 요청의 응답 ID를 VM 로그의 nginx/gateway/web 이벤트와 대조하고 관측된 출발지도 기록한다.
호스트 재부팅을 검사하려면 별도 점검 시간을 잡고 승인된 범위에서 수행한다. Docker 데몬 재시작과 호스트 재부팅을 같은 검사로 보고하지 않는다.
부팅 후 Tailscale 준비 전 포트 바인딩이 실패하면 네트워크 준비 후 `docker compose up -d --wait`로 다시 시작한다.

기존 VM과 새 VM이 동시에 데이터를 받지 않도록 검증 이후 접속 주소를 새 VM으로 전환한다.
전환 후 새 VM에서 쓰기가 시작되면 기존 백업으로 되돌릴 때 그 이후 데이터가 사라질 수 있다.
검증 결과·새 환경 버전·접속 주소·백업 시점·대상 커밋·미확인 항목을 별도 이전 결과 문서로 기록한다.
기존 `infra-status.md`의 과거 증빙은 지우지 않고, 운영 문서와 이 인계 문서의 현재값을 갱신한다.

## 8. 실패 시 복귀와 기존 VM 정리

새 VM 검증에 실패했고 새 쓰기를 받지 않았다면 새 서비스를 중지하고 기존 VM을 다시 기동한다.
다음 명령은 **기존 VM**의 프로젝트 루트에서만 실행한다.

```sh
sudo docker compose up -d --wait --wait-timeout 120
```

기존 URL로 사용자 접속을 복원하고 기본 경로·상태를 재확인한다.
새 VM에서 쓰기가 발생했다면 두 환경의 차이를 먼저 확인하여 필요한 데이터를 회수한다. 이전 백업을 무조건 덮어쓰지 않는다.
전환 성공과 데이터 보존을 사용자가 확인할 때까지 기존 VM·볼륨·외부 백업은 유지한다.
기존 VM 삭제와 볼륨 삭제는 이 가이드의 자동 작업 범위가 아니다.
기존 VM을 최종 폐기할 때는 해당 VM의 GitHub deploy key와 장치 접근 권한도 회수한다. 새 VM의 키나 기존 관리 접속 키와 혼동하지 않는다.

## 9. 참고 문서

- [Docker 공식 Ubuntu 설치](https://docs.docker.com/engine/install/ubuntu/)
- [Docker 명명 볼륨과 백업·복원](https://docs.docker.com/engine/storage/volumes/)
- [Docker 포트 게시와 isolated 모드](https://docs.docker.com/engine/network/port-publishing/)
- [Tailscale 장치 연결](https://tailscale.com/docs/how-to/connect-to-devices)
- [실제 구축·검증 기록](infra-status.md), [운영 방법](runbook.md)
