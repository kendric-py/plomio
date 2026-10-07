class WorkerSessionsError(Exception):
    pass


class BrowserInitError(WorkerSessionsError):
    pass


class SessionValidationError(WorkerSessionsError):
    pass


class JsRuntimeError(WorkerSessionsError):
    pass
