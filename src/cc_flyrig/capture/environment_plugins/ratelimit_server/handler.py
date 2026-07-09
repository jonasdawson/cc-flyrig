"""HTTP request handler that always responds 429 rate_limit_error (P4 capture fixture)."""

import json
from http.server import BaseHTTPRequestHandler


class RateLimitHandler(BaseHTTPRequestHandler):
    def _respond_429(self):
        body = json.dumps(
            {"type": "error", "error": {"type": "rate_limit_error", "message": "Rate limit reached (capture fixture)"}}
        ).encode()
        self.send_response(429)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # Respond 429 to any HTTP method — CC POSTs /v1/messages but pre-flight checks may use other verbs.
    def do_GET(self):
        self._respond_429()

    def do_POST(self):
        self._respond_429()

    def do_HEAD(self):
        self._respond_429()

    def do_OPTIONS(self):
        self._respond_429()

    def log_message(self, *args):  # silence per-request stderr noise
        pass
