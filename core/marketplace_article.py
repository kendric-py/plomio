import re
from urllib.parse import urlparse

from core.enums import Marketplace

_OZON_ARTICLE_PATTERN = re.compile(r'-(\d+)/?$')
_WB_ARTICLE_PATTERN = re.compile(r'/catalog/(\d+)/')


def extract_article(marketplace: Marketplace, input_value: str) -> str | None:
    """Best-effort, no-network extraction of a product's article straight from `input_value` (a
    URL or a bare article) — used to de-duplicate automations without doing a full parse. Returns
    `None` when the format isn't recognized; never raises. This is deliberately separate from the
    URL parsing in apps/worker_parser/src/marketplaces/{ozon,wb}/utils.py, which is fetch-oriented
    (expects a well-formed URL, and either raises or silently falls back on bad input) — a
    duplicate check needs a soft "couldn't tell" outcome, not an exception."""

    stripped = input_value.strip()
    if stripped.isdigit():
        return stripped

    if marketplace == Marketplace.OZON:
        match = _OZON_ARTICLE_PATTERN.search(urlparse(stripped).path.rstrip('/'))
        return match.group(1) if match else None

    if marketplace == Marketplace.WILDBERRIES:
        match = _WB_ARTICLE_PATTERN.search(stripped)
        return match.group(1) if match else None

    return None
