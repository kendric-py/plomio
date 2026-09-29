from dataclasses import dataclass, field
from typing import Any

from apps.worker_parser.src.entities import SessionMessage
from core.enums import Marketplace


@dataclass
class FakeResponse:
    payload: Any

    def json(self) -> Any:
        return self.payload


@dataclass
class FakeContext:
    """Подмена `FetchContext`: отдаёт заготовленные ответы по очереди и запоминает запросы."""

    responses: list[Any]
    session_message: SessionMessage
    seen_keys: set[str] = field(default_factory=set)
    limit: int | None = None
    review_page_size: int | None = None
    walk_all_review_sorts: bool = False
    confirm_empty_page: bool = False
    http_session: Any = None
    requests: list[tuple[str, dict | None]] = field(default_factory=list)

    async def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        self.requests.append((url, kwargs.get('params')))
        return FakeResponse(self.responses.pop(0))


def make_session_message() -> SessionMessage:
    """Сессия с полями `extra`, которые читают заголовки обоих маркетплейсов."""
    return SessionMessage(
        marketplace=Marketplace.OZON,
        cookies={},
        user_agent='ua',
        sec_ch_ua='',
        sec_ch_ua_platform='',
        extra={
            'xcid': 'x', 'ab_group': 'y', 'app_version': 'v', 'device_id': 'd',
            'spa_version': 's',
        },
    )
