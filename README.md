# IT-Security-2026-2
정보보호 및 보안 팀프로젝트

가상 성적관리 서비스에서 웹 취약점 재현·패치·WAF·허니팟을 검증하는 실습 프로젝트입니다.
현재는 Docker Compose 기반 1단계 인프라와 Hello World 임시 앱까지 구현했습니다.

- [프로젝트 제안서](docs/proposal.md)
- [설치·운영·이전 시 준비 사항](docs/runbook.md)
- [실제 검증 결과와 미구현 항목](docs/infra-status.md)
- [VM 이전 가이드](docs/vm-migration-guide.md)
- [새 VM의 에이전트용 인계](handoff.md)

새 VM에서는 운영 문서에 따라 Docker·Tailscale·호스트 진입 제한을 준비한 뒤 실행합니다.

```sh
cp .env.example .env
# .env의 HOST_BIND_IP를 확인합니다. 기본값은 127.0.0.1입니다.
sudo docker compose up -d --build --wait --wait-timeout 120
```

DB·파일은 Docker 볼륨에 저장됩니다. `.env`와 실행 데이터는 Git에 포함하지 않으며 VM 이전 시 별도 백업·복원이 필요합니다.
