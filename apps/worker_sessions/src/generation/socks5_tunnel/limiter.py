import threading

_global_lock = threading.Lock()
_global_semaphore: threading.Semaphore | None = None


def _get_global_semaphore(limit: int) -> threading.Semaphore:
    """Returns the single process-wide semaphore shared by every Socks5Tunnel instance,
    across every thread/event loop (pool_manager runs one event loop per worker thread).
    threading.Semaphore.acquire(blocking=False)/release() are thread-safe and don't
    block the calling event loop, so tunnels can use it directly from async code. Only
    the limit passed by the first tunnel created in the process takes effect."""
    global _global_semaphore
    with _global_lock:
        if _global_semaphore is None:
            _global_semaphore = threading.Semaphore(limit)
        return _global_semaphore


class ConnectionLimiter:
    """Caps concurrently-bridged connections both per-tunnel and process-wide. Purely
    non-blocking: a connection that can't get a slot is rejected immediately rather than
    queued, so bursts fail fast instead of piling up."""

    def __init__(self, global_limit: int, per_tunnel_limit: int) -> None:
        self._global_sem = _get_global_semaphore(global_limit)
        self._per_tunnel_limit = per_tunnel_limit
        self._local_count = 0

    def try_acquire(self) -> bool:
        if self._local_count >= self._per_tunnel_limit:
            return False
        if not self._global_sem.acquire(blocking=False):
            return False
        self._local_count += 1
        return True

    def release(self) -> None:
        self._local_count -= 1
        self._global_sem.release()
