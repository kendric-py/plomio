import json
from typing import Any


def extract_ozon_next_page(payload: dict[str, Any]) -> str | None:
    if payload.get('nextPage'):
        return payload['nextPage']
    for key, raw in payload.get('widgetStates', {}).items():
        if 'Paginator' not in key and 'paginator' not in key:
            continue
        if not isinstance(raw, str):
            continue
        try:
            widget = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(widget, dict) and widget.get('nextPage'):
            return widget['nextPage']
    return None
