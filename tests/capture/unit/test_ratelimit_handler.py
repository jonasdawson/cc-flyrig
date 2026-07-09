"""Unit tests for the rate-limit HTTP handler (environment_plugins/ratelimit_server/handler.py).

Exercises RateLimitHandler in isolation with mocked socket I/O — no real socket or thread.
See tests/capture/integration/test_ratelimit_server.py for full server lifecycle tests.
"""

import json
from io import BytesIO
from unittest.mock import Mock

from cc_flyrig.capture.environment_plugins.ratelimit_server.handler import RateLimitHandler


class TestRateLimitHandler:
    def _make_handler(self) -> RateLimitHandler:
        """Build a handler with socket I/O mocked out — no thread or port needed."""
        handler = RateLimitHandler.__new__(RateLimitHandler)
        handler.wfile = BytesIO()
        handler.send_response = Mock()
        handler.send_header = Mock()
        handler.end_headers = Mock()
        return handler

    def test_do_post__calls__sends_429_status(self):
        h = self._make_handler()
        h.do_POST()
        h.send_response.assert_called_once_with(429)

    def test_do_get__calls__sends_429_status(self):
        h = self._make_handler()
        h.do_GET()
        h.send_response.assert_called_once_with(429)

    def test_do_head__calls__sends_429_status(self):
        h = self._make_handler()
        h.do_HEAD()
        h.send_response.assert_called_once_with(429)

    def test_do_options__calls__sends_429_status(self):
        h = self._make_handler()
        h.do_OPTIONS()
        h.send_response.assert_called_once_with(429)

    def test_do_post__calls__writes_rate_limit_error_body(self):
        h = self._make_handler()
        h.do_POST()
        body = json.loads(h.wfile.getvalue())
        assert body["error"]["type"] == "rate_limit_error"

    def test_log_message__any_args__does_not_raise(self):
        h = self._make_handler()
        h.log_message("GET /v1/messages HTTP/1.1", "200", "-")
