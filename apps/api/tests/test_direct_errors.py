import pytest

from apps.api.src.routers.direct import errors
from packages.direct.src.enums import DirectRequestType, DirectStatus

FIXED_MESSAGES = {
    errors.INVALID_ARTICLE_DETAIL, errors.INVALID_SEARCH_QUERY_DETAIL,
    errors.INVALID_CATEGORY_DETAIL, errors.INVALID_SELLER_DETAIL, errors.INVALID_PAGE_KEY_DETAIL,
    errors.PRODUCT_NOT_FOUND_DETAIL, errors.CATEGORY_NOT_FOUND_DETAIL,
    errors.SELLER_NOT_FOUND_DETAIL, errors.UNAVAILABLE_DETAIL, errors.TIMEOUT_DETAIL,
    errors.INSUFFICIENT_CREDITS_DETAIL,
}


def test_insufficient_credits_is_402():
    error = errors.insufficient_credits_error()
    assert (error.status_code, error.detail) == (402, errors.INSUFFICIENT_CREDITS_DETAIL)


@pytest.mark.parametrize('request_type, detail', [
    (DirectRequestType.PRODUCT_PAGE, errors.INVALID_ARTICLE_DETAIL),
    (DirectRequestType.REVIEWS, errors.INVALID_ARTICLE_DETAIL),
    (DirectRequestType.SEARCH, errors.INVALID_SEARCH_QUERY_DETAIL),
    (DirectRequestType.CATEGORY, errors.INVALID_CATEGORY_DETAIL),
    (DirectRequestType.SELLER, errors.INVALID_SELLER_DETAIL),
])
def test_invalid_input_message_per_type(request_type, detail):
    error = errors.error_for_status(DirectStatus.INVALID_INPUT, request_type, False)
    assert (error.status_code, error.detail) == (422, detail)


@pytest.mark.parametrize('request_type', list(DirectRequestType))
def test_invalid_input_with_page_key_is_a_page_key_error(request_type):
    error = errors.error_for_status(DirectStatus.INVALID_INPUT, request_type, True)
    assert error.detail == errors.INVALID_PAGE_KEY_DETAIL


@pytest.mark.parametrize('request_type, detail', [
    (DirectRequestType.PRODUCT_PAGE, errors.PRODUCT_NOT_FOUND_DETAIL),
    (DirectRequestType.CATEGORY, errors.CATEGORY_NOT_FOUND_DETAIL),
    (DirectRequestType.SELLER, errors.SELLER_NOT_FOUND_DETAIL),
])
def test_not_found_is_404_with_fixed_message(request_type, detail):
    error = errors.error_for_status(DirectStatus.NOT_FOUND, request_type, False)
    assert (error.status_code, error.detail) == (404, detail)


def test_search_not_found_and_infrastructure_failures_are_503():
    for reply_status, request_type in (
        (DirectStatus.NOT_FOUND, DirectRequestType.SEARCH),
        (DirectStatus.UNAVAILABLE, DirectRequestType.SELLER),
        (DirectStatus.ERROR, DirectRequestType.CATEGORY),
    ):
        error = errors.error_for_status(reply_status, request_type, False)
        assert (error.status_code, error.detail) == (503, errors.UNAVAILABLE_DETAIL)


@pytest.mark.parametrize('request_type', list(DirectRequestType))
@pytest.mark.parametrize('reply_status', [s for s in DirectStatus if s != DirectStatus.OK])
def test_client_only_ever_sees_fixed_messages(request_type, reply_status):
    for page_key_used in (False, True):
        error = errors.error_for_status(reply_status, request_type, page_key_used)
        assert error.detail in FIXED_MESSAGES
