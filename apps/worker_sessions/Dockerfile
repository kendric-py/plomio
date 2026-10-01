# Контекст сборки — КОРЕНЬ репозитория (приложения импортируют core/ и packages/):
#   docker build -f apps/worker_sessions/Dockerfile -t smpcrawl-worker_sessions .
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1     PYTHONDONTWRITEBYTECODE=1     PYTHONPATH=/app     POETRY_VERSION=1.8.3     POETRY_VIRTUALENVS_CREATE=false     POETRY_NO_INTERACTION=1

RUN pip install --no-cache-dir "poetry==$POETRY_VERSION"

WORKDIR /app

COPY apps/worker_sessions/pyproject.toml apps/worker_sessions/poetry.lock ./
RUN poetry install --no-root --only main

# Системные библиотеки Firefox + бинарник Camoufox (headless-браузер для генерации сессий)
RUN python -m playwright install-deps firefox     && python -m camoufox fetch     && rm -rf /var/lib/apt/lists/*

COPY core ./core
COPY packages ./packages
COPY apps/worker_sessions/src ./apps/worker_sessions/src

CMD ["python", "-m", "apps.worker_sessions.src"]
