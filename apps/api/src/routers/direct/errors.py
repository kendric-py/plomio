from fastapi import HTTPException, status

from packages.direct.src.enums import DirectRequestType, DirectStatus

# Клиенту не отдаются ошибки маркетплейсов, парсера и инфраструктуры, названия внутренних
# сущностей и устройство потока (сессии, прокси, блокировки) — только фиксированные сообщения из
# этого файла. Разные внутренние причины сбоя сведены к одному ответу 503 намеренно. Новые
# статусы и типы запросов обязаны идти через этот модуль, а не пробрасывать `reply.error`.

INVALID_ARTICLE_DETAIL = 'Invalid article'
INVALID_SEARCH_QUERY_DETAIL = 'Invalid search query'
INVALID_CATEGORY_DETAIL = 'Invalid category url'
INVALID_SELLER_DETAIL = 'Invalid seller'
INVALID_PAGE_KEY_DETAIL = 'Invalid or expired page key'
PRODUCT_NOT_FOUND_DETAIL = 'Product not found'
CATEGORY_NOT_FOUND_DETAIL = 'Category not found'
SELLER_NOT_FOUND_DETAIL = 'Seller not found'
UNAVAILABLE_DETAIL = 'Service temporarily unavailable, please try again later'
TIMEOUT_DETAIL = 'Request timed out, please try again later'
INSUFFICIENT_CREDITS_DETAIL = 'Insufficient credits'


def insufficient_credits_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=INSUFFICIENT_CREDITS_DETAIL,
    )


def invalid_page_key_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=INVALID_PAGE_KEY_DETAIL,
    )


def invalid_search_query_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=INVALID_SEARCH_QUERY_DETAIL,
    )


def invalid_category_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=INVALID_CATEGORY_DETAIL,
    )


def invalid_seller_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=INVALID_SELLER_DETAIL,
    )


def unavailable_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=UNAVAILABLE_DETAIL,
    )


def timeout_error() -> HTTPException:
    return HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=TIMEOUT_DETAIL)


INVALID_INPUT_DETAIL_BY_TYPE = {
    DirectRequestType.PRODUCT_PAGE: INVALID_ARTICLE_DETAIL,
    DirectRequestType.REVIEWS: INVALID_ARTICLE_DETAIL,
    DirectRequestType.SEARCH: INVALID_SEARCH_QUERY_DETAIL,
    DirectRequestType.CATEGORY: INVALID_CATEGORY_DETAIL,
    DirectRequestType.SELLER: INVALID_SELLER_DETAIL,
}

# Поиск намеренно отсутствует: пустая выдача — не «не найдено», для него `not_found` сводится к 503.
NOT_FOUND_DETAIL_BY_TYPE = {
    DirectRequestType.PRODUCT_PAGE: PRODUCT_NOT_FOUND_DETAIL,
    DirectRequestType.REVIEWS: PRODUCT_NOT_FOUND_DETAIL,
    DirectRequestType.CATEGORY: CATEGORY_NOT_FOUND_DETAIL,
    DirectRequestType.SELLER: SELLER_NOT_FOUND_DETAIL,
}


def error_for_status(
    reply_status: DirectStatus,
    request_type: DirectRequestType,
    page_key_used: bool,
) -> HTTPException:
    """Ответ клиенту по статусу неуспешного ответа воркера."""
    if reply_status == DirectStatus.INVALID_INPUT:
        if page_key_used:
            return invalid_page_key_error()
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=INVALID_INPUT_DETAIL_BY_TYPE[request_type],
        )
    if reply_status == DirectStatus.NOT_FOUND and request_type in NOT_FOUND_DETAIL_BY_TYPE:
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=NOT_FOUND_DETAIL_BY_TYPE[request_type],
        )
    return unavailable_error()
