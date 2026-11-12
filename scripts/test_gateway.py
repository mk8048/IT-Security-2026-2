"""Run inside gateway: docker compose exec -T gateway python < scripts/test_gateway.py."""
import io
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

import gateway

REAL_CONNECTION = gateway.http.client.HTTPConnection
seen = {}


class Backend(BaseHTTPRequestHandler):
    def do_POST(self):
        seen.update(path=self.path, method=self.command, headers=self.headers,
                    body=self.rfile.read(int(self.headers.get("Content-Length", 0))))
        self.send_response(201)
        self.send_header("Set-Cookie", "a=1; HttpOnly")
        self.send_header("Set-Cookie", "b=2; HttpOnly")
        self.send_header("Connection", "X-Private")
        self.send_header("X-Private", "remove-me")
        self.end_headers()
        self.wfile.write(b"created")

    def log_message(self, *args):
        pass


class GatewayTest(unittest.TestCase):
    def environ(self):
        return {"REMOTE_ADDR": gateway.NGINX, "PATH_INFO": "/submit",
                "RAW_URI": "/submit?q=%2F+test", "REQUEST_METHOD": "POST",
                "CONTENT_LENGTH": "7", "CONTENT_TYPE": "text/plain",
                "HTTP_X_REQUEST_ID": "a" * 32, "HTTP_X_FORWARDED_FOR": "100.64.0.7",
                "HTTP_COOKIE": "test=value", "HTTP_CONNECTION": "X-Remove",
                "HTTP_X_REMOVE": "secret", "HTTP_FORWARDED": "spoofed",
                "wsgi.input": io.BytesIO(b"payload")}

    def test_transport(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), Backend)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with patch.object(gateway.http.client, "HTTPConnection",
                              side_effect=lambda *a, **kw: REAL_CONNECTION("127.0.0.1", server.server_port, timeout=2)):
                status, headers, body = gateway.proxy(self.environ())
            self.assertEqual((status, body), (201, b"created"))
            self.assertEqual([v for k, v in headers if k.lower() == "set-cookie"],
                             ["a=1; HttpOnly", "b=2; HttpOnly"])
            self.assertFalse(any(k.lower() in {"connection", "x-private"} for k, _ in headers))
            self.assertEqual(seen["path"], "/submit?q=%2F+test")
            self.assertEqual(seen["body"], b"payload")
            self.assertEqual(seen["headers"]["Cookie"], "test=value")
            self.assertEqual(seen["headers"]["X-Request-ID"], "a" * 32)
            self.assertNotIn("X-Remove", seen["headers"])
            self.assertNotIn("Forwarded", seen["headers"])
            env = self.environ()
            del env["CONTENT_LENGTH"]
            env["wsgi.input_terminated"] = True
            with patch.object(gateway.http.client, "HTTPConnection",
                              side_effect=lambda *a, **kw: REAL_CONNECTION("127.0.0.1", server.server_port, timeout=2)):
                self.assertEqual(gateway.proxy(env)[0], 201)
            self.assertEqual(seen["body"], b"payload")
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_limits_and_failure(self):
        for length, status in (("-1", 413), (str(gateway.LIMIT + 1), 413), ("bad", 400)):
            env = self.environ()
            env["CONTENT_LENGTH"] = length
            self.assertEqual(gateway.proxy(env)[0], status)
        env = self.environ()
        env["RAW_URI"] = "/bad\r\nheader"
        self.assertEqual(gateway.proxy(env)[0], 400)
        with patch.object(gateway.http.client.HTTPConnection, "endheaders", side_effect=OSError):
            self.assertEqual(gateway.proxy(self.environ())[0], 502)

    def test_untrusted_source(self):
        env = self.environ()
        env["REMOTE_ADDR"] = "172.29.242.3"
        result = []
        gateway.app(env, lambda status, headers: result.append(status))
        self.assertEqual(result, ["403 Forbidden"])


unittest.main()
