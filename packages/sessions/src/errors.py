from collections import Counter
from enum import Enum

from pydantic import BaseModel, Field

# Сколько последних ошибок генерации хранится по каждому маркетплейсу — проценты считаются от них.
SESSION_ERRORS_KEEP = 10


class SessionErrorKind(str, Enum):
    ANTIBOT_INIT = 'antibot_init'
    VALIDATION = 'validation'
    PROXY_UNAVAILABLE = 'proxy_unavailable'
    OTHER = 'other'


SESSION_ERROR_LABELS: dict[SessionErrorKind, str] = {
    SessionErrorKind.ANTIBOT_INIT: 'Антибот при инициализации',
    SessionErrorKind.VALIDATION: 'Ошибка валидации',
    SessionErrorKind.PROXY_UNAVAILABLE: 'Прокси не доступен',
    SessionErrorKind.OTHER: 'Прочее',
}


class SessionErrorShare(BaseModel):
    kind: SessionErrorKind = Field(description='Тип ошибки генерации сессии')
    label: str = Field(description='Название типа ошибки')
    count: int = Field(description='Сколько раз встретилась среди последних ошибок')
    percent: int = Field(description='Доля среди последних ошибок, %')


def group_errors(kinds: list[SessionErrorKind]) -> list[SessionErrorShare]:
    """Группирует последние ошибки по типу: самые частые первыми, при равенстве — в порядке
    объявления `SessionErrorKind`. Пустой список ошибок → пустой результат."""
    if not kinds:
        return []
    counts = Counter(kinds)
    order = list(SessionErrorKind)
    shares = [
        SessionErrorShare(
            kind=kind,
            label=SESSION_ERROR_LABELS[kind],
            count=count,
            percent=round(count * 100 / len(kinds)),
        )
        for kind, count in counts.items()
    ]
    return sorted(shares, key=lambda share: (-share.count, order.index(share.kind)))


def format_errors_text(shares: list[SessionErrorShare]) -> str:
    """Многострочный текст «Тип — N %» для уведомления; пусто, если ошибок не было."""
    return '\n'.join(f'{share.label} — {share.percent} %' for share in shares)
