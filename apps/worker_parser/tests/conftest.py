import json
from pathlib import Path
from typing import Any

import pytest

FIXTURES_DIR = Path(__file__).parent / 'fixtures'


@pytest.fixture
def load_fixture():
    """Фикстуры — реальные ответы маркетплейсов, записанные через живую сессию; в файле лежат
    `url`/`params` запроса и `body` — сам ответ."""

    def _load(name: str) -> dict[str, Any]:
        return json.loads((FIXTURES_DIR / f'{name}.json').read_text(encoding='utf-8'))['body']

    return _load
