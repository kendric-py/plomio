import redis.asyncio as redis

from core.configs import RedisConfig


def get_redis_client(config: RedisConfig) -> redis.Redis:
    return redis.Redis(host=config.HOST, port=config.PORT, db=config.DB, password=config.PASSWORD)
