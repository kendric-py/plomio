import asyncio


class TunnelError(Exception):
    """Base class for all errors raised while bridging one SOCKS5 connection."""


class ClientProtocolError(TunnelError):
    """The local (browser-facing) side sent something that isn't valid SOCKS5."""


class ClientDisconnected(TunnelError):
    """The local (browser-facing) side closed/reset the connection."""


class UpstreamProtocolError(TunnelError):
    """The upstream proxy sent something that isn't valid SOCKS5."""


class UpstreamAuthFailed(TunnelError):
    """The upstream proxy rejected the username/password we hold for it."""


class UpstreamUnreachable(TunnelError):
    """We couldn't open a TCP connection to the upstream proxy itself."""


class UpstreamRejected(TunnelError):
    """The upstream proxy accepted the TCP connection but replied to CONNECT with a
    non-zero REP code (RFC 1928 §6): target unreachable, ruleset, refused, etc."""

    def __init__(self, rep_code: int) -> None:
        self.rep_code = rep_code
        super().__init__(f'upstream CONNECT rejected: REP=0x{rep_code:02x}')


class TunnelAtCapacity(TunnelError):
    """No connection slot (global or per-tunnel) was available."""


class UpstreamCircuitOpen(TunnelError):
    """The upstream proxy has been failing enough recently that we're fast-failing
    new CONNECTs instead of hammering it further."""


def classify(exc: BaseException) -> str:
    """Maps an exception to a short, stable tag used for metrics/log aggregation."""
    if isinstance(exc, UpstreamRejected):
        return f'upstream_rejected_0x{exc.rep_code:02x}'
    if isinstance(exc, UpstreamAuthFailed):
        return 'upstream_auth_failed'
    if isinstance(exc, UpstreamCircuitOpen):
        return 'upstream_circuit_open'
    if isinstance(exc, UpstreamUnreachable):
        return 'upstream_unreachable'
    if isinstance(exc, UpstreamProtocolError):
        return 'upstream_protocol_error'
    if isinstance(exc, ClientProtocolError):
        return 'client_protocol_error'
    if isinstance(exc, ClientDisconnected):
        return 'client_disconnected'
    if isinstance(exc, TunnelAtCapacity):
        return 'tunnel_at_capacity'
    if isinstance(exc, (ConnectionResetError, BrokenPipeError)):
        return 'connection_reset'
    if isinstance(exc, ConnectionError):
        return 'connection_closed'
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
        return 'timeout'
    return f'other_{type(exc).__name__}'


# Errors normal for a live browser session bridging real-world traffic: the browser
# cancelling an in-flight sub-resource on navigation, an upstream leg being dropped,
# a slow/idle peer timing out. Not actionable on their own, so logged quieter than
# genuine proxy-health problems (auth failures, REP rejections, circuit-open).
EXPECTED_TEARDOWN_NOISE = frozenset({
    'connection_reset',
    'connection_closed',
    'client_disconnected',
    'timeout',
})


def rep_for(exc: BaseException) -> int:
    """Best-effort SOCKS5 REP code to report back to the client for a given error."""
    if isinstance(exc, UpstreamRejected):
        return exc.rep_code
    if isinstance(exc, (UpstreamUnreachable, ConnectionRefusedError)):
        return 0x05  # connection refused
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
        return 0x06  # TTL expired
    return 0x01  # general SOCKS server failure
