# packages/notifications

Универсальная, провайдер-агностичная доменная область уведомлений. Не знает про `packages/task`/
`packages/automation` вообще — не только не зависит от них в коде, но и не хранит ссылок на их
объекты (никакого `reference_type`/`reference_id`, в отличие от `packages/billing`): настройки
пользователя полностью **глобальны**, не привязаны к конкретной автоматизации или задаче.

## Модель — каталог событий, по образцу `packages/billing`

Ключевое требование, симметричное `packages/billing` (см. [`packages/billing/AGENTS.md`](../billing/AGENTS.md),
"Конструктор"): новый тип события подключается без миграции схемы — новой строкой в каталоге плюс
одним вызовом `NotificationService.notify(...)` в коде вызывающего домена.

- **`NotificationEvent`** (`notification_events`) — каталог: `event_code` (человекочитаемый код,
  **primary key** — `"automation.change_detected"`, `"task.completed"`, `"task.failed"`),
  `description` (для UI), `is_active` (неактивное событие никогда не создаёт доставок — способ
  временно выключить событие без удаления строки/ссылок на него из `notification_deliveries`),
  `available_fields: JSONB list[str] | None` — имена полей, по которым можно фильтровать подписку
  на это событие (для `automation.change_detected` — все значения `TrackedField` из
  `packages/automation`, для `task.*` — `NULL`, у задач нет понятия "поле"). Домен **не
  интерпретирует** эти строки и не знает про `TrackedField` — просто хранит и отдаёт список,
  сравнение делает вызывающий код через `changed_fields` в `notify()` (см. ниже).
  **`template_variables` — не колонка этой таблицы**, живёт в коде
  (`packages/notifications/src/template_catalog.py::TEMPLATE_VARIABLES`), см. "Пользовательские
  шаблоны сообщений" ниже за обоснованием и полным описанием.
- **`NotificationSetting`** (`notification_settings`) — **одна строка на пользователя** (PK =
  `user_id`, тот же приём, что `CreditWallet`), `preferences: JSONB` — карта `{event_code:
  {"channels": [...], "fields": [...] | null, "template": str | null}}`. Отсутствие ключа для
  `event_code` или пустой список каналов = уведомления по этому событию выключены — **безопасный
  дефолт**: новый пользователь ничего не получает, пока явно не включит
  `PUT /api/notifications/preferences`. `fields` (подмножество `available_fields` этого события) —
  необязательный фильтр: `null`/пусто = уведомлять по любому срабатыванию события, непустой список =
  только если оно затронуло хотя бы одно из перечисленных полей. `template` — необязательный
  пользовательский текст сообщения, см. "Пользовательские шаблоны сообщений" ниже.
- **`NotificationDelivery`** (`notification_deliveries`) — append-only журнал: "это уведомление
  нужно отправить", тот же принцип, что `automation_check_log`/`credit_transactions`. `payload`
  (JSONB) — произвольные данные события для будущего отправителя (у `automation.*` — `changes`ы,
  у `task.*` — `task_id`/`error_reason`). `status` — `PENDING`/`SENT`/`FAILED`; в этой итерации
  создаются только `PENDING`, `SENT`/`FAILED` никогда не проставляются этим доменом.

## `NotificationService` — один generic-метод, все домены зовут только его

- **`notify(user_id, event_code, payload, changed_fields=None)`** — единственная точка интеграции.
  No-op (возвращает `[]`, ничего не пишет), если `event_code` не в каталоге/неактивен, или
  пользователь не включил ни одного канала для этого события, или фильтр (`fields`, либо
  производный от `template` — см. "Фильтрация по переменным шаблона" ниже) не пересекается с
  `changed_fields` — вызывающий домен никогда не должен падать из-за отсутствующей/выключенной/
  отфильтрованной настройки, тот же контракт, что у `BillingService.charge`. Иначе создаёт по одной
  строке `NotificationDelivery` на каждый включённый канал. `changed_fields` — какие поля затронуло
  конкретное срабатывание (например, `[c['field'] for c in changes]` из `AutomationCheckLog`);
  вызывающий домен передаёт `None`, если у события нет понятия "поле" (`task.*`).
