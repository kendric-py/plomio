# Контекст сборки — КОРЕНЬ репозитория (приложения импортируют core/ и packages/):
#   docker build -f apps/worker_parser/Dockerfile -t plomio-worker_parser .
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1     PYTHONDONTWRITEBYTECODE=1     PYTHONPATH=/app     POETRY_VERSION=1.8.3     POETRY_VIRTUALENVS_CREATE=false     POETRY_NO_INTERACTION=1

RUN pip install --no-cache-dir "poetry==$POETRY_VERSION"

WORKDIR /app

COPY apps/worker_parser/pyproject.toml apps/worker_parser/poetry.lock ./
RUN poetry install --no-root --only main

COPY core ./core
COPY packages ./packages
COPY apps/worker_parser/src ./apps/worker_parser/src

CMD ["python", "-m", "apps.worker_parser.src"]
