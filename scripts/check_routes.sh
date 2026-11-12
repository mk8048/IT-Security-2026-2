#!/bin/bash
# Temporarily switches the target and stops backends; run only during maintenance.
set -eu
cd "$(dirname "$0")/.."
bind_ip=$(sudo -n docker compose config --format json | python3 -c 'import sys,json; d=json.load(sys.stdin); assert d["services"]["gateway"]["environment"]["GATEWAY_TARGET"]=="web"; print(d["services"]["nginx"]["ports"][0]["host_ip"])')
restore() {
  sudo -n docker compose up -d --wait --wait-timeout 90
}
trap restore EXIT
sudo -n env GATEWAY_TARGET=honeypot docker compose up -d --no-deps --force-recreate --wait --wait-timeout 90 gateway
curl -fsS --max-time 10 "http://$bind_ip:8080/" | python3 -c 'import sys,json; assert json.load(sys.stdin)["service"]=="honeypot"; print("PASS nginx → gateway → honeypot")'
sudo -n docker compose stop honeypot
test "$(curl -sS --max-time 10 -o /dev/null -w '%{http_code}' "http://$bind_ip:8080/")" = 502
echo 'PASS honeypot failure returns 502, without fallback to web'
restore
sudo -n docker compose stop web
test "$(curl -sS --max-time 10 -o /dev/null -w '%{http_code}' "http://$bind_ip:8080/")" = 502
echo 'PASS web failure returns 502, without fallback to honeypot'
restore
curl -fsS --max-time 10 "http://$bind_ip:8080/" | python3 -c 'import sys; assert "data-service=\"web\"" in sys.stdin.read(); print("PASS default web route restored")'
trap - EXIT
