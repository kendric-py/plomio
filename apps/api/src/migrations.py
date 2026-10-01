import logging
from pathlib import Path

from alembic import command
from alembic.config import Config as AlembicConfig

logger = logging.getLogger(__name__)

# apps/api/src/migrations.py -> корень репозитория (там лежат alembic.ini и alembic/).
ALEMBIC_INI = Path(__file__).resolve().parents[3] / 'alembic.ini'


def upgrade_to_head() -> None:
    """Накатывает миграции до head. Ошибка логируется, но не валит запуск API.

    Вызывается синхронно до старта uvicorn: `alembic/env.py` сам поднимает event loop
    (`asyncio.run`), поэтому из работающего loop (lifespan) его вызывать нельзя.
    """
    try:
        logger.info('Applying database migrations (alembic upgrade head)')
        command.upgrade(AlembicConfig(str(ALEMBIC_INI)), 'head')
        logger.info('Database migrations are up to date')
    except Exception:
        logger.exception('Database migration failed; API starts without applying migrations')
