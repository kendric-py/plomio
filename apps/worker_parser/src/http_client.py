import asyncio
import logging
import random
import time
from typing import Any, Callable
from urllib.parse import urlparse

from curl_cffi.requests import AsyncSession
from curl_cffi.requests.errors import RequestsError

from apps.worker_parser.src.config import config
from apps.worker_parser.src.exceptions import BlockedError, RequestError

logger = logging.getLogger(__name__)


async def execute_request(
    session: AsyncSession,
    method: str,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    extra_headers: dict[str, str] | None = None,
    timeout: float = config.HTTP.TIMEOUT_SECONDS,
    retries: int = config.HTTP.RETRIES,
    base_delay: float = config.HTTP.BASE_DELAY_SECONDS,
    retryable_status_codes: frozenset[int] = frozenset({408, 425, 429, 500, 502, 503, 504}),
    is_blocked: Callable[[int, str, str], bool] | None = None,
) -> Any:
    path = urlparse(url).path or url
    request_start = time.monotonic()

    last_network_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            response = await session.request(
                method, url, params=params, headers=extra_headers,
                timeout=timeout, allow_redirects=True,
            )
            content_type = response.headers.get('content-type', '')
            raw_body_prefix = response.text[:8000]
            body_prefix = raw_body_prefix.lower()
            if is_blocked and is_blocked(response.status_code, content_type, body_prefix):
                raise BlockedError(
                    f'blocked HTTP {response.status_code}',
                    status_code=response.status_code,
                    url=url,
                    content_type=content_type,
                    response_body=raw_body_prefix,
                )
            if response.status_code in retryable_status_codes:
                if attempt == retries:
                    raise RequestError(
                        f'HTTP {response.status_code} after retries',
                        status_code=response.status_code,
                        url=url,
                    )
                await asyncio.sleep(base_delay * (2**attempt) + random.uniform(0, 0.5))
                continue
            if response.status_code >= 400:
                raise RequestError(
                    f'HTTP {response.status_code}: {response.text[:300]}',
                    status_code=response.status_code,
                    url=url,
                )
            logger.debug(
                '[http_request] path=%s elapsed=%.2fs attempts=%d status=%d',
                path, time.monotonic() - request_start, attempt + 1, response.status_code,
            )
            return response
        except BlockedError:
            raise
        except RequestsError as network_error:
            last_network_error = network_error
            if attempt == retries:
                break
            await asyncio.sleep(base_delay * (2**attempt) + random.uniform(0, 0.5))
    raise RequestError(f'network error: {last_network_error}', url=url)
