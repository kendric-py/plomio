import json
import re
from typing import Any
from urllib.parse import urljoin

from apps.worker_parser.src.marketplaces.ozon.constants import OZON_BASE_URL
from packages.result.src.entities import (
    CharacteristicPayload,
    ProductPagePayload,
    ProductPayload,
    ReviewPayload,
    SellerCategoryPayload,
    SellerProfilePayload,
)


def _extract_product_title(item: dict[str, Any]) -> str | None:
    main_state = item.get('mainState', [])
    for entry in main_state:
        if entry.get('id') == 'name':
            text = entry.get('textDS', {}).get('text')
            if text:
                return text.strip()
    for entry in main_state:
        text = entry.get('textDS', {}).get('text')
        if text:
            return text.strip()
    return None


def _extract_product_price(item: dict[str, Any]) -> str | None:
    for entry in item.get('mainState', []):
        if entry.get('type') == 'priceV2':
            price_array = entry.get('priceV2', {}).get('price', [])
            if price_array:
                return str(price_array[0].get('text', ''))
    return None


def _extract_product_discount(item: dict[str, Any]) -> str | None:
    for entry in item.get('mainState', []):
        if entry.get('type') == 'priceV2':
            return entry.get('priceV2', {}).get('discount') or None
    return None


def _extract_product_stock(item: dict[str, Any]) -> str | None:
    for entry in item.get('mainState', []):
        if entry.get('type') == 'textDS' and entry.get('id', '') == '':
            text = entry.get('textDS', {}).get('text', '')
            if 'шт' in text:
                return text
    return None


def extract_ozon_product_list(
    payload: dict[str, Any],
    limit: int | None,
    seen_keys: set[str],
) -> list[ProductPayload]:
    result: list[ProductPayload] = []
    for state_raw in payload.get('widgetStates', {}).values():
        if not isinstance(state_raw, str) or '"items"' not in state_raw:
            continue
        try:
            state_object = json.loads(state_raw)
        except json.JSONDecodeError:
            continue
        for item in state_object.get('items') or []:
            if not isinstance(item, dict):
                continue
            link = item.get('action', {}).get('link')
            title = _extract_product_title(item)
            if not link or not title:
                continue
            product_id = item.get('id')
            key = str(product_id or link)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            result.append(
                ProductPayload(
                    external_id=str(product_id) if product_id is not None else None,
                    title=title,
                    price_text=_extract_product_price(item),
                    discount=_extract_product_discount(item),
                    stock=_extract_product_stock(item),
                    product_url=urljoin(OZON_BASE_URL, link),
                ),
            )
            if limit is not None and len(result) >= limit:
                return result
    return result


def _parse_rub_text(text: str) -> int | None:
    clean = re.sub(r'[₽\s\xa0]', '', text or '').replace(',', '.')
    try:
        return int(float(clean) * 100)
    except (ValueError, TypeError):
        return None


def _find_widget(widget_states: dict[str, Any], prefix: str) -> dict[str, Any] | None:
    for key, raw in widget_states.items():
        if key.split('-')[0] == prefix and isinstance(raw, str):
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                pass
    return None


def _extract_description(widget: dict[str, Any]) -> str:
    parts: list[str] = []
    annotation = (widget.get('richAnnotationJson') or {}).get('content') or []
    for section in annotation:
        for block in section.get('blocks') or []:
            for key in ('title', 'text'):
                node = block.get(key) or {}
                for chunk in node.get('content') or []:
                    if isinstance(chunk, str) and chunk.strip():
                        parts.append(chunk.strip())
    for item in widget.get('characteristics') or []:
        title = item.get('title', '')
        content = item.get('content', '')
        if title or content:
            parts.append(f'{title}: {content}'.strip(': '))
    return '\n'.join(parts)


def _extract_characteristics(widget: dict[str, Any]) -> list[CharacteristicPayload]:
    result: list[CharacteristicPayload] = []
    for group in widget.get('characteristics') or []:
        for item in group.get('short') or []:
            name = item.get('name', '')
            values = [
                value.get('text', '') for value in item.get('values') or [] if value.get('text')
            ]
            if name and values:
                result.append(CharacteristicPayload(name=name, value=', '.join(values)))
    return result


