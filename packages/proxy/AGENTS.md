# packages/proxy

Доменная область пула прокси. Админ ведёт список прокси (создание, правка, список, удаление), а
`worker_sessions` получает из него **случайный активный** прокси для генерации сессий — см.
[`apps/worker_sessions/AGENTS.md`](../../apps/worker_sessions/AGENTS.md), "Прокси".

## Модель

`Proxy` (`proxies`): `proxy_type` (`ProxyType`: `http` / `socks5`, в БД — native enum, хранит
*имена* членов: `HTTP`, `SOCKS5`), `host`, `port`, `username`/`password` (nullable — прокси без
авторизации), `is_active` (участвует ли в выдаче; по умолчанию `true`), `note` (заметка админа),
`created_at`/`updated_at`.

Уникальность — `(proxy_type, host, port, username)` с `NULLS NOT DISTINCT` (Postgres 15+): два
прокси без логина с одним адресом тоже дубль. Нарушение → `DuplicatedObjectError` → `409`.

Пароль хранится открытым текстом: воркеру он нужен как есть, хэшировать нельзя. Поэтому админские
ответы **никогда** не возвращают пароль — только `has_password` (см. ниже), а сам пароль уходит
наружу единственной ручкой `GET /api/proxy/issue`, закрытой токеном воркера.

## Сервис (`ProxyService`)

- `list_page(limit, offset, is_active)` → `(items, total)`.
- `create_proxy(...)` — `DuplicatedObjectError` при дубле.
- `update_proxy(proxy_id, values)` — `values` это только реально переданные поля
  (`UpdateProxyRequest.changed_fields()`); `None` допустим и **сбрасывает** `username`/`password`/
  `note`. Поэтому используется `ProxyRepository.update_fields`, а не `BaseRepository.update`
  (тот отбрасывает `None`). `ObjectNotFoundError` / `DuplicatedObjectError` пробрасываются.
- `delete_proxy(proxy_id)` — `ObjectNotFoundError`, если нет такого.
- `issue_random(proxy_type=None)` — случайный активный прокси (`ORDER BY random() LIMIT 1`),
  опционально заданного типа; `None`, если подходящих нет. Пул маленький, равномерности выборки
  этого достаточно, отдельная схема выбора не нужна.

## Генерации сессий (`SessionGeneration`)

Таблица `session_generations`: **каждая** попытка генерации сессии, и успешная, и нет.
`proxy_id` (FK → `proxies`, `ON DELETE SET NULL`; пуст, если прокси не использовался — например,
нет прокси или локальный режим без него — либо прокси потом удалили), `marketplace`, `outcome`
(`packages.sessions.src.enums.SessionGenerationOutcome`: `success` / `antibot_init` / `validation` /
`proxy_unavailable` / `other`), `traceback` (оригинальная ошибка для анализа, nullable), `created_at`
(UTC). Пишет `worker_sessions` через api (`POST /api/proxy/generations`). Таблица служит двум целям:

- **Пул сессий.** Из последних 50 записей маркетплейса (`ProxyService.get_recent_generations`,
  индекс `(marketplace, created_at)`) считаются процент успеха и доли ошибок в
  `GET /api/sessions/pool` и в тексте алерта `system.sessions_depleted`. Раньше окно жило в Redis —
  Redis теперь хранит только сам пул сессий.
- **Статистика прокси.** По `proxy_id` (индекс `(proxy_id, created_at)`): сводка по итогам для
  круговой диаграммы и разбивка по дням (деталка прокси в админке).

История таблицы: `d5b9f2c81e47` создала `proxy_generation_failures` (только неудачи, `proxy_id`
обязателен); `e8c4a7d12f63` переименовала её в `session_generations`, добавила `SUCCESS` в enum и
сделала `proxy_id` необязательным (с `SET NULL` вместо `CASCADE`). Первая миграция к тому моменту уже
была в проде, поэтому вторая доращивает схему, а не переписывает первую.

