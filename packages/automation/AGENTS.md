# packages/automation

Доменная область периодических задач-мониторинга цены (упоминалась как будущая работа в
[`packages/task/AGENTS.md`](../task/AGENTS.md) и в корневом [`AGENTS.md`](../../AGENTS.md), раздел
"Домен: задачи"). Пользователь регистрирует автоматизацию — ссылку/артикул товара, маркетплейс,
порог падения цены и периодичность — система периодически перепарсивает товар и фиксирует **каждый
тик проверки** (успех/провал/успех без изменений) в лог, для последующих графиков и уведомлений
(см. [`packages/notifications/AGENTS.md`](../notifications/AGENTS.md) — доменная область
существует и вызывается отсюда, реальная отправка всё ещё отложена).

Не строит собственную очередь — переиспользует [`packages/task`](../task) (`ParseType.PRODUCT_PAGE`,
одноэлементная задача на каждую проверку) и [`packages/result`](../result) (чтение спарсенного
результата). `AutomationService` оркестрирует оба сервиса через внедрённые `TaskService`/
`ResultService`, а не работает с их репозиториями напрямую.

## Модель

- **`Automation`** (`automations`) — сама автоматизация: `marketplace`, `input_value` (ссылка/
  артикул), `article` (см. "Дубли по артикулу" ниже), `status` (`ACTIVE`/`PAUSED`),
  `price_drop_threshold_percent` (1..100, `CheckConstraint`), `check_frequency_minutes` (минимум
  валидируется на уровне сервиса против сконфигурированного `min_check_frequency_minutes`, не
  `CheckConstraint` — минимум конфигурируем и может меняться без миграции), `history_retention_days`,
  три базовые цены
  (`baseline_price_kopecks`/`baseline_discounted_price_kopecks`/`baseline_original_price_kopecks`),
  `in_stock` (наличие по последней завершённой проверке, `NULL` — проверок ещё не было; см.
  "Отслеживание наличия" ниже), `next_check_at`, `pending_task_id` (FK на `tasks.id`, `SET NULL`),
  `last_checked_at`, `last_check_error`, `user_id`.
