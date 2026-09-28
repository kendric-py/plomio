import re
from functools import partial
from html import escape as escape_html
from typing import TYPE_CHECKING, Callable

from packages.notifications.src.template_catalog import get_money_fields

if TYPE_CHECKING:
    from packages.notifications.src.entities import NotificationTemplateVariableEntity

# TrackedField names (packages/automation/src/enums.py) that hold KOPECKS amounts — derived from
# template_catalog.py's own _TRACKED_FIELDS (single source of truth for is_money within this
# package) rather than hand-maintained here a second time.
MONEY_FIELDS = get_money_fields()

# Matches "{name}" only — a bare identifier in curly braces, deliberately not the full
# str.format()/Jinja2 mini-language (no "{name.attr}", "{name[0]}", "{name!r}", "{name:spec}",
# no expressions). A user edits this text, and it only ever renders back to that same user's own
# Telegram chat — there's no cross-user injection surface either way — but a plain substitution
# grammar still means "extract every {name} in this string" (get_used_variables) is exact and
# needs no sandboxing, same reasoning as the string.Template design it replaces.
_VARIABLE_PATTERN = re.compile(r'\{(\w+)\}')


def get_used_variables(template: str) -> set[str]:
    """Every `{name}` referenced in a template — used both to validate a template against
    `NotificationEvent.template_variables` at save time and to derive which changed fields should
    gate sending it (see `NotificationService.notify`, "Пользовательские шаблоны сообщений" in
    AGENTS.md)."""

    return set(_VARIABLE_PATTERN.findall(template))


def format_money_kopecks(value) -> str:
    """Kopecks (as stored everywhere else in the API — see gold-rules) -> a human-readable rubles
    string, e.g. `150000` -> `"1 500,00 ₽"`. Integer arithmetic (`divmod`), not `value / 100` as a
    float — avoids float rounding artifacts on large kopecks amounts. `None` -> empty string, same
    convention as `_escape`."""

    if value is None:
        return ''
    sign = '-' if value < 0 else ''
    rubles, kopecks = divmod(abs(value), 100)
    return f"{sign}{f'{rubles:,}'.replace(',', ' ')},{kopecks:02d} ₽"


def _escape(value) -> str:
    """`None` -> empty string (not the literal text "None"); everything else -> HTML-escaped
    string. Every value that ends up in message text goes through this, never the raw value —
    bots are created with `parse_mode=HTML` as a bot-wide default (`telegram_client.py`/
    `telegram_polling.py`), so an un-escaped `<`/`&`/`>` from marketplace data (a product title,
    seller name, error message — none of it under our control) would either break Telegram's HTML
    parser (delivery ends up FAILED) or get silently interpreted as markup. Escaping happens here,
    not in the bot client, so it covers both the built-in formatters below and a user's own
    `{name}` template the same way."""

    return '' if value is None else escape_html(str(value))


def _substitute_variable(
    payload: dict,
    variable_info_map: 'dict[str, NotificationTemplateVariableEntity]',
    match: re.Match,
) -> str:
    """The `_VARIABLE_PATTERN.sub` callback for `render_template` — a top-level function (not
    nested — see `docs/reference/anti-patterns.md`, "Не писать функции внутри функций"), bound to
    a given `payload`/`variable_info_map` via `functools.partial` at each `render_template` call."""

    name = match.group(1)
    if name not in payload:
        return match.group(0)
    value = payload[name]
    variable_info = variable_info_map.get(name)
    if variable_info is not None and variable_info.is_money:
        return format_money_kopecks(value)
    if isinstance(value, bool):
        # A tracked BOOLEAN field (e.g. in_stock_old/in_stock_new) is a raw Python bool in the
        # payload — falling through to `_escape(str(value))` below would render the literal
        # "True"/"False" in a Russian-language Telegram message instead of a localized value.
        return 'Да' if value else 'Нет'
    return _escape(value)


def render_template(
    template: str,
    payload: dict,
    template_variables: 'dict[str, NotificationTemplateVariableEntity] | None' = None,
) -> str:
    """Substitutes every `{name}` with `payload[name]` (HTML-escaped — see `_escape` — unless
    `template_variables[name].is_money`, in which case it's rendered via `format_money_kopecks`
    instead: a kopecks amount formatted as rubles needs no HTML-escaping, it's digits/space/comma/
    `₽` only; a `bool` value is rendered as "Да"/"Нет" instead of the Python literal "True"/
    "False"). A `{name}` missing from `payload` — e.g. `template_variables` shrank after the user
    saved a template using a now-removed variable — is left as literal `{name}` in the output
    instead of raising, so a stale reference degrades gracefully instead of turning a successful
    delivery into a FAILED one. The template's own literal text (outside `{name}`) is never
    escaped — a user is free to write `<b>`/`<i>`/`<a href=...>` directly in their template for
    formatting; only the *substituted values* are escaped, so marketplace data can't break out of
    that structure."""

    variable_info_map = template_variables or {}
    substitute = partial(_substitute_variable, payload, variable_info_map)
    return _VARIABLE_PATTERN.sub(substitute, template)


