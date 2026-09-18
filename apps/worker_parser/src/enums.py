from enum import Enum


class WorkerParserStatus(str, Enum):
    """Reported in the process-level liveness heartbeat (see liveness.py). Minimum set required
    by the project brief: ready to claim work, actively working a claimed task, and blocked
    waiting on a Redis session from worker_sessions. Extend if a real deployment surfaces a
    state that doesn't fit any of these (e.g. a graceful-shutdown state)."""

    READY = 'READY'
    WORKING = 'WORKING'
    WAITING_FOR_SESSION = 'WAITING_FOR_SESSION'
