from collections import Counter
from enum import Enum

from pydantic import BaseModel, Field

from packages.sessions.src.enums import SessionGenerationOutcome

# Сколько последних генераций (успехов и ошибок) хранится по каждому маркетплейсу — проценты
# считаются от них.
SESSION_GENERATIONS_KEEP = 50


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

SESSION_OUTCOME_LABELS: dict[SessionGenerationOutcome, str] = {
    SessionGenerationOutcome.SUCCESS: 'Успешно',
    **{
        SessionGenerationOutcome(kind.value): label
        for kind, label in SESSION_ERROR_LABELS.items()
    },
}


class SessionGenerationShare(BaseModel):
    kind: SessionGenerationOutcome = Field(description='Итог генерации сессии: успех или тип ошибки')
    label: str = Field(description='Название итога')
    count: int = Field(description='Сколько раз встретился среди последних генераций')
    percent: int = Field(description='Доля среди последних генераций, %')


def outcome_from_error(kind: SessionErrorKind) -> SessionGenerationOutcome:
    return SessionGenerationOutcome(kind.value)


def group_generations(outcomes: list[SessionGenerationOutcome]) -> list[SessionGenerationShare]:
    """Группирует последние генерации по итогу: самые частые первыми, при равенстве — в порядке
    объявления `SessionGenerationOutcome`. Пустой список → пустой результат."""
    if not outcomes:
        return []
    counts = Counter(outcomes)
    order = list(SessionGenerationOutcome)
    shares = [
        SessionGenerationShare(
            kind=outcome,
            label=SESSION_OUTCOME_LABELS[outcome],
            count=count,
            percent=round(count * 100 / len(outcomes)),
        )
        for outcome, count in counts.items()
    ]
    return sorted(shares, key=lambda share: (-share.count, order.index(share.kind)))


def success_percent(outcomes: list[SessionGenerationOutcome]) -> int:
    """Доля успешных генераций среди последних, %; 0, если генераций ещё не было."""
    if not outcomes:
        return 0
    return round(outcomes.count(SessionGenerationOutcome.SUCCESS) * 100 / len(outcomes))


def format_errors_text(shares: list[SessionGenerationShare]) -> str:
    """Многострочный текст «Тип — N %» для уведомления (только ошибки, без успеха); пусто, если
    ошибок не было."""
    return '\n'.join(
        f'{share.label} — {share.percent} %'
        for share in shares
        if share.kind != SessionGenerationOutcome.SUCCESS
    )
