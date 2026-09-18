class ParserError(Exception):
    """Root of all worker_parser exceptions."""


class RequestError(ParserError):
    """Network/HTTP failure — retried in place or with session reinitialization."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        url: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.url = url


class BlockedError(RequestError):
    """Marketplace anti-bot/block, detected by is_*_blocked_response predicates."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        url: str | None = None,
        content_type: str | None = None,
        response_body: str | None = None,
    ) -> None:
        super().__init__(message, status_code=status_code, url=url)
        self.content_type = content_type
        self.response_body = response_body


class SuspiciousThinResultError(BlockedError):
    """Heuristic thin-first-page signal (Wildberries) — same retry behavior as BlockedError."""


class UpstreamDataError(ParserError):
    """Well-formed but empty/unexpected marketplace response — one retry in place."""


class InputResolutionError(ParserError):
    """Input value could not be resolved to a fetch target — never retried."""


class BrowserInitError(ParserError):
    """Could not obtain a usable session from Redis in time — never retried in place."""
