"""Network-isolated portal smoke check with fictional HTTP upstreams only.

Run as the image's non-root user, mounting just this file read-only. This checks
the real rendered Nginx routing and headers; it never contacts an Auth provider.
"""

import json
import os
import subprocess
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from sherlock_api.deployment import portal_children


class Upstream(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({"path": self.path, "headers": dict(self.headers)}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def main():
    assert os.geteuid() != 0
    public_key = "sb_publishable_" + "a" * 32
    config = {
        "PATH": os.environ["PATH"],
        "PUBLIC_ORIGIN": "https://sherlock.example.test",
        "PUBLIC_KEY": public_key,
        "JWT_SECRET": "b" * 64,
        "AUTH_DATABASE_URL": "postgresql://auth:fictional@db/realm?sslmode=verify-full",
        "REST_DATABASE_URL": "postgresql://rest:fictional@db/realm?sslmode=verify-full",
        "SMTP_HOST": "smtp.example.com",
        "SMTP_PORT": "587",
        "SMTP_FROM": "noreply@example.test",
        "SMTP_USER": "fictional",
        "SMTP_PASSWORD": "fictional",
        "API_UPSTREAM": "http://127.0.0.1:8000",
    }
    portal_children(config)
    servers = [
        ThreadingHTTPServer(("127.0.0.1", port), Upstream)
        for port in (9999, 3000, 8000)
    ]
    for server in servers:
        Thread(target=server.serve_forever, daemon=True).start()
    process = subprocess.Popen(
        ["nginx", "-c", "/tmp/nginx.conf", "-g", "daemon off;"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    def request(path, headers=None):
        try:
            with urlopen(
                Request("http://127.0.0.1:8080" + path, headers=headers or {}),
                timeout=2,
            ) as response:
                return response.status, response.read()
        except HTTPError as error:
            return error.code, error.read()

    try:
        deadline = time.monotonic() + 5
        while True:
            try:
                assert request("/healthz")[0] == 200
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.05)
        assert request("/register")[0] == 200
        assert request("/assets/missing.js")[0] == 404
        for path in (
            "/auth/v1/admin/users",
            "/auth/v1/ADMIN/users",
            "/auth/v1/metrics",
        ):
            assert request(path)[0] == 404
        assert request("/auth/v1/user", {"apikey": public_key})[0] == 400
        assert (
            request("/auth/v1/user", {"X-Envoy-External-Address": "192.0.2.4"})[0]
            == 401
        )
        headers = {
            "apikey": public_key,
            "X-Envoy-External-Address": "192.0.2.4",
            "X-Forwarded-For": "203.0.113.9",
            "X-Real-IP": "203.0.113.9",
            "X-Forwarded-Host": "evil.example.test",
            "X-Forwarded-Proto": "http",
            "Authorization": "Bearer " + public_key,
        }
        status, body = request("/auth/v1/user", headers)
        assert status == 200
        forwarded = {
            name.lower(): value for name, value in json.loads(body)["headers"].items()
        }
        assert forwarded["x-real-ip"] == forwarded["x-forwarded-for"] == "192.0.2.4"
        assert forwarded["x-forwarded-proto"] == "https"
        assert "x-forwarded-host" not in forwarded and "authorization" not in forwarded
        assert (
            request(
                "/auth/v1/verify?token=fictional-test-token",
                {
                    "X-Envoy-External-Address": "192.0.2.4",
                },
            )[0]
            == 200
        )
        assert request("/rest/v1/profiles")[0] == 401
        assert request("/rest/v1/profiles", headers)[0] == 200
        assert request("/api/v1/system")[0] == 200
    finally:
        process.terminate()
        output, errors = process.communicate(timeout=5)
        for server in servers:
            server.shutdown()
        assert b"fictional-test-token" not in output + errors
    print("Portal routing, private management routes and trusted-header checks passed.")


if __name__ == "__main__":
    main()
