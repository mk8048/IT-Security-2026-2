import json
from datetime import datetime, timezone


def audit(service, environ, status, result):
    # Only these fields are collected; credentials, query and body stay out.
    print(json.dumps({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "request_id": environ.get("HTTP_X_REQUEST_ID", ""),
        "service": service,
        "event_type": "http_request",
        "source_ip": environ.get("HTTP_X_FORWARDED_FOR", environ.get("REMOTE_ADDR", "")),
        "method": environ.get("REQUEST_METHOD", ""),
        "path": environ.get("PATH_INFO", "")[:200],
        "status": status,
        "result": result,
    }), flush=True)
