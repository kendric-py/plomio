import asyncio
import logging
from types import TracebackType

from worker_sessions.config import config
from worker_sessions.generation.socks5_tunnel.bridge import bridge
from worker_sessions.generation.socks5_tunnel.errors import (
    ClientProtocolError,
    UpstreamCircuitOpen,
    UpstreamRejected,
    UpstreamUnreachable,
    classify,
    rep_for,
)
from worker_sessions.generation.socks5_tunnel.limiter import ConnectionLimiter
from worker_sessions.generation.socks5_tunnel.metrics import (
    ErrorLogThrottle,
    UpstreamCircuitBreaker,
)
from worker_sessions.generation.socks5_tunnel.protocol import (
    ConnectRequest,
    read_client_handshake,
    upstream_connect,
)

logger = logging.getLogger(__name__)


class Socks5Tunnel:
    """A local, unauthenticated SOCKS5 listener that bridges every accepted connection
    to an upstream SOCKS5 proxy using real credentials — lets Camoufox (which can't do
    SOCKS5 auth) use an authenticated upstream proxy transparently.

    Runs entirely as asyncio tasks on the caller's event loop: no per-connection OS
    thread, so `stop()` can actually wait for every in-flight connection to finish
    (or cancel it) instead of leaving orphaned threads behind.
    """

    def __init__(self, host: str, port: int, username: str, password: str) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._server: asyncio.AbstractServer | None = None
        self.port: int = 0

        tunnel_config = config.SOCKS5_TUNNEL
        self._label = f'{host}:{port}'
        self._limiter = ConnectionLimiter(
            global_limit=tunnel_config.MAX_GLOBAL_CONNECTIONS,
            per_tunnel_limit=tunnel_config.MAX_PER_TUNNEL_CONNECTIONS,
        )
        self._error_throttle = ErrorLogThrottle(
            window_s=tunnel_config.ERROR_LOG_THROTTLE_WINDOW_S, tunnel_label=self._label,
        )
        self._circuit = UpstreamCircuitBreaker(
            failure_threshold=tunnel_config.CIRCUIT_BREAKER_FAILURE_THRESHOLD,
            window_s=tunnel_config.CIRCUIT_BREAKER_WINDOW_S,
            cooldown_s=tunnel_config.CIRCUIT_BREAKER_COOLDOWN_S,
            tunnel_label=self._label,
        )
        self._tasks: set[asyncio.Task] = set()

    async def start(self) -> None:
        self._server = await asyncio.start_server(
            self._on_client_connected, '127.0.0.1', 0, backlog=config.SOCKS5_TUNNEL.LISTEN_BACKLOG,
        )
        self.port = self._server.sockets[0].getsockname()[1]
        logger.debug('[tunnel] event=started tunnel=%s port=%d', self._label, self.port)

    async def stop(self) -> None:
        """Stops accepting new connections, then gives in-flight bridges a grace period
        to finish on their own before cancelling whatever's left."""
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

        pending = [task for task in self._tasks if not task.done()]
        if pending:
            drain_timeout = config.SOCKS5_TUNNEL.STOP_DRAIN_TIMEOUT_S
            _done, still_pending = await asyncio.wait(pending, timeout=drain_timeout)
            for task in still_pending:
                task.cancel()
            if still_pending:
                await asyncio.gather(*still_pending, return_exceptions=True)

        self._error_throttle.close()
        logger.debug('[tunnel] event=stopped tunnel=%s', self._label)

    async def __aenter__(self) -> 'Socks5Tunnel':
        await self.start()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self.stop()

    def _on_client_connected(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
    ) -> None:
        task = asyncio.ensure_future(self._bridge_one(client_reader=reader, client_writer=writer))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _bridge_one(
        self, client_reader: asyncio.StreamReader, client_writer: asyncio.StreamWriter,
    ) -> None:
        tunnel_config = config.SOCKS5_TUNNEL

        if not self._limiter.try_acquire():
            logger.warning('[tunnel] event=connection_limit_reached tunnel=%s', self._label)
            await self._close_quietly(client_writer)
            return

        upstream_writer: asyncio.StreamWriter | None = None
        request: ConnectRequest | None = None
        try:
            try:
                request = await asyncio.wait_for(
                    read_client_handshake(reader=client_reader, writer=client_writer),
                    timeout=tunnel_config.CLIENT_HANDSHAKE_TIMEOUT_S,
                )
            except ClientProtocolError:
                return  # request-level rejection already replied to the client in-protocol

            if self._circuit.is_open():
                raise UpstreamCircuitOpen('upstream circuit open — fast-failing')

            try:
                upstream_reader, upstream_writer = await asyncio.wait_for(
                    asyncio.open_connection(host=self._host, port=self._port),
                    timeout=tunnel_config.UPSTREAM_CONNECT_TIMEOUT_S,
                )
            except (OSError, asyncio.TimeoutError) as exc:
                raise UpstreamUnreachable(str(exc)) from exc

            try:
                reply = await asyncio.wait_for(
                    upstream_connect(
                        reader=upstream_reader, writer=upstream_writer,
                        username=self._username, password=self._password, request=request,
                    ),
                    timeout=tunnel_config.UPSTREAM_CONNECT_TIMEOUT_S,
                )
            except UpstreamRejected:
                self._circuit.record_failure()
                raise
            self._circuit.record_success()

            client_writer.write(reply)
            await client_writer.drain()
            logger.debug(
                '[tunnel] event=bridge_established tunnel=%s port=%d', self._label, request.port,
            )

            stats = await bridge(
                client_reader=client_reader,
                client_writer=client_writer,
                upstream_reader=upstream_reader,
                upstream_writer=upstream_writer,
                idle_timeout=tunnel_config.PIPE_IDLE_TIMEOUT_S,
            )
            for exc in stats.errors:
                self._error_throttle.record(error_type=classify(exc), detail=str(exc))

        except Exception as exc:
            self._error_throttle.record(error_type=classify(exc), detail=str(exc))
            if request is not None:
                await self._try_send_failure_reply(writer=client_writer, exc=exc)
        finally:
            self._limiter.release()
            await self._close_quietly(client_writer)
            if upstream_writer is not None:
                await self._close_quietly(upstream_writer)

    @staticmethod
    async def _try_send_failure_reply(writer: asyncio.StreamWriter, exc: Exception) -> None:
        try:
            if writer.is_closing():
                return
            rep = rep_for(exc)
            writer.write(bytes([0x05, rep, 0x00, 0x01, 0, 0, 0, 0, 0, 0]))
            await writer.drain()
        except Exception:
            pass

    @staticmethod
    async def _close_quietly(writer: asyncio.StreamWriter) -> None:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass
