import asyncio
from typing import Any

from curl_cffi.requests import AsyncSession

from apps.worker_parser.src.entities import SessionMessage
from apps.worker_parser.src.http_client import execute_request
from apps.worker_parser.src.marketplaces.wb.constants import WB_BASE_URL, WB_MAIN_MENU_URL, WB_RETRYABLE_STATUS_CODES
from apps.worker_parser.src.marketplaces.wb.utils import is_wb_blocked_response

_menu_cache: dict[str, str] | None = None
_menu_cache_lock = asyncio.Lock()


def _collect_wb_search_queries(node: Any, result: dict[str, str]) -> None:
    if isinstance(node, list):
        for item in node:
            _collect_wb_search_queries(item, result)
    elif isinstance(node, dict):
        url = node.get('url')
        search_query = node.get('searchQuery')
        if url and search_query:
            result[url] = search_query
        for key in ('childs', 'nodes', 'data'):
            if key in node:
                _collect_wb_search_queries(node[key], result)


async def load_wb_menu_search_queries(
    http_session: AsyncSession,
    session_message: SessionMessage,
) -> dict[str, str]:
    global _menu_cache
    if _menu_cache is not None:
        return _menu_cache

    async with _menu_cache_lock:
        if _menu_cache is not None:
            return _menu_cache

        response = await execute_request(
            http_session,
            'GET',
            WB_MAIN_MENU_URL,
            extra_headers={
                'accept': '*/*',
                'accept-language': 'ru-RU,ru;q=0.9,en;q=0.8',
                'referer': WB_BASE_URL + '/',
                'sec-fetch-dest': 'empty',
                'sec-fetch-mode': 'cors',
                'sec-fetch-site': 'cross-site',
                'user-agent': session_message.user_agent,
            },
            retryable_status_codes=WB_RETRYABLE_STATUS_CODES,
            is_blocked=is_wb_blocked_response,
        )
        data = response.json()
        result: dict[str, str] = {}
        _collect_wb_search_queries(data, result)
        _menu_cache = result
        return result
