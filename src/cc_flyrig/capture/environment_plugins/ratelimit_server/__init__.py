"""Context manager that runs a rate-limit fixture HTTP server on a daemon thread (P4)."""

from http.server import HTTPServer
from threading import Thread

from .handler import RateLimitHandler


class RateLimitServer:
    """Context manager that runs an always-429 HTTP server on a daemon thread."""

    def __init__(self, port: int):
        self._httpd = HTTPServer(("127.0.0.1", port), RateLimitHandler)
        self._thread = Thread(target=self._httpd.serve_forever, daemon=True)

    @property
    def port(self) -> int:
        return self._httpd.server_address[1]

    def __enter__(self) -> "RateLimitServer":
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()
