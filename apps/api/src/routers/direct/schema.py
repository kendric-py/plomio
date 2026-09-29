from pydantic import BaseModel, Field

from packages.result.src.entities import ProductPagePayload, ProductPayload, ReviewPayload


# --- Ответы ---


class DirectProductResponse(BaseModel):
    """Карточка товара по артикулу."""

    request_id: str = Field(description='Идентификатор запроса (для обращения в поддержку)')
    product: ProductPagePayload = Field(description='Карточка товара')


class DirectPageResponse(BaseModel):
    """Общий контракт постраничных ответов: конец выдачи выражается одним и тем же способом —
    `next_page_key=null` (поле есть в каждом ответе, на последней странице оно `null`)."""

    request_id: str = Field(description='Идентификатор запроса (для обращения в поддержку)')
    next_page_key: str | None = Field(
        description='Ключ следующей страницы (`page_key`); `null` — страниц больше нет',
    )


class DirectReviewsResponse(DirectPageResponse):
    """Страница отзывов о товаре."""

    items: list[ReviewPayload] = Field(
        description='Отзывы страницы (на последней может быть пусто)',
    )


class DirectSearchResponse(DirectPageResponse):
    """Страница выдачи по тексту запроса."""

    items: list[ProductPayload] = Field(
        description='Товары страницы выдачи (на последней может быть пусто)',
    )


class DirectCategoryResponse(DirectPageResponse):
    """Страница товаров категории по ссылке."""

    items: list[ProductPayload] = Field(
        description='Товары страницы категории (на последней может быть пусто)',
    )


class DirectSellerResponse(DirectPageResponse):
    """Страница товаров продавца."""

    items: list[ProductPayload] = Field(
        description='Товары страницы продавца (на последней может быть пусто)',
    )
