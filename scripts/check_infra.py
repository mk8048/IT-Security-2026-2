"""Non-destructive VM checks. Uses unique temporary markers and preserves volumes."""
import http.client
import json
import os
from pathlib import Path
import subprocess
import uuid

os.chdir(Path(__file__).resolve().parents[1])
COMPOSE = ["sudo", "-n", "docker", "compose"]


def compose(*args, code=None):
    return subprocess.check_output(COMPOSE + list(args), input=code, text=True)


def inside(service, code):
    return compose("exec", "-T", service, "python", "-c", code)


config = json.loads(compose("config", "--format", "json"))
published = [(name, port) for name, svc in config["services"].items() for port in svc.get("ports", [])]
assert len(published) == 1 and published[0][0] == "nginx", published
port = published[0][1]
host = port["host_ip"]
assert host == "127.0.0.1" or host in subprocess.check_output(["tailscale", "ip", "-4"], text=True).split()
assert str(port["published"]) == "8080"
assert config["networks"]["appnet"]["internal"] and config["networks"]["honeynet"]["internal"]
for svc in ("web", "honeypot", "gateway"):
    assert inside(svc, "import os; assert os.getuid()==10001; assert os.access('/data',os.W_OK)") == ""
print("PASS configuration, sole published port, non-root apps and writable storage")

token = "infra-secret-" + uuid.uuid4().hex
conn = http.client.HTTPConnection(host, 8080, timeout=10)
conn.request("GET", "/?password=" + token, headers={"X-Forwarded-For": "203.0.113.99",
             "X-Request-ID": "spoofed-id", "Authorization": "Bearer " + token, "Cookie": "session=" + token})
response = conn.getresponse()
request_id = response.getheader("X-Request-ID")
assert response.status == 200 and response.getheader("Content-Type").startswith("text/html")
assert b'data-service="web"' in response.read()
assert request_id and len(request_id) == 32 and request_id != "spoofed-id"
conn.close()
conn = http.client.HTTPConnection(host, 8080, timeout=10)
conn.request("POST", "/", body="password=" + token, headers={"Content-Type": "application/x-www-form-urlencoded"})
response = conn.getresponse()
assert response.status == 405
response.read()
conn.close()
logs = compose("logs", "--no-color", "--since", "2m")
assert token not in logs, "Sensitive marker leaked into logs"
events = []
for line in logs.splitlines():
    try:
        event = json.loads(line.split("|", 1)[1].strip())
    except (ValueError, IndexError):
        continue
    if event.get("request_id") == request_id:
        events.append(event)
assert {e["service"] for e in events} == {"nginx", "gateway", "web"}, events
assert all(e["source_ip"] != "203.0.113.99" for e in events), events
print("PASS nginx → gateway → web, request ID correlation, forged headers and credential log exclusion")
print("Observed source IPs:", sorted({e["source_ip"] for e in events}))

targets = [("172.29.241.3", 8000), ("172.29.241.2", 8000),
           ("172.29.242.2", 8000), ("172.29.240.3", 8000),
           ("172.29.240.2", 80), (host, 8080), ("172.29.242.1", 8080),
           ("172.29.242.1", 22)]
inside("honeypot", "import socket\nfor host,port in " + repr(targets) + ":\n"
       " try:\n  s=socket.create_connection((host,port),timeout=1)\n"
       " except OSError:\n  print('BLOCKED',host,port)\n"
       " else:\n  s.close(); raise AssertionError(('isolation bypass',host,port))")
print("PASS honeypot TCP isolation: web, gateway on all networks, nginx and host published port")

marker = ".infra-check-" + uuid.uuid4().hex
try:
    for svc in ("web", "honeypot"):
        inside(svc, "from pathlib import Path\nfor root in ('/data','/files'):\n"
               f" Path(root+'/{marker}').write_text('{svc}')")
    for svc in ("web", "honeypot"):
        inside(svc, "from pathlib import Path\nfor root in ('/data','/files'):\n"
               f" assert Path(root+'/{marker}').read_text()=='{svc}'")
    compose("restart", "web", "honeypot")
    compose("up", "-d", "--wait", "--wait-timeout", "90")
    for svc in ("web", "honeypot"):
        inside(svc, "from pathlib import Path\nfor root in ('/data','/files'):\n"
               f" assert Path(root+'/{marker}').read_text()=='{svc}'")
    print("PASS separate data/files and persistence after application restart")
finally:
    for svc in ("web", "honeypot"):
        inside(svc, "from pathlib import Path\nfor root in ('/data','/files'):\n"
               f" Path(root+'/{marker}').unlink(missing_ok=True)")
print("PC-to-VM Tailscale access requires a separate test from the user's PC.")
