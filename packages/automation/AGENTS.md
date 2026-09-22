# packages/automation

Доменная область периодических задач-мониторинга цены (упоминалась как будущая работа в
[`packages/task/AGENTS.md`](../task/AGENTS.md) и в корневом [`AGENTS.md`](../../AGENTS.md), раздел
"Домен: задачи"). Пользователь регистрирует автоматизацию — ссылку/артикул товара, маркетплейс,
порог падения цены и периодичность — система периодически перепарсивает товар и фиксирует изменения
трёх цен в истории, для последующих графиков и (в будущем, отдельной работой) отправки уведомлений.

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
  `next_check_at`, `pending_task_id` (FK на `tasks.id`, `SET NULL`), `last_checked_at`,
  `last_check_error`, `user_id`.
- **`AutomationHistory`** (`automation_history`) — append-only лог зафиксированных изменений.
  **Одна строка = одна проверка**, а не одна строка на каждое изменившееся поле: `changes`
  (`JSONB`, список `{field, old_value, new_value, threshold_breached}` — по одному элементу на
  каждую из трёх цен, изменившуюся за эту проверку) и `threshold_breached` на самой строке —
  агрегат, `any(change['threshold_breached'] for change in changes)`, чтобы можно было отфильтровать
  "проверки, где хоть что-то пробило порог" без разбора JSONB. Нет отдельной колонки `change_type` —
  раз строка уже группирует все изменения одной проверки, тип на уровне строки был бы не нужен, пока
  отслеживается только цена (см. "Не входит в эту итерацию"). `id` — автоинкрементный `int`, не
  `UUID` (внутренняя запись, не публичный ресурс, как `cron_job_runs`), в отличие от `Automation.id`
  (`UUID`, публичный ресурс, как `Task.id`).

## Три отслеживаемые цены

`ProductPagePayload` (`packages/result/src/entities.py`) отдаёт три поля цены с карточки товара —
`price_kopecks` (без скидки), `discounted_price_kopecks` (со скидкой/по карте),
`original_price_kopecks` (перечёркнутая). Каждое поле имеет свою базовую цену на `Automation` и
проверяется независимо — `TRACKED_PRICE_FIELDS` в `service.py` единственное место, где перечислены
все три.

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
- `threshold_breached` на строке истории — `new_value <= baseline_value * (1 -
  price_drop_threshold_percent / 100)`, вычисляется относительно baseline на момент проверки, не
  относительно предыдущего значения истории.

В историю пишется **любое** изменение цены между проверками (не только просадка ниже baseline) — под
будущие графики; `threshold_breached` — отдельный флаг для будущей интеграции уведомлений (в этой
итерации без реальной отправки, см. "Не входит в эту итерацию").

## Флоу выполнения (три периодических job'а, `packages/cron` + `apps/api/src/jobs`)

1. **`AUTOMATION_DISPATCH`** (`AutomationService.dispatch_due_checks`) — раз в
   `config.AUTOMATION.DISPATCH_INTERVAL_SECONDS`, в три фазы (не одна транзакция — см.
   "Deadlock между `tasks.automation_id` и `claim_due_for_dispatch`" ниже, это не рефакторинг для
   красоты, а обязательный порядок):
   1. `AutomationRepository.claim_due_for_dispatch` — одной транзакцией атомарно находит
      `ACTIVE`-автоматизации с `next_check_at <= now()` и `pending_task_id IS NULL`
      (`FOR UPDATE SKIP LOCKED` — защита от повторного диспатча при нескольких репликах `apps/api`,
      как `TaskRepository.claim_next`) и сразу сдвигает им `next_check_at` на
      `check_frequency_minutes` вперёд же в этой транзакции — это и есть "захват": как только
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
3. **`AUTOMATION_RESULT_SWEEP`** (`AutomationService.process_pending_results`) — раз в
   `config.AUTOMATION.RESULT_SWEEP_INTERVAL_SECONDS`: находит автоматизации с `pending_task_id IS NOT
   NULL`, чья задача дошла до терминального статуса. При `SUCCEEDED` — читает результат через
   `ResultService.get_results_for_task`, сравнивает три цены с baseline (`_diff_prices`) и, если
   изменилось хотя бы одно поле, пишет **одну** строку `AutomationHistory` со всеми изменившимися
   полями сразу в `changes` (две одновременно изменившиеся цены — по-прежнему одна строка, не две).
   При `FAILED`/`EXPIRED`/`CANCELLED` — история не пишется (это ошибка **конкретной проверки**, не
   самой автоматизации, см. корневой `AGENTS.md`, "Правила по ошибкам"), причина сохраняется в
   `last_check_error`. В обоих случаях — `pending_task_id` очищается
   (`AutomationRepository.finalize_check`, сырой `UPDATE`, так как `BaseRepository.update` не умеет
   обнулять поле через `exclude_none=True`).
4. **`AUTOMATION_HISTORY_RETENTION_SWEEP`** (`AutomationService.sweep_history_retention`) — раз в
   `config.AUTOMATION.HISTORY_RETENTION_SWEEP_INTERVAL_SECONDS`: удаляет строки `automation_history`
   старше `history_retention_days` **своей** автоматизации — один `DELETE ... USING automations`
   запрос на все автоматизации сразу (`AutomationHistoryRepository.delete_expired`), не цикл в Python.

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
`self.task_service.*`/`self.result_service.*` внутри такого блока безопасны — это отдельные инстансы
`TaskService`/`ResultService` со своим `AsyncTransactionManager` (DI-контейнер резолвит
`transaction_manager`-провайдер как `Factory` заново для каждого сервиса, см.
`apps/api/src/container.py`), то есть отдельная транзакция/сессия, не вложенная в транзакцию
`AutomationService`.

## REST

`apps/api/src/routers/automation/` — `POST /api/automations/`, `GET /api/automations/`,
`GET /api/automations/{id}`, `PATCH /api/automations/{id}/baseline`,
`POST /api/automations/{id}/pause`, `POST /api/automations/{id}/resume`,
`DELETE /api/automations/{id}`, `GET /api/automations/{id}/history` — все владелец-only
(`ObjectNotFoundError` при чужой/несуществующей автоматизации, как в `packages/task`).

## Не входит в эту итерацию

- Реальная отправка уведомлений (Telegram и т.п.) при `threshold_breached = true` — только фиксация
  факта в БД. `User.telegram_id` (`packages/user`) уже предусмотрен под это в модели.
- Отслеживание изменений, отличных от цены (например, описания). Если появится — решить, входит ли
  такое изменение в ту же строку истории проверки (`changes` — общий список для любых типов) или
  нужен отдельный признак типа на элементе `changes` (сейчас там неявно только цена).
- Тарифные квоты на частоту/количество автоматизаций по пользователю — упоминаются в корневом
  `AGENTS.md` ("Домен: пользователи и тарифы") как будущая работа `packages/membership`.
