import time
import uuid

import pytest
import pytest_asyncio

from core.configs import RedisConfig
from core.enums import Marketplace
from core.redis import get_redis_client
from packages.direct.src.entities import DirectReply, DirectRequest
from packages.direct.src.enums import DirectRequestType, DirectStatus
from packages.direct.src.redis_bus import CONSUMER_GROUP, DirectBus

MARKETPLACE = Marketplace.WILDBERRIES
STREAM = f'direct:requests:{MARKETPLACE.value}'


def make_request(request_id: str | None = None) -> DirectRequest:
    now = time.time()
    return DirectRequest(
        request_id=request_id or uuid.uuid4().hex,
        request_type=DirectRequestType.PRODUCT_PAGE,
        marketplace=MARKETPLACE,
        input_value='123',
        created_at=now,
        deadline_at=now + 20,
    )


@pytest_asyncio.fixture
async def bus():
    """Интеграционный тест на живом Redis (localhost по умолчанию); стрим перед и после теста
    удаляется, поэтому не пересекается с реальными воркерами, только если они не запущены."""
    redis_config = RedisConfig()
    client = get_redis_client(redis_config)
    try:
        await client.ping()
    except Exception:
        pytest.skip('Redis недоступен')
    await client.delete(STREAM)
    direct_bus = DirectBus(redis_config=redis_config)
    await direct_bus.ensure_groups([MARKETPLACE])
    yield direct_bus
    await client.delete(STREAM)
    await direct_bus.close()
    await client.aclose()


@pytest.mark.asyncio
async def test_enqueue_consume_is_at_most_once(bus):
    request = make_request()
    await bus.enqueue(request)

    consumed = await bus.consume([MARKETPLACE], 'test-1', count=10, block_ms=200)
    assert [item.request_id for item in consumed] == [request.request_id]
    assert await bus.consume([MARKETPLACE], 'test-2', count=10, block_ms=100) == []

    client = get_redis_client(RedisConfig())
    assert await client.xlen(STREAM) == 0
    pending = await client.xpending(STREAM, CONSUMER_GROUP)
    assert pending['pending'] == 0
    await client.aclose()


@pytest.mark.asyncio
async def test_consume_respects_count(bus):
    for _ in range(3):
        await bus.enqueue(make_request())
    first = await bus.consume([MARKETPLACE], 'test-1', count=2, block_ms=200)
    second = await bus.consume([MARKETPLACE], 'test-1', count=2, block_ms=200)
    assert (len(first), len(second)) == (2, 1)


@pytest.mark.asyncio
async def test_reply_roundtrip_and_expiry_set(bus):
    reply = DirectReply(
        request_id='r-1', status=DirectStatus.OK, payload={'a': 1}, next_cursor={'p': 2},
    )
    await bus.publish_reply(reply)

    client = get_redis_client(RedisConfig())
    ttl = await client.ttl('direct:reply:r-1')
    assert 0 < ttl <= 30
    await client.aclose()

    received = await bus.wait_reply('r-1', timeout_seconds=1)
    assert received == reply


@pytest.mark.asyncio
async def test_wait_reply_times_out(bus):
    assert await bus.wait_reply('missing', timeout_seconds=0.2) is None


@pytest.mark.asyncio
async def test_ensure_groups_is_idempotent(bus):
    await bus.ensure_groups([MARKETPLACE])
