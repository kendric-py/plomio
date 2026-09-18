from datetime import datetime
from typing import Any

from apps.worker_parser.src.marketplaces.wb.constants import WB_BASE_URL
from apps.worker_parser.src.marketplaces.wb.utils import get_raw_wb_products, get_wb_basket_host
from packages.result.src.entities import (
    CharacteristicPayload,
    ProductPagePayload,
    ProductPayload,
    ReviewPayload,
)


def _format_wb_price(kopecks: int | None) -> str | None:
    if not kopecks:
        return None
    rubles = kopecks // 100
    return f'{rubles} ₽'


def _format_wb_discount(basic: int | None, product: int | None) -> str | None:
    if not basic or not product or basic <= product:
        return None
    percent = round((basic - product) / basic * 100)
    return f'-{percent}%'


def extract_wb_product_list(
    payload: dict[str, Any],
    limit: int | None,
    seen_ids: set[int],
) -> list[ProductPayload]:
    result: list[ProductPayload] = []
    for item in get_raw_wb_products(payload):
        if not isinstance(item, dict):
            continue
        nm_id: int | None = item.get('id')
        if nm_id is None or nm_id in seen_ids:
            continue
        seen_ids.add(nm_id)
        name: str = item.get('name') or ''
        if not name:
            continue
        sizes = item.get('sizes') or []
        price_object = (sizes[0].get('price') or {}) if sizes else {}
        price_kopecks: int | None = price_object.get('product')
        basic_kopecks: int | None = price_object.get('basic')
        total_quantity: int | None = item.get('totalQuantity')
        result.append(
            ProductPayload(
                external_id=str(nm_id),
                title=name,
                price_text=_format_wb_price(price_kopecks),
                discount=_format_wb_discount(basic_kopecks, price_kopecks),
                stock=str(total_quantity) if total_quantity is not None else None,
                product_url=f'{WB_BASE_URL}/catalog/{nm_id}/detail.aspx',
            ),
        )
        if limit is not None and len(result) >= limit:
            break
    return result


def _wb_photo_urls(nm_id: int, photo_count: int) -> list[str]:
    vol = nm_id // 100000
    part = nm_id // 1000
    host = get_wb_basket_host(nm_id)
    return [
        f'https://{host}/vol{vol}/part{part}/{nm_id}/images/big/{index}.webp'
        for index in range(1, photo_count + 1)
    ]


def _select_wb_size(sizes: list[dict[str, Any]], option_id: int | None) -> dict[str, Any] | None:
    if not sizes:
        return None
    if option_id is not None:
        for size in sizes:
            if size.get('optionId') == option_id:
                return size
    for size in sizes:
        if size.get('price'):
            return size
    return sizes[0]


def extract_wb_product_page(
    card_data: dict[str, Any],
    card_api_product: dict[str, Any],
    nm_id: int,
    size_option_id: int | None,
) -> ProductPagePayload:
    external_id = str(nm_id)
    product_url = f'{WB_BASE_URL}/catalog/{nm_id}/detail.aspx'

    title: str = card_data.get('imt_name') or card_api_product.get('name') or ''
    description: str = card_data.get('description') or ''
    vendor_code: str = card_data.get('vendor_code') or ''

    selling = card_data.get('selling') or {}
    brand = selling.get('brand_name') or card_api_product.get('brand') or ''
    seller_name = card_api_product.get('supplier') or ''

    category = card_data.get('subj_name') or ''
    category_root = card_data.get('subj_root_name') or ''

    sizes = card_api_product.get('sizes') or []
    selected_size = _select_wb_size(sizes, size_option_id)
    price_data = selected_size.get('price') if selected_size else {}
    price_kopecks: int | None = price_data.get('product') if price_data else None
    original_price_kopecks: int | None = price_data.get('basic') if price_data else None
    total_quantity = card_api_product.get('totalQuantity') or 0
    in_stock = total_quantity > 0

    rating_raw = card_api_product.get('rating')
    rating: float | None = float(rating_raw) if rating_raw else None
    review_count: int | None = card_api_product.get('feedbacks') or None

    photo_count: int = (card_data.get('media') or {}).get('photo_count') or card_api_product.get('pics') or 0
    photo_urls = _wb_photo_urls(nm_id, photo_count)

    characteristics: list[CharacteristicPayload] = []
    for option in card_data.get('options') or []:
        name: str = option.get('name') or ''
        value: str = option.get('value') or ''
        if name and value:
            characteristics.append(CharacteristicPayload(name=name, value=value))

    return ProductPagePayload(
        external_id=external_id,
        product_url=product_url,
        title=title,
        brand=brand,
        vendor_code=vendor_code,
        category=category,
        category_root=category_root,
        seller_name=seller_name,
        price_kopecks=price_kopecks,
        original_price_kopecks=original_price_kopecks,
        rating=rating,
        review_count=review_count,
        in_stock=in_stock,
        description=description,
        characteristics=characteristics,
        photo_urls=photo_urls,
    )


def _parse_wb_iso_to_timestamp(date_str: str) -> int:
    try:
        parsed = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        return int(parsed.timestamp())
    except (ValueError, AttributeError):
        return 0


def _wb_photo_url(key: str) -> str | None:
    parts = key.split('/', 1)
    if len(parts) != 2:
        return None
    shard = parts[0].zfill(2)
    photo_uuid = parts[1]
    return f'https://feedback-{shard}.wbbasket.ru/{photo_uuid}/fs.webp'


def extract_wb_review_list(
    payload: dict[str, Any],
    seen_uuids: set[str],
) -> tuple[list[ReviewPayload], int]:
    reviews: list[ReviewPayload] = []
    total: int = payload.get('feedbackCount') or 0

    for feedback in payload.get('feedbacks') or []:
        uuid_value: str = feedback.get('id') or ''
        if not uuid_value or uuid_value in seen_uuids:
            continue
        seen_uuids.add(uuid_value)
        user_details = feedback.get('wbUserDetails') or {}
        photo_urls = [
            url
            for photo in (feedback.get('photos') or [])
            if photo.get('key') and not photo.get('isBlurred')
            for url in [_wb_photo_url(photo['key'])]
            if url
        ]
        reviews.append(
            ReviewPayload(
                external_uuid=uuid_value,
                author_name=user_details.get('name') or '',
                published_at=_parse_wb_iso_to_timestamp(feedback.get('createdDate') or ''),
                score=feedback.get('productValuation') or 0,
                comment_text=feedback.get('text') or '',
                positive_text=feedback.get('pros') or '',
                negative_text=feedback.get('cons') or '',
                photo_urls=photo_urls,
            ),
        )

    return reviews, total
