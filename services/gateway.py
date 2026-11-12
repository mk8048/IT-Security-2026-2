import http.client
import json
import os
import re
from http import HTTPStatus

from audit import audit

TARGET = os.environ.get("GATEWAY_TARGET", "web")
if TARGET not in {"web", "honeypot"}:
    raise ValueError("GATEWAY_TARGET must be web or honeypot")
NGINX = "172.29.240.2"
BIND = "172.29.240.3"
LIMIT = 1024 * 1024
RESPONSE_LIMIT = 4 * LIMIT
HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
       "te", "trailer", "transfer-encoding", "upgrade"}


def filtered(headers):
    excluded = HOP | {token.strip().lower() for key, value in headers
                      if key.lower() == "connection" for token in value.split(",")}
    return [(key, value) for key, value in headers if key.lower() not in excluded]


def proxy(environ):
    raw = environ.get("RAW_URI", environ.get("PATH_INFO", "/"))
    if not raw.startswith("/") or any(ord(c) < 32 or ord(c) == 127 for c in raw):
        return 400, [], b"Invalid request target\n"
    try:
        length = int(environ.get("CONTENT_LENGTH") or "0")
    except ValueError:
        return 400, [], b"Invalid content length\n"
    if length < 0 or length > LIMIT:
        return 413, [], b"Request too large\n"
    if environ.get("CONTENT_LENGTH"):
        body = environ["wsgi.input"].read(length)
    elif environ.get("wsgi.input_terminated"):
        body = environ["wsgi.input"].read(LIMIT + 1)
    else:
        body = b""
    if len(body) > LIMIT:
        return 413, [], b"Request too large\n"
    if environ.get("CONTENT_LENGTH") and len(body) != length:
        return 400, [], b"Incomplete body\n"
    length = len(body)
    headers = [(key[5:].replace("_", "-"), value) for key, value in environ.items()
               if key.startswith("HTTP_")]
    headers = [(key, value) for key, value in filtered(headers)
               if key.lower() not in {"host", "content-length", "forwarded", "x-real-ip"}
               and not key.lower().startswith("x-forwarded-")
               and key.lower() != "x-request-id"]
    headers += [("Host", TARGET), ("Content-Length", str(length)),
                ("X-Forwarded-For", environ["HTTP_X_FORWARDED_FOR"]),
                ("X-Forwarded-Proto", "http"),
                ("X-Request-ID", environ["HTTP_X_REQUEST_ID"])]
    if environ.get("CONTENT_TYPE"):
        headers.append(("Content-Type", environ["CONTENT_TYPE"]))
    conn = http.client.HTTPConnection(TARGET, 8000, timeout=5)
    try:
        conn.putrequest(environ["REQUEST_METHOD"], raw, skip_host=True, skip_accept_encoding=True)
        for key, value in headers:
            conn.putheader(key, value)
        conn.endheaders(body)
        response = conn.getresponse()
        data = response.read(RESPONSE_LIMIT + 1)
        if len(data) > RESPONSE_LIMIT:
            return 502, [], b"Backend response too large\n"
        return response.status, filtered(response.getheaders()), data
    except (OSError, http.client.HTTPException):
        return 502, [], b"Backend unavailable\n"
    finally:
        conn.close()


def ready():
    for service in ("web", "honeypot"):
        conn = http.client.HTTPConnection(service, 8000, timeout=2)
        try:
            conn.request("GET", "/healthz")
            response = conn.getresponse()
            if response.status != 200 or json.loads(response.read(4096))["service"] != service:
                return False
        except (OSError, http.client.HTTPException, ValueError, KeyError):
            return False
        finally:
            conn.close()
    return os.access("/data", os.W_OK)


class Gateway:
    """Pass-through WSGI scaffold; attack detection and automatic diversion are pending."""
    # shortcut: bounded buffered HTTP only; add streaming/WebSocket support when required.
    def __call__(self, environ, start_response):
        if environ.get("PATH_INFO") == "/healthz" and environ.get("REMOTE_ADDR") in {NGINX, BIND}:
            status = 200 if ready() else 503
            data = json.dumps({"service": "gateway", "status": "ready" if status == 200 else "unavailable"}).encode()
            start_response(f"{status} {HTTPStatus(status).phrase}", [("Content-Type", "application/json")])
            return [data]
        if (environ.get("REMOTE_ADDR") != NGINX
                or not re.fullmatch(r"[0-9a-f]{32}", environ.get("HTTP_X_REQUEST_ID", ""))):
            start_response("403 Forbidden", [("Content-Type", "text/plain")])
            return [b"Untrusted proxy\n"]
        status, headers, data = proxy(environ)
        headers = [(key, value) for key, value in headers if key.lower() != "x-request-id"]
        headers.append(("X-Request-ID", environ["HTTP_X_REQUEST_ID"]))
        audit("gateway", environ, status, "forwarded_to_" + TARGET if status != 502 else "backend_error")
        start_response(f"{status} {http.client.responses.get(status, 'Unknown')}", headers)
        return [data]


app = Gateway()
