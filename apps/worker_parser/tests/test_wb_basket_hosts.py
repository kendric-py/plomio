from typing import Any

import pytest

from apps.worker_parser.src.exceptions import BlockedError, RequestError
from apps.worker_parser.src.marketplaces.wb import utils
from apps.worker_parser.src.marketplaces.wb.fetchers import _fetch_wb_card_json
from fakes import FakeResponse, make_session_message

# Реальный хост подставляется тестом через `real_host`; таблица для этого nm_id не важна.
NM_ID = 1812477873


@pytest.fixture(autouse=True)
def clean_learned_hosts():
    utils._WB_LEARNED_BASKET_HOSTS.clear()
    yield
    utils._WB_LEARNED_BASKET_HOSTS.clear()


class HostContext:
    """Отвечает 200 только на `real_host`, на остальных — 404 (или заданную ошибку)."""

    def __init__(self, real_host: str | None, error: Exception | None = None) -> None:
        self.real_host = real_host
        self.error = error
        self.session_message = make_session_message()
        self.hosts: list[str] = []

    async def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        host = url.split('/')[2]
        self.hosts.append(host)
        if self.error is not None:
            raise self.error
        if host != self.real_host:
            raise RequestError('HTTP 404', status_code=404, url=url)
        return FakeResponse({'nm_id': NM_ID})


def test_candidates_start_with_table_host_then_neighbours():
    primary = utils.get_wb_basket_host(NM_ID)
    candidates = utils.get_wb_basket_host_candidates(NM_ID)
    assert candidates[0] == primary
    assert len(candidates) == len(set(candidates))
    number = int(primary.split('.')[0].removeprefix('basket-'))
    assert utils._wb_basket_host_by_number(number + 1) in candidates


def test_remember_overrides_table_for_the_whole_vol():
    utils.remember_wb_basket_host(NM_ID, 'basket-99.wbbasket.ru')
    assert utils.get_wb_basket_host(NM_ID) == 'basket-99.wbbasket.ru'
    # Тот же vol (nm_id // 100000) — тот же хост, в том числе для фото.
    assert utils.get_wb_basket_host(NM_ID + 1) == 'basket-99.wbbasket.ru'


@pytest.mark.asyncio
async def test_falls_back_to_neighbour_basket_and_remembers_it():
    primary = utils.get_wb_basket_host(NM_ID)
    number = int(primary.split('.')[0].removeprefix('basket-'))
    real = utils._wb_basket_host_by_number(number + 2)
    context = HostContext(real_host=real)

    card = await _fetch_wb_card_json(NM_ID, 'https://www.wildberries.ru/x', context)

    assert card == {'nm_id': NM_ID}
    assert context.hosts[0] == primary
    assert context.hosts[-1] == real
    assert utils.get_wb_basket_host(NM_ID) == real

    # Второй запрос по тому же vol идёт сразу на запомненный хост.
    context = HostContext(real_host=real)
    await _fetch_wb_card_json(NM_ID, 'https://www.wildberries.ru/x', context)
    assert context.hosts == [real]


@pytest.mark.asyncio
async def test_404_on_every_host_raises_404():
    context = HostContext(real_host=None)
    with pytest.raises(RequestError) as error:
        await _fetch_wb_card_json(NM_ID, 'https://www.wildberries.ru/x', context)
    assert error.value.status_code == 404
    assert len(context.hosts) == len(utils.get_wb_basket_host_candidates(NM_ID))


@pytest.mark.asyncio
async def test_non_404_error_is_not_swallowed_by_probing():
    blocked = BlockedError('blocked', status_code=498, url='u', content_type='', response_body='')
    context = HostContext(real_host=None, error=blocked)
    with pytest.raises(BlockedError):
        await _fetch_wb_card_json(NM_ID, 'https://www.wildberries.ru/x', context)
    assert len(context.hosts) == 1