def _find_brand(characteristics: list[CharacteristicPayload]) -> str:
    for characteristic in characteristics:
        if characteristic.name.lower() in ('бренд', 'brand', 'торговая марка', 'марка'):
            return characteristic.value
    return ''


def extract_ozon_product_page(
    page1_payload: dict[str, Any],
    page2_payload: dict[str, Any],
    product_url: str,
    external_id: str,
) -> ProductPagePayload:
    widget_states_1 = page1_payload.get('widgetStates', {})
    widget_states_2 = page2_payload.get('widgetStates', {})

    heading = _find_widget(widget_states_1, 'webProductHeading') or {}
    title = heading.get('title', '')
    if not title:
        seo = page1_payload.get('seo', {})
        for meta in seo.get('meta') or []:
            if meta.get('property') == 'og:title':
                title = meta.get('content', '')
                break

    price_widget = _find_widget(widget_states_1, 'webPrice') or {}
    discounted_price_kopecks = _parse_rub_text(price_widget.get('cardPrice', ''))
    price_kopecks = _parse_rub_text(price_widget.get('price', ''))
    original_price_kopecks = _parse_rub_text(price_widget.get('originalPrice', ''))
    # `webPrice.isAvailable` is only ever present (and true) when the item IS in stock — when it's
    # out of stock the key is missing entirely (not `false`), so `.get('isAvailable', True)` alone
    # would default to "in stock" and miss it. A dedicated `webOutOfStock` widget (offering the item
    # from another seller) is what actually appears on out-of-stock pages — verified live via
    # https://www.ozon.ru/product/lf-bros-n3-avtonomnyy-perenosnoy-vozdushnyy-otopitel-12-220v-dizelnyy-1980965427/
    in_stock: bool = (
        _find_widget(widget_states_1, 'webOutOfStock') is None
        and price_widget.get('isAvailable', True) is not False
    )

    score_widget = _find_widget(widget_states_1, 'webReviewProductScore') or {}
    rating: float | None = score_widget.get('totalScore') or None
    review_count: int | None = score_widget.get('reviewsCount') or None

    gallery = _find_widget(widget_states_1, 'webGallery') or {}
    photo_urls = [image['src'] for image in (gallery.get('images') or []) if image.get('src')]

    seller_widget = _find_widget(widget_states_1, 'webCurrentSeller') or {}
    seller_name = (
        (seller_widget.get('sellerCell') or {})
        .get('centerBlock', {})
        .get('title', {})
        .get('text', '')
    )

    sku_widget = _find_widget(widget_states_1, 'webDetailSKU') or {}
    vendor_code = sku_widget.get('copyText', '') or external_id

    breadcrumbs_widget = _find_widget(widget_states_1, 'breadCrumbs') or {}
    crumbs = breadcrumbs_widget.get('breadcrumbs') or []
    category_root = crumbs[0]['text'] if crumbs else ''
    category = crumbs[-2]['text'] if len(crumbs) >= 2 else (crumbs[-1]['text'] if crumbs else '')

    description = ''
    for key, raw in widget_states_2.items():
        if 'webDescription' in key and isinstance(raw, str):
            try:
                widget = json.loads(raw)
                text = _extract_description(widget)
                if len(text) > len(description):
                    description = text
            except json.JSONDecodeError:
                pass

    characteristics: list[CharacteristicPayload] = []
    characteristics_widget = _find_widget(widget_states_2, 'webCharacteristics') or {}
    if characteristics_widget:
        characteristics = _extract_characteristics(characteristics_widget)

    brand = _find_brand(characteristics)

    return ProductPagePayload(
        external_id=external_id,
        product_url=product_url,
        title=title,
        brand=brand,
        vendor_code=vendor_code,
        category=category,
        category_root=category_root,
        seller_name=seller_name,
        discounted_price_kopecks=discounted_price_kopecks,
        price_kopecks=price_kopecks,
        original_price_kopecks=original_price_kopecks,
        rating=rating,
        review_count=review_count,
        in_stock=in_stock,
        description=description,
        characteristics=characteristics,
        photo_urls=photo_urls,
    )