- **`AutomationCheckLog`** (`automation_check_log`, переименована из `AutomationHistory`/
  `automation_history` — смысл таблицы фундаментально изменился) — append-only лог. **Одна строка =
  один тик проверки, всегда** — успех, провал или успех без изменений (раньше строка писалась
  только при успехе с реальным изменением): `succeeded`, `error_message` (причина провала;
  `None` при успехе), `snapshot` (`JSONB`, полный снимок всех отслеживаемых полей на момент тика —
  только при успехе; нужен, чтобы следующий тик было с чем сравнивать), `changes` (`JSONB`, список
  `{field, old_value, new_value, threshold_breached}` — все поля, изменившиеся **относительно
  предыдущего успешного тика**), `has_changes` (`bool(changes)`), `threshold_breached` (агрегат,
  `any(change['threshold_breached'] for change in changes)` — семантика не изменилась, см. "Семантика
  базовой цены" ниже) и `checked_at` (переименовано из `detected_at`). `id` — автоинкрементный
  `int`, не `UUID` (внутренняя запись, не публичный ресурс, как `cron_job_runs`), в отличие от
  `Automation.id` (`UUID`, публичный ресурс, как `Task.id`).

**`has_changes` vs `threshold_breached` — два независимых сравнения, с разными точками отсчёта:**

- `has_changes` — новое значение поля сравнивается со **снимком предыдущего успешного тика**
  (`AutomationCheckLogRepository.get_latest_succeeded`). Отвечает на вопрос "что-то изменилось с
  прошлой проверки" — для всех восьми отслеживаемых полей одинаково.
- `threshold_breached` — новое значение сравнивается с фиксированным **baseline** на `Automation`
  (см. "Семантика базовой цены" ниже), только для `KOPECKS`-полей и восстановления наличия. Отвечает
  на вопрос "пробит ли порог падения цены/товар снова в наличии" — не путать с `has_changes`:
  постепенное падение цены на 1% за тик может быть `has_changes=true` много раз подряд, пока
  `threshold_breached` не станет `true` только когда накопленное падение относительно baseline
  превысит `price_drop_threshold_percent`.

## Отслеживаемые поля

`ProductPagePayload` (`packages/result/src/entities.py`) отдаёт карточку товара. Восемь полей
отслеживаются на изменение — `TrackedField`/`TrackedFieldKind` (`packages/automation/src/enums.py`)
и `TRACKED_FIELDS` в `service.py` (единственное место, где перечислены все восемь):

| `TrackedField` | `TrackedFieldKind` | baseline-колонка на `Automation` | payload-поле |
|---|---|---|---|
| `PRICE` | `KOPECKS` | `baseline_price_kopecks` | `price_kopecks` |
| `DISCOUNTED_PRICE` | `KOPECKS` | `baseline_discounted_price_kopecks` | `discounted_price_kopecks` |
| `ORIGINAL_PRICE` | `KOPECKS` | `baseline_original_price_kopecks` | `original_price_kopecks` |
| `IN_STOCK` | `BOOLEAN` | `in_stock` | `in_stock` |
| `TITLE` | `TEXT` | — | `title` |
| `RATING` | `NUMERIC` | — | `rating` |
| `REVIEW_COUNT` | `NUMERIC` | — | `review_count` |
| `SELLER_NAME` | `TEXT` | — | `seller_name` |

Поля без baseline-колонки (`TITLE`/`RATING`/`REVIEW_COUNT`/`SELLER_NAME`) участвуют только в
`has_changes` (сравнение с предыдущим тиком) — у них нет понятия "порог в процентах", `threshold_
breached` для них всегда `False`.

## Отслеживание наличия (in_stock)

`ProductPagePayload.in_stock` — тот же payload, что и остальные поля (см. таблицу выше), `TrackedFieldKind.BOOLEAN`:

- `threshold_breached = True` только когда `False → True` (товар снова появился в наличии) — это и
  есть событие, ради которого частота проверки для отсутствующего в наличии товара увеличена (см.
  ниже). Переход `True → False` тоже пишется в лог (для графика доступности), но не считается
  "пробитием порога".
- `AutomationService._diff_against_previous_and_baseline` пишет в общий `baseline_updates`-дикт
  (`dict[str, int | bool]`, несмотря на имя — исторически "только baseline_*_kopecks", теперь ещё и
  `in_stock`), который одним `UPDATE` уходит в `AutomationRepository.finalize_check`.

Частота следующей проверки, пока `in_stock = false`, — не `check_frequency_minutes` пользователя, а
`config.AUTOMATION.OUT_OF_STOCK_CHECK_FREQUENCY_MINUTES` (константа конфига, не настраивается на
уровне автоматизации): `AutomationRepository.claim_due_for_dispatch` выбирает между ними через `CASE
WHEN in_stock = false` прямо в `UPDATE ... SET next_check_at`. Смысл — проверять товар без наличия
чаще, чем раз в обычный (обычно куда более длинный) пользовательский интервал, чтобы быстрее поймать
факт появления в наличии.

`apps/worker_parser`: у Ozon `webPrice.isAvailable` присутствует и `true` только когда товар в
наличии — при отсутствии наличия ключ пропадает вовсе (не становится `false`), поэтому
`in_stock` на Ozon определяется по отдельному виджету `webOutOfStock` (появляется на карточке
проданного товара — предлагает купить у другого продавца), а не по одному `isAvailable`. У
Wildberries `in_stock = totalQuantity > 0` — надёжно работает уже как есть (`totalQuantity: 0` и
пустые `stocks` у всех размеров на реально распроданном товаре).

## Дубли по артикулу

Пользователь не может завести вторую автоматизацию на тот же товар в рамках одного маркетплейса —
даже если ссылку он ввёл в другом виде (другой текст слага, другие query-параметры и т.п.).

- При создании `core.marketplace_article.extract_article(marketplace, input_value)` пытается
  вытащить числовой артикул прямо из строки — без похода в сеть (Ozon: `-<цифры>` в конце пути
  URL; Wildberries: `/catalog/<цифры>/`; либо, если вся строка — просто число, она сама и есть
  артикул). Результат кладётся в `Automation.article` (может быть `NULL`, если формат не
  распознан). Это **не** тот же код, что использует `apps/worker_parser` для реального фетчинга
  (там URL-парсинг рассчитан на строго валидный URL и либо бросает исключение, либо тихо
  подставляет заглушку — для проверки дублей нужен мягкий результат "не смогли понять", а не
  ошибка).
- `AutomationRepository.find_duplicate` ищет у пользователя в этом маркетплейсе автоматизацию
  (**в любом статусе** — `PAUSED` тоже считается) с тем же `article`; если `article` вытащить не
  удалось — фолбэк на точное совпадение `input_value` (больше никакого надёжного способа
  сравнить нет).
- Найденный дубликат → `DuplicateAutomationError` (`packages/automation/src/exceptions.py`) →
  REST `409 Conflict`.
- Частичный уникальный индекс `ux_automations_user_marketplace_article` (`(user_id, marketplace,
  article) WHERE article IS NOT NULL`) — подстраховка на случай гонки между `find_duplicate` и
  `create` (два одновременных запроса); `BaseRepository.create` в этом случае ловит
  `IntegrityError` → `DuplicatedObjectError` (`core.exceptions`), сервис перехватывает и
  переводит в тот же `DuplicateAutomationError`.

## Семантика базовой цены (baseline)

Базовая цена — точка отсчёта для сравнения, а не "цена на предыдущей проверке":

- Проставляется автоматически при **первой** успешной проверке автоматизации (когда
  `baseline_*_kopecks IS NULL`) — в историю при этом ничего не пишется.
- На всех последующих проверках сравнение всегда идёт с этой зафиксированной базовой ценой, а не с
  результатом предыдущей проверки — иначе постепенное падение цены на 1% за проверку никогда не
  накопилось бы до порога уведомления.
- Пользователь может обновить базовую цену вручную (`AutomationService.update_baseline`,
  `PATCH /api/automations/{id}/baseline`) — например, чтобы "переустановить" точку отсчёта после
  осознанного решения считать текущую цену новой нормой.
- `threshold_breached` на строке лога — `new_value <= baseline_value * (1 -
  price_drop_threshold_percent / 100)`, вычисляется относительно baseline на момент проверки, не
  относительно снимка предыдущего тика (см. "has_changes vs threshold_breached — два независимых
  сравнения" выше).

В лог пишется **любое** изменение поля между тиками (не только просадка ниже baseline) — под
будущие графики; `threshold_breached`/`has_changes` — оба триггерят `NotificationService.notify`
(`packages/notifications`) с разными `event_code` (см. "Уведомления" ниже).

## Флоу выполнения (три периодических job'а, `packages/cron` + `apps/api/src/jobs`)

1. **`AUTOMATION_DISPATCH`** (`AutomationService.dispatch_due_checks`) — раз в
   `config.AUTOMATION.DISPATCH_INTERVAL_SECONDS`, в три фазы (не одна транзакция — см.
   "Deadlock между `tasks.automation_id` и `claim_due_for_dispatch`" ниже, это не рефакторинг для
   красоты, а обязательный порядок):
   1. `AutomationRepository.claim_due_for_dispatch` — одной транзакцией атомарно находит
      `ACTIVE`-автоматизации с `next_check_at <= now()` и `pending_task_id IS NULL`
      (`FOR UPDATE SKIP LOCKED` — защита от повторного диспатча при нескольких репликах `apps/api`,
      как `TaskRepository.claim_next`) и сразу сдвигает им `next_check_at` на
      `check_frequency_minutes` вперёд (или на `config.AUTOMATION.
      OUT_OF_STOCK_CHECK_FREQUENCY_MINUTES`, если `in_stock = false` — см. "Отслеживание наличия"
      выше) же в этой транзакции — это и есть "захват": как только
      транзакция закоммитится, эти автоматизации больше не `next_check_at <= now()`, значит не
      будут выбраны повторно, даже до того как для них появится `pending_task_id`. Транзакция
      коммитится немедленно, до создания задач.
   2. Для каждой захваченной автоматизации — `TaskService.create_task(..., automation_id=
      automation.id)`, вне какой-либо открытой транзакции `AutomationRepository`.
   3. `AutomationRepository.set_pending_task` — отдельная короткая транзакция на каждую пару
      (автоматизация, задача), проставляет `pending_task_id`.

   Если процесс упадёт между фазой 1 и 3 — автоматизация останется без `pending_task_id`, но с уже
   сдвинутым `next_check_at`; она не зависнет навсегда, а просто пропустит одну проверку и попадёт
   в дальнейший обычный цикл на следующий `next_check_at`.
2. `apps/worker_parser` берёт и обрабатывает эту задачу как обычную `PRODUCT_PAGE`-задачу — без
   изменений в воркере.
3. **`AUTOMATION_RESULT_SWEEP`** (`AutomationService.process_pending_results` →
   `_finalize_check`) — раз в `config.AUTOMATION.RESULT_SWEEP_INTERVAL_SECONDS`: находит
   автоматизации с `pending_task_id IS NOT NULL`, чья задача дошла до терминального статуса.
   **Пишет ровно одну строку `AutomationCheckLog` на каждый такой тик, независимо от исхода**
   (раньше — только при успехе с реальным изменением):
   - `SUCCEEDED` с результатом — строит снимок всех восьми полей (`_build_snapshot`), сравнивает
     его со снимком предыдущего успешного тика (`has_changes`/`changes`) и с baseline
     (`threshold_breached`/`baseline_updates`) единым проходом
     (`_diff_against_previous_and_baseline`).
   - `SUCCEEDED` без результата (нет строки в `packages/result`) — трактуется как провал тика,
     `error_message='check_task_no_result'`.
   - `FAILED`/`EXPIRED`/`CANCELLED` — `succeeded=False`, `error_message=f'check_task_
     {status.lower()}'` (это ошибка **конкретной проверки**, не самой автоматизации, см. корневой
     `AGENTS.md`, "Правила по ошибкам"); та же причина дублируется в `Automation.last_check_error`.

   В обоих случаях — `pending_task_id` очищается (`AutomationRepository.finalize_check`, сырой
   `UPDATE`, так как `BaseRepository.update` не умеет обнулять поле через `exclude_none=True`).
   Если `has_changes or threshold_breached` — `_finalize_check` **не зовёт** `notify()` сам, а
   возвращает готовый набор `**kwargs` для него; `process_pending_results` копит эти наборы по
   всем автоматизациям батча и вызывает `notification_service.notify(event_code='automation.
   change_detected', payload={..., 'automation_link': ..., 'threshold_breached': ...},
   changed_fields=[c['field'] for c in changes])` для каждого только **после**
   `await self.transaction_manager.commit()` — то есть вне
   открытой транзакции, см. "Композиция сервисов и транзакции" ниже. Раньше `_finalize_check` звал
   `notify()` прямо из середины цикла внутри ещё не закоммиченной транзакции — если `_finalize_
   check` следующей автоматизации в том же батче падал с исключением, откатывались `AutomationCheckLog`
   и `finalize_check` уже обработанных автоматизаций этого батча, а их `NotificationDelivery`
   (записанная отдельной, уже закоммиченной транзакцией `NotificationService`) — нет: уведомление
   уходило про тик, которого по данным БД не существует, а на следующей развёртке та же
   автоматизация обрабатывалась заново (`pending_task_id` не очистился) и слала дубль.
   (единый `event_code` на оба случая — `threshold_breached` всегда подразумевает `has_changes`,
   получатель различает их по `payload`/по фильтру полей в своей подписке). `automation_link` —
   ссылка на страницу автоматизации в веб-интерфейсе (`{config.REST.FRONTEND_BASE_URL}
   /automations/{automation_id}`, `AutomationService.frontend_base_url`, см.
   [`packages/notifications/AGENTS.md`](../notifications/AGENTS.md#базовый-url-фронтенда)); `None`,
   если `FRONTEND_BASE_URL` не задан. См. [`packages/notifications/AGENTS.md`](../notifications/AGENTS.md).
4. **`AUTOMATION_HISTORY_RETENTION_SWEEP`** (`AutomationService.sweep_history_retention`) — раз в
   `config.AUTOMATION.HISTORY_RETENTION_SWEEP_INTERVAL_SECONDS`: удаляет строки
   `automation_check_log` старше `history_retention_days` **своей** автоматизации — один
   `DELETE ... USING automations` запрос на все автоматизации сразу
   (`AutomationCheckLogRepository.delete_expired`), не цикл в Python.

## `Task.automation_id` — скрытие проверочных задач от обычного списка задач

`packages/task`: `Task` получил `automation_id: UUID | None` (FK на `automations.id`,
`ON DELETE SET NULL`) — проставляется один раз при создании в `dispatch_due_checks` и **не
обнуляется** после обработки, в отличие от `Automation.pending_task_id` (тот обнуляется, когда
проверка завершена, — это единственная причина, по которой понадобилась отдельная постоянная
колонка: иначе после первой же завершённой проверки было бы невозможно понять, что эта задача
вообще создана автоматизацией, а не пользователем).

`TaskRepository.get_by_user_id`/`count_by_user_id` (и `TaskService.list_tasks` поверх них) по
умолчанию (`include_automation_tasks=False`) добавляют `WHERE automation_id IS NULL` — обычный
`GET /api/tasks/`, которым пользуется фронтенд, ничего не меняет в контракте и просто больше не
показывает проверочные задачи автоматизаций.

### Deadlock между `tasks.automation_id` и `claim_due_for_dispatch`

`automations`↔`tasks` — двусторонняя связь: `automations.pending_task_id → tasks.id` (уже была) и
теперь `tasks.automation_id → automations.id` (эта колонка). Если в одной и той же транзакции
захватить строку `automations` через `FOR UPDATE SKIP LOCKED` (как раньше делал
`get_due_for_dispatch`), а затем — **не закоммитив** — в другой сессии (`task_service`, у него свой
`AsyncTransactionManager`/своя сессия, см. "Композиция сервисов" ниже) выполнить `INSERT INTO
tasks (..., automation_id) VALUES (...)`, эта вторая сессия заблокируется: Postgres обязан
проверить FK `tasks.automation_id → automations.id`, для чего ему нужно взять `FOR KEY SHARE` на
ту самую строку `automations`, а она уже заблокирована первой (незакоммиченной) транзакцией — та
же строка не может быть заблокирована другой транзакцией параллельно. Первая транзакция не
коммитится, потому что сама ждёт результата `INSERT`а — классический deadlock между двумя
сессиями (проверено на реальной БД: `pg_stat_activity` показывал одну сессию `idle in transaction`
на `SELECT ... FOR UPDATE`, вторую — `active`/`Lock: transactionid` на этом самом `INSERT`).

Поэтому `dispatch_due_checks` обязан коммитить транзакцию `AutomationRepository` сразу после
`claim_due_for_dispatch`, до любого вызова `task_service.create_task` — см. флоу выше.

## Композиция сервисов и транзакции

`AutomationService` не открывает вложенные `async with self.transaction_manager(...)` блоки —
`AsyncTransactionManager` держит состояние (`session`, флаги репозиториев) на самом себе, и второй
вызов `self.transaction_manager(...)` поверх уже открытого того же инстанса подменяет его сессию у же
внутри блока. Поэтому каждый метод открывает ровно один блок со всеми нужными ему флагами репозиториев
сразу (как `TaskService.list_tasks` с `use_task_repository`+`use_task_item_repository`). Вызовы
`self.task_service.*`/`self.result_service.*`/`self.notification_service.notify(...)` внутри такого
блока безопасны — это отдельные инстансы `TaskService`/`ResultService`/`NotificationService` со
своим `AsyncTransactionManager` (DI-контейнер резолвит `transaction_manager`-провайдер как
`Factory` заново для каждого сервиса, см. `apps/api/src/container.py`), то есть отдельная
транзакция/сессия, не вложенная в транзакцию `AutomationService`.

## REST

`apps/api/src/routers/automation/` — `POST /api/automations/`, `GET /api/automations/`,
`GET /api/automations/with-history`, `GET /api/automations/{id}`,
`PATCH /api/automations/{id}/baseline`, `POST /api/automations/{id}/pause`,
`POST /api/automations/{id}/resume`, `DELETE /api/automations/{id}`,
`GET /api/automations/{id}/history` — все владелец-only (`ObjectNotFoundError` при
чужой/несуществующей автоматизации, как в `packages/task`).

`GET /` и `GET /with-history` принимают опциональный период `date_from`/`date_to` (включительно, по
`Automation.created_at`) — `list_automations`/`list_automations_with_recent_checks` →
`AutomationRepository.get_by_user_id`/`count_by_user_id`, общие фильтры в `_apply_user_filters`.

`GET /api/automations/{id}` (`AutomationDetailResponse` — расширяет `AutomationResponse`
единственным полем `last_info`) — снимок всех восьми `TRACKED_FIELDS` на момент **последней
успешной** проверки (`AutomationCheckLogRepository.get_latest_succeeded(automation_id).snapshot`,
`None` — ни одна проверка ещё не завершилась успехом), в дополнение к скалярным
`in_stock`/`baseline_*` полям самой `Automation`. Больше нигде не отдаётся — остальные ручки,
возвращающие `AutomationResponse` (`create`/`list`/`pause`/`resume`/`update_baseline`), не делают
лишний запрос ради поля, которое там не нужно; за снимками *истории* тиков — `GET /with-history`
(`snapshot` на каждом из последних 5 тиков) или `GET /{id}/history` (без `snapshot`, см. выше).

`GET /api/automations/with-history` (`AutomationService.list_automations_with_recent_checks`) —
та же страница, что `GET /api/automations/`, но каждая автоматизация приходит с последними
`RECENT_CHECKS_LIMIT` (5) строками `AutomationCheckLog`, новые сначала, **включая `snapshot`**
(`AutomationRecentCheckResponse` в `apps/api/src/routers/automation/schema.py` — расширяет
`AutomationHistoryResponse` этим единственным полем; `GET /api/automations/{id}/history` snapshot
по-прежнему не отдаёт). Реализовано без N+1:
`AutomationCheckLogRepository.get_recent_by_automation_ids` берёт последние 5 тиков сразу для всех
автоматизаций страницы одним запросом (`ROW_NUMBER() OVER (PARTITION BY automation_id ORDER BY
checked_at DESC)`, `WHERE rn <= 5`), а не по отдельному запросу на автоматизацию. Роутер регистрирует
`GET /with-history` **до** `GET /{automation_id}` — иначе Starlette сопоставил бы `with-history` с
динамическим `{automation_id}` (структурное совпадение "один сегмент пути") раньше, чем со
статическим маршрутом, и отдавал бы `422` при попытке провалидировать `"with-history"` как `UUID`.

## Не входит в эту итерацию

- Реальная отправка уведомлений — не здесь, `packages/automation` только вызывает `notify
  ('automation.change_detected', ...)`; отправка в Telegram и перевод `PENDING → SENT/FAILED`
  реализованы в `packages/notifications` (`NotificationService.dispatch_pending`, см.
  [`packages/notifications/AGENTS.md`](../notifications/AGENTS.md)).
- Отслеживание изменений карточки сверх восьми уже перечисленных в `TRACKED_FIELDS` полей
  (например, описания, фото, характеристик). Если появится — добавить в `TRACKED_FIELDS`/
  `TrackedField` по тому же образцу, что `TITLE`/`RATING`/`REVIEW_COUNT`/`SELLER_NAME`.
- Квоты на количество активных автоматизаций по маркетплейсу — не реализованы в этой итерации
  (тарификация сейчас покрывает только кредиты, см. "Тарификация — `packages/billing`" ниже).

## Тарификация — `packages/billing`

`AutomationService` инжектит `BillingService` (см. [`packages/billing/AGENTS.md`](../billing/AGENTS.md)
за полным контрактом) — тарифов/подписок нет, единая кредитная система на всех пользователей:

- **`create_automation`** — сначала проверяет `billing_service.has_positive_balance(user_id)`
  (иначе `InsufficientCreditsError`, REST — `402`), после успешного создания зовёт
  `charge(action_code='automation.create', ...)` (no-op, пока `base_cost=0`).
- **`dispatch_due_checks`** — для каждой захваченной (`claim_due_for_dispatch`, `next_check_at` уже
  сдвинут) автоматизации проверяет баланс её владельца **до** создания проверочной задачи. При
  `<= 0` — задача этого цикла не создаётся, `Automation.last_check_error = 'insufficient_credits'`
  через `AutomationRepository.finalize_check` (без сброса `next_check_at` — автоматизация тихо
  пропускает эту проверку и снова попадёт в выборку на своём обычном `next_check_at`, не раньше и
  не через отдельный retry-механизм). При положительном балансе — `task_service.create_task(...,
  pricing_dimension_code='automation_check_frequency', pricing_dimension_value=
  automation.check_frequency_minutes)`: проверочная задача несёт снэпшот текущей
  `check_frequency_minutes` на момент диспатча, а не живую ссылку — `packages/task` тарифицирует
  результаты этой задачи по этому снэпшоту, не обращаясь к `packages/automation` (см.
  [`packages/task/AGENTS.md`](../task/AGENTS.md), "Тарификация").
- Фактическое списание за результат проверки (1 `PRODUCT_PAGE` = 1 результат) происходит не здесь,
  а в `TaskService.record_item_progress`, когда воркер сохраняет результат этой проверочной
  задачи — `AutomationService` только проставляет измерение множителя, сам расчёт и списание вне
  этого домена.
