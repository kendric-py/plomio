# packages/result

Доменная область хранения результатов парсинга маркетплейсов (товары, карточки товара, отзывы,
профили продавцов). `packages/task` хранит только оркестрацию задачи (статус, приоритет, курсор,
`result_count`) — сами спарсенные сущности хранятся здесь. Единственный текущий потребитель —
`apps/worker_parser`.

## Модель

Одна таблица `result_items`: `id` (UUID), `task_item_id` (FK → `task_items.id`, `ondelete='CASCADE'`),
`marketplace` (`core.enums.Marketplace`), `parse_type` (`packages.task.src.enums.ParseType`),
`payload` (JSONB), `created_at`.

**Одна строка = одна спарсенная сущность** (один товар, один отзыв, один профиль продавца) — не
пакет из нескольких сущностей в одном JSONB-массиве. Такой ритм соответствует тому, как воркер
персистит прогресс: `ResultService.record_results` вызывается в паре с
`TaskService.record_item_progress` после каждой обработанной страницы, а не в конце всего входа.

Одна таблица с непрозрачным `payload: JSONB` — по аналогии с `TaskItem.cursor` в `packages/task` —
вместо отдельной таблицы под каждую пару (маркетплейс, тип парсинга).

## Payload-модели — унифицированы по назначению, не по маркетплейсу

Одна pydantic-модель на тип сущности (не на пару маркетплейс×тип парсинга) —
`packages/result/src/entities.py`. Какой маркетплейс породил конкретную строку, хранится в
колонке `ResultItem.marketplace`, а не выражается отдельным классом payload. Унификация
разноформатных ответов Ozon и Wildberries в эту общую форму происходит внутри парсера каждого
маркетплейса (`apps/worker_parser/src/marketplaces/{ozon,wb}/parsers.py`), а не в этом домене —
сюда попадают уже нормализованные данные:

- `ProductPayload` — элемент списка товаров (`SEARCH_QUERY`/`CATEGORY`/`SELLER`): `external_id`,
  `title`, `product_url`, `price_text`, `discount`, `stock`.
- `ProductPagePayload` — полная карточка товара (`PRODUCT_PAGE`): `external_id`, `product_url`,
  `title`, `brand`, `vendor_code`, `category`, `category_root`, `seller_name`, `price_kopecks`,
  `original_price_kopecks`, `rating`, `review_count`, `in_stock`, `description`,
  `characteristics` (список `CharacteristicPayload`: name/value), `photo_urls`.
- `ReviewPayload` — отзыв (`REVIEWS`): `external_uuid`, `author_name`, `published_at`, `score`,
  `comment_text`, `positive_text`, `negative_text`, `photo_urls`.
- `SellerProfilePayload` — профиль продавца, доп. элемент к списку товаров при `SELLER`:
  `supplier_id`, `name`, `full_name`, `trademark`, `inn`, `ogrnip`, `kpp`, `rating`,
  `feedbacks_count`, `registration_date`, `sale_item_quantity`, `delivery_duration`, `is_premium`,
  `is_deleted`, `deactivated`, `categories` (список `SellerCategoryPayload`), `total_products`,
  `seller_url`.

Портированы из `marketplace-parser/src/schemas/*`, где схема уже была маркетплейс-агностичной
(различие маркетплейсов было полем `marketplace` внутри одной модели, а не отдельным классом) —
здесь этот же принцип, только `marketplace` хранится на уровне строки `result_items`, а не внутри
payload.

## Интеграция

`ResultItemRepository` подключается в
[`core.transaction_manager.AsyncTransactionManager`](../../core/transaction_manager.py) через
`use_result_repository=True`.

`ResultService.record_results(task_item_id, marketplace, parse_type, payloads)` — `payloads`
список отдельных сущностей одной страницы; каждая сохраняется отдельной строкой `result_items`.

## Зависимости

`packages/result` зависит от `packages/task` (`ParseType`) и `core` (`Marketplace`), не наоборот —
`packages/task` не знает о существовании `packages/result`.
