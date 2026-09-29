from typing import Any

from pydantic import BaseModel, Field

from core.enums import Marketplace
from packages.direct.src.enums import DirectRequestType, DirectStatus


class DirectRequest(BaseModel):
    request_id: str = Field(..., description='Идентификатор запроса; ключ списка ответа')
    request_type: DirectRequestType = Field(...)
    marketplace: Marketplace = Field(...)
    input_value: str = Field(..., description='Артикул/ссылка товара или текст поискового запроса')
    page_cursor: dict[str, Any] | None = Field(
        default=None,
        description='Курсор маркетплейса из проверенного page_key; None — 1-я страница',
    )
    created_at: float = Field(..., description='Unix-секунды постановки в очередь')
    # Unix-секунды, а не ISO8601, как остальные даты проекта: воркер сравнивает срок с
    # `time.time()` на каждом запросе, и это осознанное исключение из правила про даты.
    deadline_at: float = Field(..., description='Unix-секунды, после которых ответ не нужен')


class DirectReply(BaseModel):
    request_id: str = Field(...)
    status: DirectStatus = Field(...)
    payload: dict[str, Any] | None = Field(default=None)
    next_cursor: dict[str, Any] | None = Field(default=None)
    # Только для логов: клиенту не отдаётся никогда (см. AGENTS.md, "Ошибки клиенту").
    error: str | None = Field(default=None)