def extract_ozon_review_list(
    payload: dict[str, Any],
    seen_uuids: set[str],
) -> tuple[list[ReviewPayload], int]:
    reviews: list[ReviewPayload] = []
    total = 0
    for key, raw in payload.get('widgetStates', {}).items():
        if 'webListReviews' not in key or not isinstance(raw, str):
            continue
        try:
            widget = json.loads(raw)
        except json.JSONDecodeError:
            continue
        paging = widget.get('paging', {})
        total = paging.get('commonTotal') or paging.get('total') or total
        for review_item in widget.get('reviews') or []:
            uuid_value = review_item.get('uuid', '')
            if not uuid_value or uuid_value in seen_uuids:
                continue
            seen_uuids.add(uuid_value)
            content = review_item.get('content', {})
            reviews.append(
                ReviewPayload(
                    external_uuid=uuid_value,
                    author_name=review_item.get('author', {}).get('firstName', ''),
                    published_at=review_item.get('publishedAt', 0),
                    score=content.get('score', 0),
                    comment_text=content.get('comment', ''),
                    positive_text=content.get('positive', ''),
                    negative_text=content.get('negative', ''),
                    photo_urls=[
                        photo.get('url', '')
                        for photo in (content.get('photos') or [])
                        if photo.get('url')
                    ],
                ),
            )
    return reviews, total


