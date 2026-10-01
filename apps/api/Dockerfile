# Контекст сборки — КОРЕНЬ репозитория (приложения импортируют core/ и packages/):
#   docker build -f apps/api/Dockerfile -t plomio-api .
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1     PYTHONDONTWRITEBYTECODE=1     PYTHONPATH=/app     POETRY_VERSION=1.8.3     POETRY_VIRTUALENVS_CREATE=false     POETRY_NO_INTERACTION=1

RUN pip install --no-cache-dir "poetry==$POETRY_VERSION"

WORKDIR /app

COPY apps/api/pyproject.toml apps/api/poetry.lock ./
RUN poetry install --no-root --only main

COPY core ./core
COPY packages ./packages
COPY alembic.ini ./
COPY alembic ./alembic
COPY apps/api/src ./apps/api/src

EXPOSE 8000

CMD ["python", "-m", "apps.api.src"]