- **`get_preferences`/`update_preferences`** — чтение/полная замена карты `preferences` текущего
  пользователя; `update_preferences` проверяет каждый `event_code` карты против каталога
  (`is_active`, иначе `UnknownNotificationEventError`), если задан `fields` — что он подмножество
  `available_fields` этого события (иначе `InvalidNotificationFieldFilterError`), и если задан
  `template` — что все `{переменные}`, использованные в нём, входят в ключи
  `template_catalog.get_template_variables(event_code)` (иначе `InvalidNotificationTemplateError`,
  см. "Пользовательские шаблоны сообщений").
- **`list_deliveries`** — постраничный журнал доставок пользователя.
- **`list_events`** — активные `event_code` из каталога, чтобы фронтенд строил форму настройки без
  хардкода списка событий на клиенте.

Никакого админского CRUD над каталогом в этой итерации (в отличие от `packages/billing`, где
`BillingAction`/`PricingMultiplierRule` — центральные конфигурационные таблицы, которыми управляет
администратор): `notification_events` заполняется data-миграцией по мере появления вызывающих
доменов, `NotificationSetting` целиком принадлежит пользователю.

## Кто сейчас вызывает `notify`

- **`packages/automation`** (`AutomationService.process_pending_results`, после коммита её
  транзакции — `_finalize_check` только строит `notify_call`/дикт-аргументы и возвращает их
  вызывающему коду, сам `notify()` не зовёт, см. "Композиция сервисов и транзакции" в
  [`packages/automation/AGENTS.md`](../automation/AGENTS.md)) — после записи тика в
  `automation_check_log`, один вызов при `has_changes or threshold_breached`:
  `event_code='automation.change_detected'`, `payload={'automation_id': ..., 'product_name': ...,
  'link': ..., 'automation_link': ..., 'changes': [...], 'changes_text':
  format_changes_text(changes), 'threshold_breached': ..., 'price_old': ..., 'price_new': ...,
  ...}` (плюс `{field}_old`/`{field}_new` на каждое из восьми отслеживаемых полей — см.
  "Переменные `automation.change_detected`" ниже), `changed_fields=[c['field'] for c in changes]`.
  `automation_link` — ссылка на страницу автоматизации в веб-интерфейсе (`{FRONTEND_BASE_URL}
  /automations/{automation_id}`), не путать с `link` (ссылка на карточку товара на маркетплейсе).
  Один `event_code` на оба случая — `threshold_breached` всегда подразумевает `has_changes`
  (поле, пробившее порог, всё равно попадает в `changes`), различать их отдельными событиями
  избыточно; получатель уведомления сам смотрит на `payload.threshold_breached`, если ему это
  важно. Фильтр по полям (`preferences[...].fields`) даёт то же самое различение на уровне
  подписки — например, подписаться только на `PRICE`/`DISCOUNTED_PRICE`. См.
  [`packages/automation/AGENTS.md`](../automation/AGENTS.md).
- **`packages/task`** (`TaskService.complete_item`) — при переходе задачи в терминальный статус:
  `event_code='task.completed'`/`'task.failed'`, `payload={'task_id': ..., 'error_reason': ...,
  'task_link': ..., 'result_count': ...}`. `task_link` — ссылка на страницу задачи в веб-интерфейсе
  (`{FRONTEND_BASE_URL}/tasks/{task_id}`). `result_count` — суммарное количество собранных
  результатов по всем `TaskItem` задачи на момент завершения (`sum(item.result_count for item in
  items)`, тот же агрегат, что `TaskService.get_progress`, посчитанный на уже прочитанных сиблингах,
  без дополнительного запроса). **Пропускается**, если `Task.automation_id is not None`
  — это внутренняя проверочная задача автоматизации, её завершение уже обрабатывается событиями
  `automation.*` для того же тика, повторное `task.*`-уведомление было бы дублем. См.
  [`packages/task/AGENTS.md`](../task/AGENTS.md).

