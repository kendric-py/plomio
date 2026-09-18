from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from core.enums import Marketplace
from packages.task.src.enums import ParseType


class ResultItemEntity(BaseModel):
    id: Optional[UUID] = Field(default=None, description='Идентификатор строки результата')
    task_item_id: Optional[UUID] = Field(
        default=None,
        description='Идентификатор элемента задачи, породившего эту сущность',
    )
    marketplace: Optional[Marketplace] = Field(default=None, description='Маркетплейс сущности')
    parse_type: Optional[ParseType] = Field(
        default=None,
        description='Тип парсинга, породивший эту сущность',
    )
    payload: Optional[dict] = Field(
        default=None,
        description='Сериализованная модель одной сущности (товар/отзыв/профиль продавца)',
    )
    created_at: Optional[datetime] = Field(default=None, description='Время сохранения сущности')


class CharacteristicPayload(BaseModel):
    """Унифицировано для обоих маркетплейсов — маппинг из маркетплейс-специфичного ответа в эту
    форму происходит внутри соответствующего парсера (`marketplaces/{ozon,wb}/parsers.py`)."""

    name: str = Field(...)
    value: str = Field(...)


class ProductPayload(BaseModel):
    """Элемент списка товаров (`SEARCH_QUERY`/`CATEGORY`/`SELLER`). Унифицировано для обоих
    маркетплейсов — который из них породил конкретную строку, определяет `ResultItem.marketplace`,
    не отдельный класс."""

    external_id: str | None = Field(default=None, description='Идентификатор товара у маркетплейса')
    title: str = Field(..., description='Название товара')
    product_url: str = Field(..., description='Ссылка на товар')
    price_text: str | None = Field(default=None, description='Цена в виде текста из выдачи')
    discount: str | None = Field(default=None, description='Текст скидки из выдачи')
    stock: str | None = Field(default=None, description='Текст о наличии из выдачи')


class ProductPagePayload(BaseModel):
    """Полная карточка товара (`PRODUCT_PAGE`). Унифицировано для обоих маркетплейсов."""

    external_id: str = Field(..., description='Идентификатор товара у маркетплейса')
    product_url: str = Field(..., description='Ссылка на товар')
    title: str = Field(..., description='Название товара')
    brand: str = Field(default='', description='Бренд')
    vendor_code: str = Field(default='', description='Артикул продавца')
    category: str = Field(default='', description='Категория товара')
    category_root: str = Field(default='', description='Корневая категория')
    seller_name: str = Field(default='', description='Название продавца')
    price_kopecks: int | None = Field(default=None, description='Цена в копейках')
    original_price_kopecks: int | None = Field(default=None, description='Цена без скидки в копейках')
    rating: float | None = Field(default=None, description='Рейтинг товара')
    review_count: int | None = Field(default=None, description='Количество отзывов')
    in_stock: bool = Field(default=True, description='Наличие товара')
    description: str = Field(default='', description='Описание товара')
    characteristics: list[CharacteristicPayload] = Field(
        default_factory=list,
        description='Характеристики товара',
    )
    photo_urls: list[str] = Field(default_factory=list, description='Ссылки на фотографии')


class ReviewPayload(BaseModel):
    """Отзыв (`REVIEWS`). Унифицировано для обоих маркетплейсов."""

    external_uuid: str = Field(..., description='Идентификатор отзыва у маркетплейса')
    author_name: str = Field(default='', description='Имя автора отзыва')
    published_at: int = Field(default=0, description='Unix-время публикации отзыва')
    score: int = Field(default=0, description='Оценка отзыва')
    comment_text: str = Field(default='', description='Текст отзыва')
    positive_text: str = Field(default='', description='Текст "достоинства"')
    negative_text: str = Field(default='', description='Текст "недостатки"')
    photo_urls: list[str] = Field(default_factory=list, description='Ссылки на фотографии отзыва')


class SellerCategoryPayload(BaseModel):
    """Унифицировано для обоих маркетплейсов."""

    category_id: int = Field(...)
    name: str = Field(...)
    parent_name: str | None = Field(default=None)


class SellerProfilePayload(BaseModel):
    """Профиль продавца, дополнительный элемент к списку товаров при `SELLER`. Унифицировано для
    обоих маркетплейсов."""

    supplier_id: int = Field(..., description='Идентификатор продавца')
    name: str | None = Field(default=None, description='Название продавца')
    full_name: str | None = Field(default=None, description='Полное юридическое название')
    trademark: str | None = Field(default=None, description='Торговая марка')
    inn: str | None = Field(default=None, description='ИНН')
    ogrnip: str | None = Field(default=None, description='ОГРНИП')
    kpp: str | None = Field(default=None, description='КПП')
    rating: str | None = Field(default=None, description='Рейтинг продавца')
    feedbacks_count: int | None = Field(default=None, description='Количество отзывов о продавце')
    registration_date: datetime | None = Field(default=None, description='Дата регистрации')
    sale_item_quantity: int | None = Field(default=None, description='Количество товаров в продаже')
    delivery_duration: int | None = Field(default=None, description='Срок доставки')
    is_premium: bool | None = Field(default=None, description='Премиум-статус продавца')
    is_deleted: bool | None = Field(default=None, description='Продавец удалён')
    deactivated: bool | None = Field(default=None, description='Продавец деактивирован')
    categories: list[SellerCategoryPayload] = Field(
        default_factory=list,
        description='Категории товаров продавца',
    )
    total_products: int | None = Field(default=None, description='Общее количество товаров')
    seller_url: str | None = Field(default=None, description='Ссылка на витрину продавца')
