import logging
import time
from collections import Counter

from worker_sessions.generation.socks5_tunnel.errors import EXPECTED_TEARDOWN_NOISE

logger = logging.getLogger(__name__)


class ErrorLogThrottle:
    """Aggregates repeated connection errors within a rolling window and emits one
    summary per window instead of one line per connection — a single degraded upstream
    proxy, or a browser cancelling sub-resources on navigation, can otherwise flood the
    logs with one line per connection. Errors that are normal teardown noise
    (EXPECTED_TEARDOWN_NOISE) are logged at DEBUG/INFO; anything else — auth failures,
    REP rejections, protocol errors — stays at ERROR/WARNING so it's actually visible."""

    def __init__(self, window_s: float, tunnel_label: str) -> None:
        self._window_s = window_s
        self._label = tunnel_label
        self._window_start = time.monotonic()
        self._counts: Counter[str] = Counter()

    def record(self, error_type: str, detail: str) -> None:
        now = time.monotonic()
        if now - self._window_start >= self._window_s:
            self._flush()
            self._window_start = now
        first_of_kind = self._counts[error_type] == 0
        self._counts[error_type] += 1
        if first_of_kind:
            level = logging.DEBUG if error_type in EXPECTED_TEARDOWN_NOISE else logging.ERROR
            logger.log(
                level,
                '[tunnel] event=connection_error tunnel=%s error_type=%s detail=%s',
                self._label, error_type, detail,
            )

    def _flush(self) -> None:
        total = sum(self._counts.values())
        if total > len(self._counts):
            noisy = {
                key: value for key, value in self._counts.items() if key in EXPECTED_TEARDOWN_NOISE
            }
            notable = {
                key: value
                for key, value in self._counts.items()
                if key not in EXPECTED_TEARDOWN_NOISE
            }
            if notable:
                summary = ' '.join(f'{key}={value}' for key, value in sorted(notable.items()))
                logger.warning(
                    '[tunnel] event=connection_error_summary tunnel=%s window_s=%.0f %s',
                    self._label, self._window_s, summary,
                )
            if noisy:
                summary = ' '.join(f'{key}={value}' for key, value in sorted(noisy.items()))
                logger.info(
                    '[tunnel] event=connection_teardown_summary tunnel=%s window_s=%.0f %s',
                    self._label, self._window_s, summary,
                )
        self._counts.clear()

    def close(self) -> None:
        self._flush()


class UpstreamCircuitBreaker:
    """Tracks upstream CONNECT failures in a rolling window; once the failure count
    crosses the threshold, is_open() returns True for cooldown_s so the tunnel can
    fast-fail new CONNECTs without hammering an upstream that's clearly unhealthy."""

    def __init__(
        self, failure_threshold: int, window_s: float, cooldown_s: float, tunnel_label: str,
    ) -> None:
        self._failure_threshold = failure_threshold
        self._window_s = window_s
        self._cooldown_s = cooldown_s
        self._label = tunnel_label
        self._failure_times: list[float] = []
        self._open_until: float | None = None

    def is_open(self) -> bool:
        if self._open_until is None:
            return False
        if time.monotonic() < self._open_until:
            return True
        self._open_until = None
        self._failure_times.clear()
        logger.warning('[tunnel] event=circuit_closed tunnel=%s', self._label)
        return False

    def record_success(self) -> None:
        self._failure_times.clear()

    def record_failure(self) -> None:
        now = time.monotonic()
        cutoff = now - self._window_s
        self._failure_times = [
            timestamp for timestamp in self._failure_times if timestamp >= cutoff
        ]
        self._failure_times.append(now)
        if len(self._failure_times) >= self._failure_threshold and self._open_until is None:
            self._open_until = now + self._cooldown_s
            logger.warning(
                '[tunnel] event=circuit_open tunnel=%s failures=%d window_s=%.0f cooldown_s=%.0f',
                self._label, len(self._failure_times), self._window_s, self._cooldown_s,
            )
