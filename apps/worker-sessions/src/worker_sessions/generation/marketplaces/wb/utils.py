import uuid

from worker_sessions.generation.marketplaces.wb.constants import (
    WB_FALLBACK_SPA_VERSION,
    WB_SCRIPT_URL_PATTERN,
    WB_SPA_VERSION_PATTERN,
)


def generate_device_id() -> str:
    return 'site_' + uuid.uuid4().hex


def extract_wb_spa_version(html_or_script: str) -> str:
    match = WB_SPA_VERSION_PATTERN.search(html_or_script)
    return match.group(1) if match else WB_FALLBACK_SPA_VERSION


def extract_wb_script_url(html: str) -> str | None:
    match = WB_SCRIPT_URL_PATTERN.search(html)
    return match.group(1) if match else None


def is_wb_blocked_response(status: int, content_type: str, body_prefix: str) -> bool:
    if status in {401, 403, 498}:
        return True
    markers = ('wbaas', 'captcha', 'antibot')
    return any(marker in body_prefix for marker in markers)
