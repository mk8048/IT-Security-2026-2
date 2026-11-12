import os
import sqlite3

from flask import Flask, jsonify, render_template, request
from audit import audit

SERVICE = os.environ["SERVICE_NAME"]
TRUSTED_GATEWAY = os.environ["TRUSTED_GATEWAY"]
DB = "/data/app.sqlite3"
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024
with sqlite3.connect(DB) as db:
    db.execute("CREATE TABLE IF NOT EXISTS infrastructure (service TEXT NOT NULL)")
    if not db.execute("SELECT 1 FROM infrastructure").fetchone():
        db.execute("INSERT INTO infrastructure VALUES (?)", (SERVICE,))


@app.before_request
def trust_proxy():
    if request.remote_addr != TRUSTED_GATEWAY:
        if request.path == "/healthz" and request.remote_addr == "127.0.0.1":
            return None
        return jsonify(error="untrusted_proxy"), 403


@app.after_request
def log_response(response):
    if request.remote_addr == TRUSTED_GATEWAY:
        audit(SERVICE, request.environ, response.status_code, "served")
    return response


@app.get("/")
def index():
    if SERVICE == "web":
        return render_template("index.html", service=SERVICE)
    return jsonify(service=SERVICE, stage="infrastructure_skeleton",
                   message="Temporary app: authentication, grades and WAF are not implemented.")


@app.get("/healthz")
def health():
    try:
        with sqlite3.connect(DB, timeout=2) as db:
            assert db.execute("SELECT service FROM infrastructure").fetchone()[0] == SERVICE
        if not all(os.access(path, os.W_OK) for path in ("/data", "/files")):
            raise OSError("storage unavailable")
        return jsonify(service=SERVICE, status="ready")
    except (sqlite3.Error, AssertionError, OSError):
        return jsonify(service=SERVICE, status="unavailable"), 503