def _parse_widget_states(payload: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in payload.get('widgetStates', {}).items():
        if isinstance(value, str):
            try:
                result[key] = json.loads(value)
            except json.JSONDecodeError:
                result[key] = value
        else:
            result[key] = value
    return result


def _find_prefixed_widget(widget_states: dict[str, Any], prefix: str) -> dict[str, Any] | None:
    for key, value in widget_states.items():
        if key.startswith(prefix + '-'):
            return value if isinstance(value, dict) else None
    return None


def _find_all_prefixed_widgets(widget_states: dict[str, Any], prefix: str) -> list[dict[str, Any]]:
    return [
        value for key, value in widget_states.items()
        if key.startswith(prefix + '-') and isinstance(value, dict)
    ]


def _extract_seller_id(transparency: dict[str, Any]) -> int | None:
    action_link: str = transparency.get('action', {}).get('link', '')
    match = re.search(r'seller_id=(\d+)', action_link)
    if match:
        return int(match.group(1))
    for button in transparency.get('buttons', []):
        for link in [
            button.get('button', {}).get('common', {}).get('action', {}).get('link', ''),
            button.get('favoriteButton', {})
            .get('favoriteButton', {})
            .get('button', {})
            .get('common', {})
            .get('action', {})
            .get('link', ''),
        ]:
            match = re.search(r'seller_id=(\d+)', str(link))
            if match:
                return int(match.group(1))
    return None


def extract_ozon_seller_id_from_widget_states(raw_widget_states: dict[str, Any]) -> int | None:
    widget_states = _parse_widget_states({'widgetStates': raw_widget_states})
    transparency = _find_prefixed_widget(widget_states, 'sellerTransparency') or {}
    return _extract_seller_id(transparency)


def _parse_count_text(text: str) -> int | None:
    text = text.strip()
    parts = text.split()
    if not parts:
        return None
    num_str = parts[0].replace(',', '.').replace(' ', '').replace('\xa0', '')
    multiplier = 1
    if len(parts) >= 2 and parts[1].upper() in ('K', 'К'):
        multiplier = 1000
    elif len(parts) >= 2 and parts[1].upper() in ('M', 'М', 'МЛН'):
        multiplier = 1_000_000
    try:
        return int(float(num_str) * multiplier)
    except (ValueError, TypeError):
        return None


def _extract_badge_text(badges: list[dict], icon_name: str) -> str | None:
    for badge in badges:
        if badge.get('leftIcon') == icon_name:
            return badge.get('text')
    return None


def _badge_exists(badges: list[dict], icon_name: str) -> bool:
    return any(badge.get('leftIcon') == icon_name for badge in badges)


def _extract_legal_info(textblocks: list[dict]) -> tuple[str | None, str | None]:
    for textblock in textblocks:
        for atom in textblock.get('body', []):
            text: str = atom.get('textAtom', {}).get('text', '')
            if '<br>' in text:
                parts = [part.strip() for part in text.split('<br>')]
                legal_name = parts[0] if len(parts) > 0 else None
                inn_ogrn = parts[2] if len(parts) > 2 else None
                return legal_name, inn_ogrn
    return None, None


def _extract_stats_cell(cells: list[dict], title_text: str) -> str | None:
    for cell in cells:
        ds_cell = cell.get('dsCell', {})
        center_title: str = ds_cell.get('centerBlock', {}).get('title', {}).get('text', '')
        if title_text.lower() in center_title.lower():
            return ds_cell.get('rightBlock', {}).get('badge', {}).get('text', '') or None
    return None


def _extract_categories(cell_lists: list[dict]) -> list[SellerCategoryPayload]:
    categories: list[SellerCategoryPayload] = []
    for cell_list in cell_lists:
        if cell_list.get('backgroundColor') != 'bgSecondary':
            continue
        for cell in cell_list.get('cells', []):
            ds_cell = cell.get('dsCell', {})
            name: str = ds_cell.get('centerBlock', {}).get('title', {}).get('text', '')
            action_link: str = ds_cell.get('common', {}).get('action', {}).get('link', '')
            match = re.search(r'-(\d+)/?$', action_link)
            category_id = int(match.group(1)) if match else 0
            if name:
                categories.append(SellerCategoryPayload(category_id=category_id, name=name))
    return categories


def extract_ozon_seller_profile(
    raw_main_widget_states: dict[str, Any],
    raw_modal_widget_states: dict[str, Any],
    seller_url: str,
) -> SellerProfilePayload:
    main_widget_states = _parse_widget_states({'widgetStates': raw_main_widget_states})
    modal_widget_states = _parse_widget_states({'widgetStates': raw_modal_widget_states})
    transparency = _find_prefixed_widget(main_widget_states, 'sellerTransparency') or {}
    badges: list[dict] = transparency.get('badges', [])
    name: str | None = transparency.get('title', {}).get('text')
    seller_id = _extract_seller_id(transparency)
    is_premium = _badge_exists(badges, 'ic_m_multicolor_premium_plus')
    rating_text = _extract_badge_text(badges, 'ic_m_star_filled')
    rating = rating_text.replace(',', '.') if rating_text else None
    reviews_text = _extract_badge_text(badges, 'ic_m_speech_bubble_filled')
    feedbacks_count = _parse_count_text(reviews_text) if reviews_text else None
    orders_text = _extract_badge_text(badges, 'ic_m_box_filled')
    sale_item_quantity = _parse_count_text(orders_text) if orders_text else None

    textblocks = _find_all_prefixed_widgets(modal_widget_states, 'textBlock')
    legal_name, inn_ogrn = _extract_legal_info(textblocks)

    cell_lists = _find_all_prefixed_widgets(modal_widget_states, 'cellList')
    stats_cells: list[dict] = []
    for cell_list in cell_lists:
        if cell_list.get('backgroundColor') == 'bgPrimary':
            stats_cells = cell_list.get('cells', [])
            break

    modal_reviews_text = _extract_stats_cell(stats_cells, 'Количество отзывов')
    if modal_reviews_text:
        feedbacks_count = _parse_count_text(modal_reviews_text)
    modal_orders_text = _extract_stats_cell(stats_cells, 'Заказов')
    if modal_orders_text:
        sale_item_quantity = _parse_count_text(modal_orders_text)

    categories = _extract_categories(cell_lists)

    return SellerProfilePayload(
        supplier_id=seller_id or 0,
        name=name,
        full_name=legal_name,
        inn=inn_ogrn,
        rating=rating,
        feedbacks_count=feedbacks_count,
        sale_item_quantity=sale_item_quantity,
        is_premium=is_premium or None,
        categories=categories,
        seller_url=seller_url,
    )
