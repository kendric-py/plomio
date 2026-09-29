from dataclasses import dataclass

from pydantic import BaseModel

from apps.worker_parser.src.entities import (
    OzonPaginationCursor,
    OzonReviewCursor,
    WbReviewCursor,
    WildberriesPaginationCursor,
)
from apps.worker_parser.src.fetch_context import PageFetcher
from apps.worker_parser.src.marketplaces.ozon import fetchers as ozon_fetchers
from apps.worker_parser.src.marketplaces.ozon.utils import create_ozon_http_session
from apps.worker_parser.src.marketplaces.wb import fetchers as wb_fetchers
from apps.worker_parser.src.marketplaces.wb.utils import create_wb_http_session
from core.enums import Marketplace
from packages.task.src.enums import ParseType

# Публичный реестр: единственное место, где (маркетплейс, тип) сопоставляется с реализацией.
# Раньше словари жили приватными в runner.py — новым модулям пришлось бы импортировать
# `_`-имена и получать цикл импортов.


@dataclass(frozen=True)
class PageOperation:
    fetch_page: PageFetcher
    # Модель курсора для восстановления из `TaskItem.cursor`; None — курсора нет (карточка).
    cursor_model: type[BaseModel] | None


OPERATIONS: dict[tuple[Marketplace, ParseType], PageOperation] = {
    (Marketplace.OZON, ParseType.PRODUCT_PAGE): PageOperation(
        ozon_fetchers.fetch_ozon_product_page, None,
    ),
    (Marketplace.OZON, ParseType.SEARCH_QUERY): PageOperation(
        ozon_fetchers.fetch_ozon_search_page, OzonPaginationCursor,
    ),
    (Marketplace.OZON, ParseType.CATEGORY): PageOperation(
        ozon_fetchers.fetch_ozon_category_page, OzonPaginationCursor,
    ),
    (Marketplace.OZON, ParseType.SELLER): PageOperation(
        ozon_fetchers.fetch_ozon_seller_page, OzonPaginationCursor,
    ),
    (Marketplace.OZON, ParseType.REVIEWS): PageOperation(
        ozon_fetchers.fetch_ozon_review_page, OzonReviewCursor,
    ),
    (Marketplace.WILDBERRIES, ParseType.PRODUCT_PAGE): PageOperation(
        wb_fetchers.fetch_wb_product_page, None,
    ),
    (Marketplace.WILDBERRIES, ParseType.SEARCH_QUERY): PageOperation(
        wb_fetchers.fetch_wb_search_page, WildberriesPaginationCursor,
    ),
    (Marketplace.WILDBERRIES, ParseType.CATEGORY): PageOperation(
        wb_fetchers.fetch_wb_category_page, WildberriesPaginationCursor,
    ),
    (Marketplace.WILDBERRIES, ParseType.SELLER): PageOperation(
        wb_fetchers.fetch_wb_seller_page, WildberriesPaginationCursor,
    ),
    (Marketplace.WILDBERRIES, ParseType.REVIEWS): PageOperation(
        wb_fetchers.fetch_wb_review_page, WbReviewCursor,
    ),
}

HTTP_SESSION_FACTORY_BY_MARKETPLACE = {
    Marketplace.OZON: create_ozon_http_session,
    Marketplace.WILDBERRIES: create_wb_http_session,
}

SELLER_PROFILE_FETCHERS = {
    Marketplace.OZON: ozon_fetchers.fetch_ozon_seller_profile,
    Marketplace.WILDBERRIES: wb_fetchers.fetch_wb_seller_profile,
}
