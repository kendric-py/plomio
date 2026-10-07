# Контекст сборки — КОРЕНЬ репозитория (приложения импортируют core/ и packages/):
#   docker build -f apps/worker_sessions/Dockerfile -t plomio-worker_sessions .
# Node для js_runtime (безбраузерная генерация сессий): берём готовый бинарник из официального образа.
FROM node:22-slim AS node

# Node для js_runtime (безбраузерная генерация сессий). npm нужен только на сборке: зависимости
# ставим здесь, в финальный образ едут бинарник node и готовый node_modules. Обе базы — Debian
# bookworm (glibc), поэтому prebuilt-бинарник @napi-rs/canvas подходит.
FROM node:22-slim AS js_runtime_deps
WORKDIR /js_runtime
COPY apps/worker_sessions/js_runtime/package.json apps/worker_sessions/js_runtime/package-lock.json ./
RUN npm ci --omit=dev

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1     PYTHONDONTWRITEBYTECODE=1     PYTHONPATH=/app     POETRY_VERSION=1.8.3     POETRY_VIRTUALENVS_CREATE=false     POETRY_NO_INTERACTION=1

RUN pip install --no-cache-dir "poetry==$POETRY_VERSION"

WORKDIR /app

COPY apps/worker_sessions/pyproject.toml apps/worker_sessions/poetry.lock ./
RUN poetry install --no-root --only main

# Системные библиотеки Firefox + бинарник Camoufox (headless-браузер для генерации сессий)
RUN python -m playwright install-deps firefox     && python -m camoufox fetch     && rm -rf /var/lib/apt/lists/*

COPY --from=js_runtime_deps /usr/local/bin/node /usr/local/bin/node
COPY --from=js_runtime_deps /js_runtime/node_modules ./apps/worker_sessions/js_runtime/node_modules
COPY apps/worker_sessions/js_runtime/package.json ./apps/worker_sessions/js_runtime/package.json
COPY apps/worker_sessions/js_runtime/ready ./apps/worker_sessions/js_runtime/ready
# Кэши challenge-скриптов и временные файлы js_runtime пишутся сюда, а не в код.
ENV JS_RUNTIME_CACHE_DIR=/tmp/js_runtime

COPY core ./core
COPY packages ./packages
COPY apps/worker_sessions/src ./apps/worker_sessions/src

CMD ["python", "-m", "apps.worker_sessions.src"]
