import asyncio
import logging

from apps.worker_sessions.src.pool_manager import run_pool_manager

if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s',
    )
    asyncio.run(run_pool_manager())