def format_changes_text(changes: list[dict]) -> str:
    """Flattens `AutomationCheckLog.changes` (`{field, old_value, new_value, threshold_breached}[]`)
    into one multiline string — the `{changes_text}` template variable of
    `automation.change_detected` (see `NotificationEvent.template_variables`). A user's own
    template can't loop over the raw `changes` list, so the calling domain
    (`AutomationService._finalize_check`) calls this once when building `notify()`'s payload,
    rather than every custom template reimplementing the same loop.

    Deliberately **not** HTML-escaped here — this string lands in `NotificationDelivery.payload`,
    which is channel-agnostic stored/API data (`GET /api/notifications/deliveries`), not
    Telegram-bound text yet. Escaping happens once, at the point something actually renders it for
    Telegram (`_escape`, in `render_template`/`format_automation_change_detected` below) — baking
    HTML entities into stored payload would leak a Telegram-specific concern into a generic
    journal, and there's no channel besides Telegram today that would even need it un-escaped.

    A `MONEY_FIELDS` field's `old_value`/`new_value` (raw kopecks, same as everywhere else in the
    API) *is* converted to a rubles string here (`format_money_kopecks`) — unlike HTML-escaping,
    that isn't a Telegram-specific rendering concern, it's "how humans read a price", so it belongs
    in this already-human-readable string rather than deferred to the Telegram-render boundary."""

    lines = []
    for change in changes:
        field = change.get('field')
        old_value, new_value = change.get('old_value'), change.get('new_value')
        if field in MONEY_FIELDS:
            old_value, new_value = format_money_kopecks(old_value), format_money_kopecks(new_value)
        lines.append(f'{field}: {old_value} → {new_value}')
    return '\n'.join(lines)


def format_automation_change_detected(payload: dict) -> str:
    lines = [f"🔔 Автоматизация {_escape(payload.get('automation_id'))}: обнаружены изменения"]
    changes_text = payload.get('changes_text') or format_changes_text(payload.get('changes') or [])
    if changes_text:
        lines.append(_escape(changes_text))
    return '\n'.join(lines)


def format_task_completed(payload: dict) -> str:
    return f"✅ Задача {_escape(payload.get('task_id'))} завершена"


def format_task_failed(payload: dict) -> str:
    return (
        f"❌ Задача {_escape(payload.get('task_id'))} завершилась с ошибкой: "
        f"{_escape(payload.get('error_reason'))}"
    )


MESSAGE_FORMATTERS: dict[str, Callable[[dict], str]] = {
    'automation.change_detected': format_automation_change_detected,
    'task.completed': format_task_completed,
    'task.failed': format_task_failed,
}


def build_message_text(
    event_code: str,
    payload: dict,
    template: str | None = None,
    template_variables: 'dict[str, NotificationTemplateVariableEntity] | None' = None,
) -> str:
    """Renders a human-readable Telegram message for a delivery. `template` — the user's own
    `{name}`-style template (`NotificationEventPreference.template`, validated against
    `NotificationEvent.template_variables` at `update_preferences` time, see
    `packages/notifications/AGENTS.md`, "Пользовательские шаблоны сообщений") — takes priority over
    the built-in formatter below when set. `template_variables` — the same event's catalog entry,
    passed through to `render_template` so it knows which `{name}`s are money (kopecks -> rubles)
    vs plain values; only used when `template` is set.

    Falls back to a generic `event_code: payload` dump for an event_code without a registered
    formatter — this should not happen for anything in `notification_events` (every catalog entry
    that reaches here is one the calling domain already knows how to describe), but keeps
    `dispatch_pending` from crashing on a future event_code added to the catalog before its
    formatter is wired up here."""

    if template:
        return render_template(
            template=template, payload=payload, template_variables=template_variables,
        )

    formatter = MESSAGE_FORMATTERS.get(event_code)
    if formatter is None:
        return f'{event_code}: {payload}'
    return formatter(payload)