Оба вызова — вне открытого `async with self.transaction_manager(...)`-блока вызывающего домена
(после коммита его собственной транзакции), тот же принцип "композиции сервисов", что описан в
[`packages/automation/AGENTS.md`](../automation/AGENTS.md#композиция-сервисов-и-транзакции):
`NotificationService` резолвится DI-контейнером как отдельный `providers.Factory`, со своим
`AsyncTransactionManager`/сессией.

## Интеграция

`NotificationEventRepository`/`NotificationSettingRepository`/`NotificationDeliveryRepository`
подключаются в [`core.transaction_manager.AsyncTransactionManager`](../../core/transaction_manager.py)
через `use_notification_event_repository=True`/`use_notification_setting_repository=True`/
`use_notification_delivery_repository=True`.

## Базовый URL фронтенда

Базовый URL фронтенда, без завершающего `/`; фронтенд не живёт в этом репозитории, поэтому значение
приходит только из конфига. Инжектируется как обычная строка (не `Config`-объект — домен не должен
знать про REST-конфиг apps/api, тот же принцип, что у `telegram_notifier`/`telegram_link_store` в
`NotificationService`), отдельно для каждого места, которое реально строит ссылку — **два разных
процесса, два разных `.env`, значение нужно задать в обоих**:

- `AutomationService.frontend_base_url` ← `config.REST.FRONTEND_BASE_URL`
  (`apps/api/src/config.py::RestConfig`, `.env`: `REST_FRONTEND_BASE_URL`) — `AutomationService`
  живёт только в `apps/api` (`AUTOMATION_RESULT_SWEEP` тикает на его event loop), поэтому для
  `automation_link` этого единственного источника достаточно.
- `TaskService.frontend_base_url` — **не всегда `apps/api`**: обычные (не проверочные) задачи
  завершает `apps/worker_parser` (`TaskService.complete_item`, вызывается из `task_runner.py`, не из
  `apps/api`), у него свой процесс и свой `.env` (`apps/worker_parser/src/config.py::Config.
  FRONTEND_BASE_URL`, без REST-префикса — свой конфиг, не переиспользует `RestConfig`), собственный
  от `apps/api`'s `REST_FRONTEND_BASE_URL`. `services.py::build_services` передаёт его в
  `TaskService` тем же способом, что `apps/api/src/container.py` — своей строкой, не объектом
  конфига. Если задать `REST_FRONTEND_BASE_URL` только в `apps/api/.env`, `task_link` для обычных
  задач всё равно останется `None` — нужно продублировать значение в `apps/worker_parser/.env`
  (`FRONTEND_BASE_URL`). См. [`apps/worker_parser/AGENTS.md`](../../apps/worker_parser/AGENTS.md).

Оба конструируют `task_link`/`automation_link` перед вызовом `notify()` — см.
`TaskService.complete_item` и `AutomationService._finalize_check`. Пустая строка (не задан в `.env`)
→ оба поля `None` в `payload`, а не URL с пустым хостом.

## REST

`apps/api/src/routers/notifications/` (`/api/notifications`, все owner-only,
`Depends(get_current_user)`): `GET /events` (включает `available_fields`, чтобы фронт строил
фильтр по полям без хардкода), `GET`/`PUT /preferences` (карта `{event_code: {channels, fields}}`),
`GET /deliveries` (read-only — доставки создаются только доменом, не пользователем).

## Пользовательские шаблоны сообщений

Каждый пользователь может задать свой текст сообщения на событие — `NotificationEventPreference.
template`, часть той же карты `preferences`, что `channels`/`fields`. Синтаксис — свой минимальный
`{name}` (`packages/notifications/src/formatting.py::_VARIABLE_PATTERN`, regex `\{(\w+)\}`), не
`string.Template` и не Jinja2/произвольный Python: **сознательный выбор**, а не временное
упрощение — грамматика физически умеет только "найти `{name}` и заменить его значением из payload",
без циклов, выражений, доступа к атрибутам/индексам (`{name.attr}`/`{name[0]}`) и вызова функций —
а значит не требует ни песочницы, ни ревью на предмет инъекций, даже притом что шаблон редактирует
сам пользователь (влияет только на текст, который придёт ему же в Telegram — не на других
пользователей и не на поведение системы).

- **`template_catalog.py::TEMPLATE_VARIABLES: dict[str, dict[str, NotificationTemplateVariableEntity]]`**
  — `{event_code: {переменная: {field, description, is_money}}}`. **Живёт в коде, не в БД** —
  сознательное решение, не временное упрощение: новая переменная в принципе не может появиться без
  правки кода домена, который кладёт её в `payload` (`packages/automation`/`packages/task`), так что
  хранить её описание отдельно в БД и синхронизировать миграцией на каждое добавление/переименование
  было бы лишним шагом, а не гибкостью — этот каталог не то, что администратор захочет поменять без
  деплоя (в отличие от `event_code`/`description`/`is_active`/`available_fields` в
  `notification_events`, которые как раз остались в БД). Добавление/правка переменной = правка
  словаря в `template_catalog.py` + обычный деплой, без Alembic. Непустое `field` означает, что
  использование `{имя}` в шаблоне подписывает доставку на изменения именно этого поля (см.
  "Фильтрация по переменным шаблона" ниже); `field: None` — переменная не привязана ни к какому
  полю, чисто контекстная (например, `product_name`/`link` — они не значат "уведомлять при
  изменении названия/ссылки", просто показывают текущее значение). `description` —
  человекочитаемое объяснение для UI (`GET /api/notifications/events`), что именно переменная
  показывает — фронт строит по нему подсказку "доступные переменные" рядом с полем ввода шаблона,
  без хардкода текста на клиенте. `is_money` — см. "Переменные `automation.change_detected`" ниже.
  **Не путать с `available_fields`** (список `TrackedField` в БД, для ручного фильтра `fields`) —
  разные структуры, разное назначение и разное место хранения.
- **Валидация** — `NotificationService.update_preferences`: `formatting.get_used_variables
  (preference.template)` (извлекает имена без рендера, той же regex-граммой) обязано быть
  подмножеством `set(template_catalog.get_template_variables(event_code).keys())`, иначе
  `InvalidNotificationTemplateError` → REST `422`. Проверяется на **сохранении**, не на отправке —
  невалидный шаблон в БД в принципе не может оказаться.
- **Рендер** — `formatting.py::build_message_text(event_code, payload, template)`: если `template`
  задан, `render_template(template, payload)` — подставляет `payload[name]` на место каждого
  `{name}` (`None` → пустая строка, не литерал `"None"`), а `{name}`, отсутствующее в `payload`
  (устарело — `template_variables` события сузились уже после того, как пользователь сохранил
  шаблон под старый набор), оставляет как есть в тексте буквально, не роняя отправку в `FAILED`;
  иначе — встроенный форматтер по `event_code` (`MESSAGE_FORMATTERS`), тот же путь, что был до
  этого раздела.
- **`parse_mode=HTML` — постоянный, на уровне бота**, не аргумент отдельных вызовов
  `send_message`/`message.answer`: оба места, создающие `aiogram.Bot`
  (`telegram_client.py::TelegramNotifier`, `telegram_polling.py::run_telegram_polling`), передают
  `default=DefaultBotProperties(parse_mode=ParseMode.HTML)`. Это значит, что **пользователь может
  писать HTML-разметку прямо в своём шаблоне** (`<b>`/`<i>`/`<a href="...">`) — она уйдёт в
  Telegram как есть, отрисуется жирным/курсивом/ссылкой. Но это же значит, что любое подставляемое
  *значение* обязано быть HTML-экранировано **до** подстановки — иначе `<`/`&` из данных
  маркетплейса (название товара, имя продавца, текст ошибки — ничего из этого не под нашим
  контролем) либо ломает HTML-парсер Telegram (доставка получает `FAILED` с ошибкой парсинга), либо
  незаметно интерпретируется как разметка. Поэтому `formatting.py::_escape` (`html.escape` из
  стандартной библиотеки) применяется к **каждому** подставляемому значению — и в `render_template`
  (пользовательские `{name}`), и во встроенных `format_*`-функциях (`automation_id`, `task_id`,
  `error_reason`, содержимое `changes_text` на момент рендера) — но не к собственному тексту
  шаблона пользователя (тот, что вне `{name}`), иначе его собственная разметка сломалась бы тоже.
  **`format_changes_text` при этом сознательно не экранирует** — она пишет
  `payload['changes_text']`, а это канал-агностичные данные, которые ещё и отдаются как есть в
  `GET /api/notifications/deliveries`; экранирование там означало бы протекание Telegram-специфики
  в общий журнал. Экранирование происходит один раз, на границе фактического рендера для Telegram.

### Переменные `automation.change_detected`

Помимо `automation_id`/`changes`/`changes_text` (см. "Кто сейчас
вызывает `notify`" выше), доступны:

- `product_name`, `link` — заголовок и ссылка карточки на момент **этого** тика
  (`ProductPagePayload.title`/`.product_url`), не привязаны ни к какому `TrackedField` — чисто
  контекст для текста сообщения, использование не подписывает ни на что.
- `automation_link` — ссылка на страницу автоматизации в веб-интерфейсе (`{FRONTEND_BASE_URL}
  /automations/{automation_id}`, см. "Базовый URL фронтенда" ниже), тоже не привязана ни к какому
  `TrackedField`. `None`, если `FRONTEND_BASE_URL` не задан (рендерится как пустая строка).
- **`{field}_old`/`{field}_new`** на каждое из восьми отслеживаемых полей (`price_old`/
  `price_new`, `discounted_price_old`/`discounted_price_new`, `original_price_old`/
  `original_price_new`, `in_stock_old`/`in_stock_new`, `title_old`/`title_new`, `rating_old`/
  `rating_new`, `review_count_old`/`review_count_new`, `seller_name_old`/`seller_name_new`) —
  **всегда** присутствуют в `payload`, даже если конкретно это поле в этом тике не менялось (иначе
  в шаблоне были бы пустые места при срабатывании по другому полю). `_new` — значение из текущего
  `snapshot` (`AutomationService._build_snapshot`), `_old` — из `snapshot` **предыдущего успешного**
  тика (`AutomationCheckLogRepository.get_latest_succeeded`, `None` на самом первом успешном тике
  автоматизации, что и рендерится как пустая строка). Имена — `TRACKED_FIELD_VARIABLE_NAMES` в
  `packages/automation/src/service.py`, рядом с `TRACKED_FIELDS`.
- Цены (`price_*`/`discounted_price_*`/`original_price_*`) — в `payload` (и в `GET /api/
  notifications/deliveries`) по-прежнему копейки, как везде в API, но **при рендере в шаблон
  подставляются как рубли** ("1 500,00 ₽", не "150000") — см. `is_money` в
  `template_catalog.TEMPLATE_VARIABLES` выше.

## Фильтрация по переменным шаблона

Если у `preference` задан `template`, он **заменяет** `fields` как фильтр постановки в очередь, а
не дополняет его — `NotificationService.notify` вызывает `derive_gating_fields(template,
event_code)`: множество полей, на которые ссылаются переменные, реально использованные в шаблоне
(пересечение `get_used_variables(template)` с ключами `template_catalog.get_template_variables
(event_code)`, у которых `.field` непусто). Доставка создаётся, только если это множество
пересекается с `changed_fields` данного срабатывания — **или множество пусто** (шаблон не
использует ни одной field-переменной, например только `{product_name}`/`{link}` — тогда фильтра
нет вообще, срабатывает на любое изменение, как `fields=null`).

Мотивация — не давать пользователю держать в синхроне два независимых списка (`fields` и то, что он
реально показывает в тексте): подписка на `fields=["RATING"]` при шаблоне, который показывает
только цену со скидкой, раньше присылала бы уведомление с текстом про цену на срабатывание по
рейтингу, содержащим неизменившиеся (устаревшие по смыслу, хоть и не по значению) `{discounted_
price_old}`/`{discounted_price_new}`. Значение `fields` в `preferences[event_code]`, если оно там
осталось от предыдущей настройки, **игнорируется** целиком, пока задан `template` — не объединяется
и не пересекается с производным множеством полей шаблона.

`changes_text` у `automation.change_detected` — отдельный случай: `{name}`-подстановка не умеет
проходить циклом по списку, а `payload.changes` — список объектов (`{field, old_value, new_value,
threshold_breached}`). Поэтому `AutomationService._finalize_check` сам схлопывает список в готовую
многострочную строку через `formatting.py::format_changes_text(changes)` **до** вызова `notify()` и
кладёт результат в `payload['changes_text']` рядом с сырым `payload['changes']` — пользовательский
шаблон работает только с уже готовой строкой, не с исходной структурой. Тот же `format_changes_text`
переиспользует и встроенный форматтер этого события, чтобы не дублировать логику склейки.
`changes_text` в `template_catalog` имеет `field=None` (не гейтит ни на что) — она уже отражает
*все* изменившиеся поля разом, привязывать её к одному конкретному полю было бы неверно.

## Отправка — `NotificationService.dispatch_pending`

Периодический job **`NOTIFICATION_DELIVERY_SWEEP`** (`packages/cron` + `apps/api/src/jobs/
notification_delivery_sweep.py`, `config.NOTIFICATIONS.DELIVERY_SWEEP_INTERVAL_SECONDS`/
`DELIVERY_SWEEP_BATCH_SIZE`) — тикает на event loop `apps/api`, не отдельный процесс (тот же
принцип, что `AUTOMATION_DISPATCH`/`AUTOMATION_RESULT_SWEEP`, см.
[`packages/cron/AGENTS.md`](../cron/AGENTS.md)). Вызывает `NotificationService.dispatch_pending
(batch_size)`:

1. `NotificationDeliveryRepository.claim_pending(limit)` — атомарно захватывает до `limit` самых
   старых `PENDING`-доставок (`FOR UPDATE SKIP LOCKED`, защита от повторной отправки при нескольких
   репликах `apps/api`, тот же приём, что `AutomationRepository.claim_due_for_dispatch`/
   `TaskRepository.claim_next`). В отличие от `TASK_LEASE_RECLAIM_SWEEP`, отдельного job'а на
   "зависшие" доставки не нужно: строка не покидает `PENDING`, пока сам процесс не запишет
   терминальный статус в этой же транзакции — крэш между захватом и записью откатывает транзакцию
   целиком, строка остаётся `PENDING` и просто берётся следующим тиком.
2. Для канала `TELEGRAM` (единственный сейчас): если у пользователя нет `telegram_id`
   (`packages/user`) — сразу `FAILED`, `failure_reason='telegram_id не привязан'` (ретраить
   бессмысленно, состояние само не изменится). Иначе — читает `NotificationSetting.preferences
   [event_code].template` этого пользователя (текущее значение на момент отправки, не то, что было
   на момент `notify()`) и рендерит текст через
   `packages/notifications/src/formatting.py::build_message_text(event_code, payload, template)` —
   пользовательский `template`, если задан, иначе встроенный форматтер по `event_code` (см.
   "Пользовательские шаблоны сообщений" ниже) — и отправляет через `TelegramNotifier.send`
   (`telegram_client.py`, тонкая обёртка над `aiogram.Bot`).
3. **Одна попытка на доставку, без retry/backoff** — неудачная отправка сразу `FAILED` с текстом
   исключения в `failure_reason`, не переигрывается следующим тиком. Сознательное упрощение этой
   итерации (см. ниже).

`TelegramNotifier` собирается в DI-контейнере `apps/api` (`container.telegram_notifier`,
`providers.Singleton(build_telegram_notifier, bot_token=..., proxy_url=...)`) и
инжектируется в `NotificationService` необязательным параметром. Пустой `TELEGRAM_BOT_TOKEN`
(`core.configs.TelegramConfig`, по умолчанию) — `build_telegram_notifier` возвращает `None`,
`dispatch_pending` в этом случае пропускает `TELEGRAM`-доставки (оставляет `PENDING`), не падает —
тот же приём, что `LivenessReporter` при пустом `LIVENESS_ENDPOINT_URL`.

**Прокси для Bot API.** Если с хоста `api.telegram.org` недоступен напрямую (бот тогда молчит:
`TelegramNetworkError: Request timeout error`, polling падает), задаётся `TELEGRAM_PROXY_URL` —
SOCKS5 в виде `socks5://user:pass@host:port` (спецсимволы в логине/пароле — в URL-кодировке).
Пустое значение (по умолчанию) — бот ходит в Telegram напрямую, без прокси. Единая точка сборки
бота — `telegram_client.build_bot(bot_token, proxy_url)` (`AiohttpSession(proxy=...)`, нужен пакет
`aiohttp-socks` в зависимостях `apps/api`); её используют и `TelegramNotifier`, и long polling.

## Привязка Telegram

`User.telegram_id` не заполняется вручную — пользователь привязывает свой Telegram через deep-link:

1. `POST /api/notifications/telegram/link` (owner-only) → `NotificationService.
   create_telegram_link_code(user_id, ttl_seconds)` → `TelegramLinkStore.create_link_code`
   (`telegram_link_store.py`) генерирует одноразовый код (`secrets.token_urlsafe`) и кладёт его в
   Redis: `telegram_link:{code}` — `SET ... EX <ttl_seconds>` со значением `user_id`, тот же приём
   TTL-ключа, что `packages.sessions.SessionPoolStore` (`config.TELEGRAM.LINK_CODE_TTL_SECONDS`,
   по умолчанию 600с). Ответ — `deep_link: https://t.me/{TELEGRAM_BOT_USERNAME}?start={code}`
   (`TELEGRAM_BOT_USERNAME` — только для сборки ссылки, не для аутентификации Bot API).
2. Пользователь переходит по ссылке в Telegram → бот получает `/start <code>` —
   `packages/notifications/src/telegram_polling.py` (обработчик на `aiogram.Dispatcher`, фильтр
   `CommandStart(deep_link=True)`) вызывает `NotificationService.confirm_telegram_link(code,
   telegram_user_id)`:
   - `TelegramLinkStore.consume_link_code(code)` — `GET` + `DEL` одним ходом (код одноразовый:
     повторный `/start` с уже использованным кодом не может повторно привязать другой аккаунт).
     `None` (код не найден/истёк) → `TelegramLinkOutcome.INVALID_CODE`.
   - Если `telegram_id` уже занят **другим** пользователем — `ALREADY_LINKED_OTHER`, ничего не
     меняется (метод никогда не отбирает Telegram-аккаунт у одного пользователя в пользу другого).
   - Если уже привязан этому же пользователю — `ALREADY_LINKED_SAME`, no-op.
   - Иначе — `UserRepository.update(UserEntity(id=user_id, telegram_id=telegram_user_id))`,
     `TelegramLinkOutcome.LINKED`.
   - `telegram_polling.py::OUTCOME_TEXT` отвечает пользователю в том же чате соответствующим
     текстом.

**Long polling — временное решение этой итерации.** `run_telegram_polling` (`apps/api/src/server.py`
lifespan, запускается только если задан `TELEGRAM_BOT_TOKEN`) крутит `dispatcher.start_polling`
как ещё один `asyncio.create_task` рядом с cron-джобами — но, в отличие от них, **безопасно только
для одной реплики `apps/api`**: несколько реплик, поллящих один и тот же `bot_token`, конфликтуют
на `getUpdates` (Telegram отвечает `409 Conflict` всем, кроме одной, выигравшей гонку). Замена на
webhook (`POST /api/notifications/telegram/webhook`, `config.REST.PUBLIC_BASE_URL` уже
зарезервирован под это в конфиге) — задокументированная будущая работа, не в этой итерации.
`handle_signals=False` при `start_polling` — эта задача не должна ставить свои `SIGINT`/`SIGTERM`-
обработчики поверх uvicorn'а, процесс останавливает её сам через `task.cancel()` в `lifespan`.
Если polling падает с исключением (например, недоступен Telegram), оно логируется
(`[telegram_polling] polling crashed`) и polling перезапускается через 10 секунд — иначе фоновая
задача умирала бы молча, и бот просто переставал отвечать.

## Не входит в эту итерацию

- Webhook вместо long polling для приёма апдейтов Telegram (см. выше).

- Retry/backoff для неудачной отправки — доставка, не отправившаяся с первой попытки, остаётся
  `FAILED` навсегда, не переигрывается.
- Настройки, привязанные к конкретному объекту (например, отдельная настройка на одну
  автоматизацию, а не глобально для пользователя) — сейчас `NotificationSetting` намеренно не
  хранит `reference_type`/`reference_id`; если понадобится — отдельное расширение модели, не эта
  итерация.
- Админский CRUD каталога `notification_events` — заполняется только миграциями.
- Каналы кроме Telegram.

## Доставки задачи (админка)

`NotificationService.list_deliveries_for_task(task_id)` → `NotificationDeliveryRepository.get_by_task_id`:
доставки, у которых `payload.task_id == task_id` (`task.completed`/`task.failed` кладёт `task_id` сам, а
`automation.change_detected` — `task_id` проверочной задачи тика, `AutomationService._finalize_check`). Поиск
идёт по индексу `ix_notification_deliveries_payload_task_id` (выражение `payload->>'task_id'`, миграция
`d7a1c3e5b902`). Используется `GET /api/admin/tasks/{task_id}`. `list_deliveries_for_automation(automation_id, limit, offset)` — вся история уведомлений автоматизации
(`payload.automation_id`, индекс `ix_notification_deliveries_payload_automation_id`, та же миграция),
`GET /api/admin/automations/{id}/notifications`.

Доставки автоматизаций, созданные **до**
появления `task_id` в payload, подбираются по времени: `automation.change_detected` той же автоматизации
(`payload.automation_id`), поставленный в течение `LEGACY_DELIVERY_WINDOW` (5 мин) после `finished_at`
проверочной задачи (свип результатов отрабатывает за секунды). Эвристика действует только для доставок
без `task_id`.
