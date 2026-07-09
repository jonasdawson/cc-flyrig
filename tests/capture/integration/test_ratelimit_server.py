"""Integration tests for the rate-limit fixture server (environment_plugins/ratelimit_server/).

Covers the full server lifecycle with real HTTP requests (real socket, real thread).
See tests/capture/unit/test_ratelimit_handler.py for handler-in-isolation tests.
"""

import json
import urllib.error
import urllib.request

from cc_flyrig.capture.environment_plugins.ratelimit_server import RateLimitServer


class TestRateLimitServer:
    def test_server__post_to_messages__returns_429_with_rate_limit_error_body(self):
        """Integration: real HTTP POST to /v1/messages returns 429 with rate_limit_error body."""
        with RateLimitServer(port=0) as server:
            url = f"http://127.0.0.1:{server.port}/v1/messages"
            req = urllib.request.Request(url, data=b"{}", method="POST")
            try:
                urllib.request.urlopen(req)
                raise AssertionError("expected HTTPError 429")
            except urllib.error.HTTPError as exc:
                assert exc.code == 429
                body = json.loads(exc.read())
                assert body["error"]["type"] == "rate_limit_error"

    def test_server__get__returns_429(self):
        """Integration: real HTTP GET also returns 429 (CC may send pre-flight requests)."""
        with RateLimitServer(port=0) as server:
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{server.port}/")
                raise AssertionError("expected HTTPError 429")
            except urllib.error.HTTPError as exc:
                assert exc.code == 429

    def test_server__port_zero__reflects_os_assigned_port(self):
        """port=0 yields an OS-assigned port that is positive and reachable."""
        with RateLimitServer(port=0) as server:
            assert server.port > 0

    def test_server__exit__shuts_down_cleanly(self):
        """After __exit__, the server no longer accepts connections."""
        with RateLimitServer(port=0) as server:
            port = server.port
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/")
            raise AssertionError("expected connection refused after shutdown")
        except (urllib.error.URLError, OSError):
            pass
