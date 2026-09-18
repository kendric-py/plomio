from enum import Enum


class Marketplace(str, Enum):
    """Values match `packages/task/src/enums.py`-adjacent marketplace identifiers used across
    the monorepo — the wire contract for SessionMessage.marketplace."""

    OZON = 'ozon'
    WILDBERRIES = 'wildberries'


class WorkerSessionsStatus(str, Enum):
    """Reported in the process-level liveness heartbeat (see liveness.py). Minimum set
    proposed by analogy with worker-parser's three required states (ready/working/waiting-for-
    proxy) — extend if a real deployment surfaces a state that doesn't fit any of these."""

    READY = 'READY'
    GENERATING = 'GENERATING'
    WAITING_FOR_PROXY = 'WAITING_FOR_PROXY'
