from packages.notifications.src.entities import NotificationTemplateVariableEntity

# {event_code: {variable: NotificationTemplateVariableEntity}} — которая "{name}" пользовательский
# шаблон может использовать для каждого события, и что она значит/на что гейтит. Код-owned, не
# таблица БД: новая переменная не может появиться без правки кода домена, который кладёт её в
# payload (packages/automation, packages/task) — в отличие от event_code/description/is_active/
# available_fields (остаются в notification_events, редактируемых независимо от кода). Хранение в
# коде означает, что добавление/переименование/переописание переменной — обычная правка кода +
# деплой, не миграция данных — см. packages/notifications/AGENTS.md,
# "Пользовательские шаблоны сообщений".

# {field}_old/{field}_new на каждое отслеживаемое поле automation.change_detected — описываются
# один раз здесь (имя, TrackedField, что значит, деньги ли это), а сами Entity на _old/_new
# генерируются ниже _tracked_field_variables(), чтобы не дублировать текст описания и is_money
# дважды на каждое поле.
_TRACKED_FIELDS: list[tuple[str, str, str, bool]] = [
    ('price', 'PRICE', 'Цена без скидки', True),
    ('discounted_price', 'DISCOUNTED_PRICE', 'Цена со скидкой', True),
    ('original_price', 'ORIGINAL_PRICE', 'Оригинальная цена', True),
    ('in_stock', 'IN_STOCK', 'Наличие товара', False),
    ('title', 'TITLE', 'Название товара', False),
    ('rating', 'RATING', 'Рейтинг товара', False),
    ('review_count', 'REVIEW_COUNT', 'Количество отзывов', False),
    ('seller_name', 'SELLER_NAME', 'Название продавца', False),
]


def _tracked_field_variables() -> dict[str, NotificationTemplateVariableEntity]:
    variables: dict[str, NotificationTemplateVariableEntity] = {}
    for name, field, description, is_money in _TRACKED_FIELDS:
        variables[f'{name}_old'] = NotificationTemplateVariableEntity(
            field=field, description=f'{description}(Старое)',
            is_money=is_money,
        )
        variables[f'{name}_new'] = NotificationTemplateVariableEntity(
            field=field, description=f'{description}(Новое)', is_money=is_money,
        )
    return variables


TEMPLATE_VARIABLES: dict[str, dict[str, NotificationTemplateVariableEntity]] = {
    'automation.change_detected': {
        'automation_id': NotificationTemplateVariableEntity(
            description='Идентификатор автоматизации',
        ),
        'product_name': NotificationTemplateVariableEntity(
            description='Название товара',
        ),
        'link': NotificationTemplateVariableEntity(description='Ссылка на карточку товара'),
        'automation_link': NotificationTemplateVariableEntity(
            description='Ссылка на страницу автоматизации в веб-интерфейсе',
        ),
        'changes_text': NotificationTemplateVariableEntity(
            description='Список всех изменившихся полей',
        ),
        **_tracked_field_variables(),
    },
    'task.completed': {
        'task_id': NotificationTemplateVariableEntity(
            description='Идентификатор завершённой задачи',
        ),
        'task_link': NotificationTemplateVariableEntity(
            description='Ссылка на страницу задачи в веб-интерфейсе',
        ),
        'result_count': NotificationTemplateVariableEntity(
            description='Количество собранных результатов',
        ),
    },
    'task.failed': {
        'task_id': NotificationTemplateVariableEntity(description='Идентификатор задачи'),
        'error_reason': NotificationTemplateVariableEntity(description='Причина ошибки задачи'),
        'task_link': NotificationTemplateVariableEntity(
            description='Ссылка на страницу задачи в веб-интерфейсе',
        ),
        'result_count': NotificationTemplateVariableEntity(
            description='Количество собранных результатов',
        ),
    },
}


def get_template_variables(event_code: str) -> dict[str, NotificationTemplateVariableEntity]:
    return TEMPLATE_VARIABLES.get(event_code, {})


def get_money_fields() -> set[str]:
    """TrackedField names (the `field` column of `_TRACKED_FIELDS` above, e.g. `"PRICE"`) whose
    `_old`/`_new` template variables are money amounts — derived from the same `_TRACKED_FIELDS`
    list this module already maintains, so `packages/notifications/src/formatting.py::MONEY_FIELDS`
    doesn't hand-maintain a second, independently-editable copy of the same `is_money` flags."""

    return {field for _name, field, _description, is_money in _TRACKED_FIELDS if is_money}
