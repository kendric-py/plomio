# SMPCrawl

SMPCrawl — проект для парсинга данных с маркетплейсов.

Описание архитектуры и доменных правил живёт в [AGENTS.md](./AGENTS.md) и в `docs/reference/`.
Секреты хранятся в `.env` (файл в `.gitignore`), а шаблоны с безопасными значениями — в `.env.example`
(есть корневой `.env.example`, и по одному на каждое приложение в `apps/*/.env.example`).

## Как это работает

Клиент ставит задачу (единоразовую или периодическую, например мониторинг цены) через фронтенд или API.
`apps/api` создаёт задачу и кладёт её в очередь, реализованную поверх таблиц PostgreSQL. Для периодических
задач планировщик (scheduler) регулярно ставит их в очередь заново. `apps/worker_parser` забирает задачу
из очереди, запрашивает у `apps/worker_sessions` сессию (куки, заголовки, прокси) и выполняет парсинг
OZON/Wildberries, периодически отправляя HTTP heartbeat со своим статусом. Результат сохраняется в
PostgreSQL: для единоразовых задач — на 7 дней, для периодических — на срок, заданный администратором.

Подробности — в [`AGENTS.md`](./AGENTS.md) и [`docs/reference/architecture.md`](./docs/reference/architecture.md).

## Список доступных приложений и их назначение

Монорепозиторий собран через Poetry workspaces (см. корневой `Makefile` и `pyproject.toml`).
Общий код лежит в `src/shared`, переиспользуемые доменные пакеты — в `packages/`.

| Приложение | Назначение |
| --- | --- |
| [`apps/api`](./apps/api) | REST API на FastAPI. Постановка задач, отдача результатов, доступ для клиентов, администраторов и внешних интеграций. |
| [`apps/worker_parser`](./apps/worker_parser) | Забирает задачи из очереди и парсит OZON и Wildberries, используя сессии от `worker_sessions`. Отправляет HTTP heartbeat со своим статусом. |
| [`apps/worker_sessions`](./apps/worker_sessions) | Генерирует сессии (куки, заголовки, данные о прокси), которые использует `worker_parser` для работы с маркетплейсами. |

Подробное описание каждого приложения — в его собственном `AGENTS.md` (`apps/<app>/AGENTS.md`), которые пока не заполнены.

Пакеты:

| Пакет | Назначение |
| --- | --- |
| [`packages/user`](./packages/user) | Доменные модели пользователя сервиса SMPCrawl (клиент с доступом через фронтенд/API, администратор с доступом к тарифам). |

## Документы и их назначение

| Документ | Назначение |
| --- | --- |
| [`AGENTS.md`](./AGENTS.md) | Обзор архитектуры и доменных правил проекта, с ссылками на файлы ниже. |
| `apps/*/AGENTS.md` | Архитектура и доменные правила конкретного приложения (пока не заполнены). |
| [`docs/reference/architecture.md`](./docs/reference/architecture.md) | Поток данных, очередь задач, heartbeat, хранение данных, роли. |
| [`docs/reference/backend.md`](./docs/reference/backend.md) | Стек, приложения, пакеты бекенда. |
| [`docs/reference/frontend.md`](./docs/reference/frontend.md) | Правила фронтенда (пока не заполнен — приложения ещё нет в репозитории). |
| [`docs/reference/gold-rules.md`](./docs/reference/gold-rules.md) | Обязательные практики разработки (пока не заполнен). |
| [`docs/reference/anti-patterns.md`](./docs/reference/anti-patterns.md) | Что запрещено делать в коде (вложенные функции, импорты внутри функций, циклические импорты, сокращённые имена, позиционные аргументы). |
| [`docs/reference/agent-documentation.md`](./docs/reference/agent-documentation.md) | Правило: при разработке нового функционала агент обязан создавать/дополнять документацию. |
| `.env.example` (корневой и в каждом `apps/*`) | Шаблон переменных окружения с безопасными значениями по умолчанию. |
| `Makefile` | Команды установки зависимостей и запуска приложений (`install-*`, `run-*`, `lock-*`). |

## Как начать работу с проектом

Формат: **хочу сделать это → читай это**.

- **Хочу понять архитектуру проекта и доменные правила**
  → [`AGENTS.md`](./AGENTS.md) и [`docs/reference/`](./docs/reference).

- **Хочу разобраться в конкретном приложении**
  → `AGENTS.md` этого приложения, например [`apps/api/AGENTS.md`](./apps/api/AGENTS.md) (пока не заполнены).

- **Хочу настроить переменные окружения**
  → скопировать соответствующий `.env.example` в `.env` и заполнить значения. Никогда не коммитить `.env`.

- **Хочу установить/запустить проект**
  → см. раздел [Запуск и взаимодействие с проектом](#запуск-и-взаимодействие-с-проектом).

## Запуск и взаимодействие с проектом

Установка и запуск идут через `Makefile` (см. [`Makefile`](./Makefile)) и Poetry.

Установка зависимостей:

```sh
make install-all      # все приложения + shared-код
make install-shared    # только shared-код
make install-<app>     # конкретное приложение, например make install-api
```

Запуск приложений:

```sh
make run-api               # apps/api
make run-worker_parser     # apps/worker_parser
make run-worker_sessions   # apps/worker_sessions
```

Перед запуском каждого приложения нужно скопировать его `.env.example` в `.env` и заполнить значения:

- [`apps/api/.env.example`](./apps/api/.env.example) → `apps/api/.env`
- [`apps/worker_parser/.env.example`](./apps/worker_parser/.env.example) → `apps/worker_parser/.env`
- [`apps/worker_sessions/.env.example`](./apps/worker_sessions/.env.example) → `apps/worker_sessions/.env`

> TODO: добавить инструкции по запуску через Docker (есть `Dockerfile` в каждом `apps/*`), по накатке миграций БД,
> по локальному запуску тестов и по тому, как приложения взаимодействуют друг с другом в рантайме, когда эти процессы появятся/будут описаны.
