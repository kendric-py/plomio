from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from typing import Any, Callable, Iterable

import xlsxwriter

from packages.result.src.entities import ResultItemEntity


@dataclass(frozen=True)
class Column:
    header: str
    key: str
    width: int
    color: str  # фон заголовка
    tint: str  # светлый фон ячеек колонки
    format: Callable[[Any], Any] | None = None


_BLUE = ('#1F4E79', '#DDEBF7')
_GREEN = ('#2E7D32', '#E2F0D9')
_ORANGE = ('#C55A11', '#FCE4D6')
_PURPLE = ('#6A3D9A', '#E9DDF3')
_GRAY = ('#595959', '#EDEDED')


def _join(value: Any) -> str:
    return '\n'.join(str(item) for item in value or [])


def _characteristics(value: Any) -> str:
    return '\n'.join(f"{item['name']}: {item['value']}" for item in value or [])


def _rubles(value: Any) -> float | None:
    return None if value is None else value / 100


def _unix_time(value: Any) -> str:
    if not value:
        return ''
    return datetime.fromtimestamp(value, tz=timezone.utc).strftime('%Y-%m-%d %H:%M')


def _categories(value: Any) -> str:
    return '\n'.join(item['name'] for item in value or [])


def _col(header: str, key: str, width: int, palette: tuple[str, str], fmt=None) -> Column:
    return Column(header, key, width, palette[0], palette[1], fmt)


_PRODUCT_LIST = ('Список товаров', [
    _col('ID товара', 'external_id', 16, _GRAY),
    _col('Название', 'title', 50, _BLUE),
    _col('Ссылка', 'product_url', 45, _BLUE),
    _col('Цена', 'price_text', 16, _GREEN),
    _col('Скидка', 'discount', 14, _GREEN),
    _col('Наличие', 'stock', 18, _ORANGE),
])

_PRODUCT_PAGE = ('Карточки товаров', [
    _col('ID товара', 'external_id', 16, _GRAY),
    _col('Название', 'title', 50, _BLUE),
    _col('Ссылка', 'product_url', 45, _BLUE),
    _col('Бренд', 'brand', 18, _BLUE),
    _col('Артикул продавца', 'vendor_code', 18, _BLUE),
    _col('Категория', 'category', 28, _PURPLE),
    _col('Корневая категория', 'category_root', 28, _PURPLE),
    _col('Продавец', 'seller_name', 24, _PURPLE),
    _col('Цена со скидкой, ₽', 'discounted_price_kopecks', 18, _GREEN, _rubles),
    _col('Цена, ₽', 'price_kopecks', 14, _GREEN, _rubles),
    _col('Цена до скидки, ₽', 'original_price_kopecks', 18, _GREEN, _rubles),
    _col('Рейтинг', 'rating', 10, _ORANGE),
    _col('Отзывов', 'review_count', 10, _ORANGE),
    _col('В наличии', 'in_stock', 12, _ORANGE, lambda v: 'Да' if v else 'Нет'),
    _col('Описание', 'description', 60, _GRAY),
    _col('Характеристики', 'characteristics', 50, _GRAY, _characteristics),
    _col('Фото', 'photo_urls', 45, _GRAY, _join),
])

_REVIEWS = ('Отзывы', [
    _col('ID отзыва', 'external_uuid', 38, _GRAY),
    _col('Автор', 'author_name', 22, _BLUE),
    _col('Дата (UTC)', 'published_at', 18, _BLUE, _unix_time),
    _col('Оценка', 'score', 10, _ORANGE),
    _col('Отзыв', 'comment_text', 60, _GREEN),
    _col('Достоинства', 'positive_text', 40, _GREEN),
    _col('Недостатки', 'negative_text', 40, _GREEN),
    _col('Фото', 'photo_urls', 45, _GRAY, _join),
])

_SELLER = ('Профили продавцов', [
    _col('ID продавца', 'supplier_id', 14, _GRAY),
    _col('Название', 'name', 28, _BLUE),
    _col('Полное название', 'full_name', 36, _BLUE),
    _col('Торговая марка', 'trademark', 22, _BLUE),
    _col('ИНН', 'inn', 16, _PURPLE),
    _col('ОГРНИП', 'ogrnip', 18, _PURPLE),
    _col('КПП', 'kpp', 12, _PURPLE),
    _col('Рейтинг', 'rating', 10, _ORANGE),
    _col('Отзывов', 'feedbacks_count', 10, _ORANGE),
    _col('Дата регистрации', 'registration_date', 20, _GREEN, lambda v: (v or '')[:10]),
    _col('Товаров в продаже', 'sale_item_quantity', 16, _GREEN),
    _col('Всего товаров', 'total_products', 14, _GREEN),
    _col('Срок доставки', 'delivery_duration', 14, _GREEN),
    _col('Premium', 'is_premium', 10, _ORANGE, lambda v: 'Да' if v else 'Нет'),
    _col('Категории', 'categories', 40, _GRAY, _categories),
    _col('Ссылка', 'seller_url', 45, _GRAY),
])


def _kind(payload: dict) -> tuple[str, list[Column]]:
    if 'supplier_id' in payload:
        return _SELLER
    if 'external_uuid' in payload:
        return _REVIEWS
    if 'characteristics' in payload:
        return _PRODUCT_PAGE
    return _PRODUCT_LIST


def build_results_xlsx(results: Iterable[ResultItemEntity]) -> bytes:
    """Собирает xlsx: по листу на тип сущности (товары, карточки, отзывы, продавцы)."""
    buffer = BytesIO()
    workbook = xlsxwriter.Workbook(buffer, {'in_memory': True, 'strings_to_urls': False})

    grouped: dict[str, tuple[list[Column], list[dict]]] = {}
    for result in results:
        payload = result.payload or {}
        title, columns = _kind(payload)
        grouped.setdefault(title, (columns, []))[1].append(payload)
    if not grouped:
        grouped['Результаты'] = (_PRODUCT_LIST[1], [])

    base = {'valign': 'top', 'text_wrap': True, 'border': 1, 'border_color': '#BFBFBF'}
    for title, (columns, rows) in grouped.items():
        sheet = workbook.add_worksheet(title)
        header_formats = [
            workbook.add_format({
                'bold': True, 'font_size': 14, 'font_color': '#FFFFFF', 'bg_color': column.color,
                'align': 'center', 'valign': 'vcenter', 'text_wrap': True, 'border': 1,
                'border_color': '#FFFFFF',
            })
            for column in columns
        ]
        cell_formats = [
            workbook.add_format({**base, 'bg_color': column.tint}) for column in columns
        ]
        sheet.set_row(0, 36)
        for index, column in enumerate(columns):
            sheet.write(0, index, column.header, header_formats[index])
            sheet.set_column(index, index, column.width)
        for row_index, payload in enumerate(rows, start=1):
            for index, column in enumerate(columns):
                value = payload.get(column.key)
                if column.format is not None:
                    value = column.format(value)
                if value is None:
                    sheet.write_blank(row_index, index, None, cell_formats[index])
                else:
                    sheet.write(row_index, index, value, cell_formats[index])
        sheet.freeze_panes(1, 0)
        sheet.autofilter(0, 0, max(len(rows), 1), len(columns) - 1)

    workbook.close()
    return buffer.getvalue()
