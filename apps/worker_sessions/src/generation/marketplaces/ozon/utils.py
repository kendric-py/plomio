from apps.worker_sessions.src.generation.marketplaces.ozon.constants import (
    OZON_APP_VERSION_PATTERN,
    OZON_FALLBACK_APP_VERSION,
)


def extract_ozon_app_version(html: str) -> str:
    regex_match = OZON_APP_VERSION_PATTERN.search(html)
    return regex_match.group(1) if regex_match else OZON_FALLBACK_APP_VERSION


def is_ozon_blocked_response(status: int, content_type: str, body_prefix: str) -> bool:
    if status in {401, 403}:
        return True
    if status == 200 and content_type.startswith('application/json'):
        return False
    markers = ('__rr=1', 'abt-challenge', 'incidentid', 'captcha', '"error":"forbidden"')
    return any(marker in body_prefix for marker in markers)
