import asyncio
from dataclasses import dataclass, field


@dataclass
class BridgeStats:
    bytes_up: int = 0
    bytes_down: int = 0
    errors: list[BaseException] = field(default_factory=list)


async def _pump(
    src: asyncio.StreamReader,
    dst: asyncio.StreamWriter,
    idle_timeout: float,
    stats: BridgeStats,
    direction: str,
) -> None:
    """Copies bytes from src to dst until EOF, an idle timeout, or an error. On a clean
    EOF from src, only half-closes dst's write side (write_eof) instead of tearing the
    whole connection down — the other direction may still be mid-transfer and a full
    close there would surface as a TCP RST on a connection that's still legitimately
    in use (this was the direct cause of the "Connection reset by peer" flood in the
    previous thread-based implementation)."""
    try:
        while True:
            data = await asyncio.wait_for(src.read(65536), timeout=idle_timeout)
            if not data:
                break
            dst.write(data)
            await dst.drain()
            if direction == 'up':
                stats.bytes_up += len(data)
            else:
                stats.bytes_down += len(data)
    except BaseException as exc:  # noqa: BLE001 - peer resets/timeouts are expected teardown noise
        stats.errors.append(exc)
    finally:
        try:
            if dst.can_write_eof():
                dst.write_eof()
        except Exception:
            pass


async def bridge(
    client_reader: asyncio.StreamReader,
    client_writer: asyncio.StreamWriter,
    upstream_reader: asyncio.StreamReader,
    upstream_writer: asyncio.StreamWriter,
    idle_timeout: float,
) -> BridgeStats:
    """Bidirectionally relays data between the client and upstream connections until
    both directions have finished (cleanly or otherwise), then returns stats/errors for
    the caller to log/classify. Never raises — connection teardown races are normal."""
    stats = BridgeStats()
    await asyncio.gather(
        _pump(
            src=client_reader, dst=upstream_writer, idle_timeout=idle_timeout,
            stats=stats, direction='up',
        ),
        _pump(
            src=upstream_reader, dst=client_writer, idle_timeout=idle_timeout,
            stats=stats, direction='down',
        ),
    )
    return stats
