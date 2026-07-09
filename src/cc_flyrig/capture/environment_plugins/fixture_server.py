"""P4: start a localhost always-429 fixture HTTP server for the scenario's lifetime.

``ANTHROPIC_BASE_URL`` is auto-injected so all of CC's API calls hit the fixture, forcing the
``StopFailure`` ``rate_limit`` path reproducibly, independent of stored credentials.
"""

from contextlib import contextmanager

from .base import EnvironmentPlugin, require_one_of
from .ratelimit_server import RateLimitServer

_SERVERS = frozenset({"ratelimit-429"})
_PORT = 8472


@contextmanager
def _server():
    """Start the always-429 server; yield the env addition that redirects CC to it."""
    with RateLimitServer(_PORT) as server:
        yield {"ANTHROPIC_BASE_URL": f"http://127.0.0.1:{server.port}"}


ENVIRONMENT_PLUGIN = EnvironmentPlugin(
    validate=lambda v: require_one_of(_SERVERS, v),
    configure=lambda v, ctx, plan: plan.run_contexts.append(_server()),
)
