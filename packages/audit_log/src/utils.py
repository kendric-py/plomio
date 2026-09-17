from typing import Any

from pydantic import BaseModel

SENSITIVE_FIELD_MARKERS = ('password', 'token', 'secret', 'hashed_')


def _is_sensitive(field_name: str) -> bool:
    lowered = field_name.lower()
    return any(marker in lowered for marker in SENSITIVE_FIELD_MARKERS)


def build_create_fields(entity: BaseModel) -> dict[str, dict[str, Any]]:
    """Снапшот всех полей новой сущности: {field: {before: None, after: value}}."""
    data = entity.model_dump(mode='json', exclude_none=True)
    return {
        name: {'before': None, 'after': value}
        for name, value in data.items()
        if not _is_sensitive(name)
    }


def build_delete_fields(entity: BaseModel) -> dict[str, dict[str, Any]]:
    """Снапшот удаляемой сущности: {field: {before: value, after: None}}."""
    data = entity.model_dump(mode='json', exclude_none=True)
    return {
        name: {'before': value, 'after': None}
        for name, value in data.items()
        if not _is_sensitive(name)
    }


def build_update_fields(before: BaseModel, patch: BaseModel) -> dict[str, dict[str, Any]]:
    """Диффует только реально изменившиеся поля patch относительно before.

    `patch` — объект с полями, которые сервис намеревался изменить (обычно
    тот же entity, что передаётся в `BaseRepository.update`). Значения,
    отсутствующие в `patch` (не заданные явно) или совпадающие со старыми,
    в результат не попадают.
    """
    changed = patch.model_dump(
        mode='json',
        exclude_unset=True,
        exclude_defaults=True,
        exclude_none=True,
    )
    before_data = before.model_dump(mode='json')
    fields: dict[str, dict[str, Any]] = {}
    for name, new_value in changed.items():
        if _is_sensitive(name):
            continue
        old_value = before_data.get(name)
        if old_value == new_value:
            continue
        fields[name] = {'before': old_value, 'after': new_value}
    return fields