**Антибот-ошибки.** `antibot_init` почти не зависит от прокси — скрипты антибота маркетплейса
меняются, и тогда падают все прокси разом. Поэтому они пишутся с `proxy_id` (для анализа и
`traceback`), но `ProxyService.get_generation_stats` по умолчанию их **исключает**
(`include_antibot=False`) — и из числителя, и из знаменателя долей: иначе исправный прокси выглядит
плохим из-за смены скрипта. Включаются флагом. Смену скриптов видно по `get_antibot_by_day` —
антибот-ошибки по дням по всем прокси (`GET /api/admin/proxies/antibot-timeline`): резкий рост =
сломался антибот-поток, а не прокси.

Сервис: `record_generation(marketplace, outcome, proxy_id=None, traceback=None)` (если прокси уже
удалён, пишет без него — генерация всё равно была), `get_recent_generations(marketplace)`,
`get_generation_stats(proxy_id, date_from, date_to, outcomes, include_antibot)` →
`(по итогам, по дням)` (`ObjectNotFoundError`, если прокси нет), `get_antibot_by_day(marketplace,
date_from, date_to)`, `sweep_generation_retention(retention_days)`. Хранение —
`PROXY_FAILURE_RETENTION_DAYS` (30 дней; имя осталось от первой версии, как и у cron-джоба), чистка
кроном `PROXY_FAILURE_RETENTION_SWEEP` (`apps/api/src/jobs/proxy_failure_retention_sweep.py`, интервал
`PROXY_FAILURE_RETENTION_SWEEP_INTERVAL_SECONDS`, по умолчанию час) — поэтому фильтр по дате в
деталке осмыслен в пределах 30 дней. Дни группируются в UTC.

Объём: одна строка на каждую попытку генерации (секунды между попытками у каждого воркера), за 30
дней это порядка сотен тысяч — миллионов строк; индексы и ежечасная чистка рассчитаны на это.

## REST

Роутер — `apps/api/src/routers/proxy`. Подробный контракт для фронтенда — в
[`docs/reference/frontend-api.md`](../../docs/reference/frontend-api.md), раздел `/api/admin/proxies`.

- Админ (`get_current_admin_user`): `GET`/`POST /api/admin/proxies/`, `GET`/`PATCH`/`DELETE
  /api/admin/proxies/{proxy_id}`, `GET /api/admin/proxies/{proxy_id}/generation-stats`
  (`outcomes` повторяющимся параметром, `include_antibot`, `date_from`/`date_to`; ответ —
  `total`, `success_percent`, `by_outcome[]` с долями для круговой диаграммы, `by_day[]`), `GET
  /api/admin/proxies/antibot-timeline` (регистрируется до `/{proxy_id}`).
- Воркер (`X-Worker-Token`): `POST /api/proxy/generations` (`204`) — итог попытки генерации, успех
  или ошибка; `proxy_id` в теле необязателен.
- Воркер: `GET /api/proxy/issue` — авторизация заголовком `X-Worker-Token`, сравнивается с
  `PROXY_WORKER_TOKEN` api (`secrets.compare_digest`). Пустой `PROXY_WORKER_TOKEN` — выдача
  выключена, ответ `503` (а не открытая всем ручка). Нет активных прокси — `404`, это ожидаемо
  обрабатывает `worker_sessions` (`proxy/client.py`: «прокси сейчас нет»).

Формат ответа `issue` — контракт с `worker_sessions`: `proxy_id`, `proxy_type`, `proxy_host`,
`proxy_port`, `proxy_username`, `proxy_password`. Менять поля нельзя без правки `get_proxy()` воркера.

## Что не сделано

- Audit-лог правок прокси не пишется (остальные админские CRUD, кроме начисления кредитов, тоже не
  аудируются).
- Нет проверки работоспособности прокси и автоматического отключения неживых — `is_active`
  переключает админ вручную.
- Выдача не учитывает нагрузку на конкретный прокси: `GENERATION_MAX_SESSIONS_PER_PROXY` ограничивает
  только то, сколько сессий подряд воркер генерирует через уже выданный прокси.
