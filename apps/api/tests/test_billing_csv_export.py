from datetime import datetime, timezone

from apps.api.src.routers.billing.csv_export import BOM, HEADER, build_transactions_csv
from packages.billing.src.entities import CreditTransactionEntity
from packages.billing.src.enums import ReferenceType


def _spend() -> CreditTransactionEntity:
    return CreditTransactionEntity(
        id=1,
        user_id=1,
        amount=-3,
        balance_after=97,
        action_code='result.SEARCH_QUERY',
        reference_type=ReferenceType.TASK,
        reference_id='task-1',
        transaction_metadata={'quantity': 3, 'unit_cost': '1.00', 'multiplier': '1.00'},
        created_at=datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc),
    )


def _grant() -> CreditTransactionEntity:
    return CreditTransactionEntity(
        id=2,
        user_id=1,
        amount=100,
        balance_after=100,
        transaction_metadata={'comment': 'бонус; "тест"'},
        created_at=datetime(2026, 10, 8, 9, 0, tzinfo=timezone.utc),
    )


def test_csv_starts_with_bom_and_header() -> None:
    content = build_transactions_csv([])
    assert ord(content[0]) == 0xFEFF
    assert content.startswith(BOM)
    assert content[len(BOM):].strip() == ';'.join(HEADER)


def test_csv_distinguishes_spend_and_grant() -> None:
    lines = build_transactions_csv([_spend(), _grant()]).splitlines()
    assert 'списание' in lines[1]
    assert 'result.SEARCH_QUERY' in lines[1]
    assert 'task-1' in lines[1]
    assert 'начисление' in lines[2]


def test_csv_escapes_delimiter_and_quotes_in_comment() -> None:
    content = build_transactions_csv([_grant()])
    assert '"бонус; ""тест"""' in content


def test_csv_attributes_automation_check_charge_to_automation() -> None:
    check = _spend().model_copy(
        update={'transaction_metadata': {'quantity': 1, 'automation_id': 'auto-7'}},
    )
    row = build_transactions_csv([check]).splitlines()[1].split(';')
    # Списание идёт с reference_type=task, но источник для пользователя — автоматизация.
    assert row[5] == 'automation'
    assert row[6] == 'auto-7'
