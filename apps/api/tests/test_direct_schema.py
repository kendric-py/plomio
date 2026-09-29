from apps.api.src.routers.direct.schema import (
    DirectCategoryResponse,
    DirectReviewsResponse,
    DirectSearchResponse,
    DirectSellerResponse,
)

PAGE_RESPONSES = (
    DirectReviewsResponse, DirectSearchResponse, DirectCategoryResponse, DirectSellerResponse,
)


def test_last_page_is_explicit_on_every_paged_response():
    """Конец выдачи одинаков у всех постраничных ответов: `next_page_key` есть и он `null`."""
    for response_model in PAGE_RESPONSES:
        body = response_model(request_id='r', items=[], next_page_key=None).model_dump()
        assert 'next_page_key' in body and body['next_page_key'] is None


def test_next_page_key_is_passed_through():
    for response_model in PAGE_RESPONSES:
        body = response_model(request_id='r', items=[], next_page_key='key').model_dump()
        assert body['next_page_key'] == 'key'
