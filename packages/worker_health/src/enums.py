from enum import Enum


class WorkerType(str, Enum):
    PARSER = 'PARSER'
    SESSIONS = 'SESSIONS'


class WorkerHeartbeatEventType(str, Enum):
    MISSED = 'MISSED'
    RECOVERED = 'RECOVERED'
