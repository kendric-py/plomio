import logging

import redis.asyncio as redis
from redis.exceptions import ResponseError

from core.configs import RedisConfig
from core.enums import Marketplace
from core.redis import get_redis_client
from packages.direct.src.entities import DirectReply, DirectRequest

logger = logging.getLogger(__name__)

REQUESTS_STREAM_MAXLEN = 1000
REPLY_TTL_SECONDS = 30
CONSUMER_GROUP = 'direct-workers'
_DATA_FIELD = b'data'


def _requests_stream(marketplace: Marketplace) -> str:
    return f'direct:requests:{marketplace.value}'


def _reply_key(request_id: str) -> str:
    return f'direct:reply:{request_id}'


class DirectBus:
    """Транспорт direct-запросов поверх Redis: запросы — Stream с consumer group, ответы —
    список на каждый `request_id`. Семантика at-most-once: сообщение снимается со стрима сразу
    при чтении (`XACK`+`XDEL`), поэтому упавший воркер значит таймаут у клиента, а не повторную
    обработку — ретраи транспорта не нужны, ответ всё равно имеет срок годности."""

    def __init__(self, redis_config: RedisConfig) -> None:
        self._client: redis.Redis = get_redis_client(redis_config)

    async def enqueue(self, request: DirectRequest) -> None:
        await self._client.xadd(
            _requests_stream(request.marketplace),
            {_DATA_FIELD: request.model_dump_json()},
            maxlen=REQUESTS_STREAM_MAXLEN,
            approximate=True,
        )

    async def wait_reply(self, request_id: str, timeout_seconds: float) -> DirectReply | None:
        popped = await self._client.blpop([_reply_key(request_id)], timeout=timeout_seconds)
        if popped is None:
            return None
        return DirectReply.model_validate_json(popped[1])

    async def publish_reply(self, reply: DirectReply) -> None:
        key = _reply_key(reply.request_id)
        async with self._client.pipeline(transaction=True) as pipeline:
            pipeline.rpush(key, reply.model_dump_json())
            pipeline.expire(key, REPLY_TTL_SECONDS)
            await pipeline.execute()

    async def ensure_groups(self, marketplaces: list[Marketplace]) -> None:
        for marketplace in marketplaces:
            try:
                await self._client.xgroup_create(
                    _requests_stream(marketplace), CONSUMER_GROUP, id='0', mkstream=True,
                )
            except ResponseError as error:
                if 'BUSYGROUP' not in str(error):
                    raise

    async def consume(
        self,
        marketplaces: list[Marketplace],
        consumer_name: str,
        count: int,
        block_ms: int,
    ) -> list[DirectRequest]:
        streams = {_requests_stream(marketplace): '>' for marketplace in marketplaces}
        response = await self._client.xreadgroup(
            CONSUMER_GROUP, consumer_name, streams, count=count, block=block_ms,
        )
        requests: list[DirectRequest] = []
        for stream_name, messages in response or []:
            message_ids = [message_id for message_id, _ in messages]
            await self._ack_and_delete(stream_name, message_ids)
            for message_id, fields in messages:
                request = self._parse_request(message_id, fields)
                if request is not None:
                    requests.append(request)
        return requests

    async def close(self) -> None:
        await self._client.aclose()

    async def _ack_and_delete(self, stream_name: bytes | str, message_ids: list) -> None:
        async with self._client.pipeline(transaction=True) as pipeline:
            pipeline.xack(stream_name, CONSUMER_GROUP, *message_ids)
            pipeline.xdel(stream_name, *message_ids)
            await pipeline.execute()

    @staticmethod
    def _parse_request(message_id: bytes | str, fields: dict) -> DirectRequest | None:
        try:
            return DirectRequest.model_validate_json(fields[_DATA_FIELD])
        except (KeyError, ValueError):
            logger.exception('[direct_bad_message] message_id=%s', message_id)
            return None
