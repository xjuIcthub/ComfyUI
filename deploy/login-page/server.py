#!/usr/bin/env python3
import argparse
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

PUBLIC_FILES = {
    "/index.html",
    "/register.html",
    "/styles.css",
    "/app.js",
    "/runtime-config.js",
}
PUBLIC_HOSTS = {"login.icthub.top", "register.icthub.top"}
PREVIEW_HOSTS = {"127.0.0.1", "localhost", "::1"}


class LoginPageHandler(SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _public_path(self):
        host = self.headers.get("Host", "").rsplit(":", 1)[0].strip("[]").lower()
        if host not in PUBLIC_HOSTS | PREVIEW_HOSTS:
            return None

        path = urlsplit(self.path).path
        if path == "/":
            return "/register.html" if host == "register.icthub.top" else "/index.html"
        return path if path in PUBLIC_FILES else None

    def _serve(self, head_only=False):
        path = self._public_path()
        if path is None:
            self.send_error(404)
            return
        self.path = path
        if head_only:
            super().do_HEAD()
        else:
            super().do_GET()

    def do_GET(self):
        self._serve()

    def do_HEAD(self):
        self._serve(head_only=True)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", "default-src 'self'; base-uri 'none'; form-action https://auth.icthub.top; frame-ancestors 'none'; object-src 'none'")
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Permissions-Policy", "camera=(), geolocation=(), microphone=()")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        super().end_headers()

    def log_message(self, message, *args):
        path = urlsplit(self.path).path
        status = next((str(value) for value in args if str(value).isdigit() and len(str(value)) == 3), "-")
        sys.stderr.write(f'{self.client_address[0]} - "{self.command} {path}" {status}\n')


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Serve the ICThub branded authentication entry pages.")
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8190)
    parser.add_argument("--directory", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()

    handler = partial(LoginPageHandler, directory=str(args.directory.resolve()))
    server = ThreadingHTTPServer((args.bind, args.port), handler)
    server.serve_forever()
