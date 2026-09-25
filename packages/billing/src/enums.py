from enum import Enum


class ReferenceType(str, Enum):
    """Тип сущности, породившей списание/начисление — для трассировки в `CreditTransaction`."""

    TASK = 'task'
    AUTOMATION = 'automation'


class PricingDimension(str, Enum):
    """Известные на сегодня измерения `PricingMultiplierRule.dimension_code`. Не исчерпывающий
    список — новое измерение подключается новыми строками в `pricing_multiplier_rules` и одной
    точкой кода, которая передаёт его значение в `BillingService.charge`, без добавления сюда
    нового элемента. Здесь — только чтобы `packages/task`/`packages/automation` не дублировали эти
    строки буквально."""

    TASK_PRIORITY = 'task_priority'
    AUTOMATION_CHECK_FREQUENCY = 'automation_check_frequency'
