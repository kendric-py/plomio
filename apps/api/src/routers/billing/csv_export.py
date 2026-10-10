import csv
import io
from collections.abc import Iterable

from packages.billing.src.entities import CreditTransactionEntity

HEADER = [
    'Дата (UTC)',
    'Тип',
    'Сумма',
    'Баланс после',
    'Действие',
    'Источник',
    'ID источника',
    'Количество',
    'Цена за единицу',
    'Множитель',
    'Комментарий',
]

# BOM — чтобы Excel открыл файл в UTF-8, а не в системной кодировке.
BOM = chr(0xFEFF)


def _row(transaction: CreditTransactionEntity) -> list:
    metadata = transaction.transaction_metadata or {}
    is_spend = (transaction.amount or 0) < 0
    # Проверка автоматизации идёт с reference_type=task, но источник для человека — автоматизация.
    automation_id = metadata.get('automation_id')
    source_type = 'automation' if automation_id else (
        transaction.reference_type.value if transaction.reference_type else ''
    )
    source_id = automation_id or transaction.reference_id or ''
    return [
        transaction.created_at.isoformat() if transaction.created_at else '',
        'списание' if is_spend else 'начисление',
        transaction.amount,
        transaction.balance_after,
        transaction.action_code or '',
        source_type,
        source_id,
        metadata.get('quantity', ''),
        metadata.get('unit_cost', ''),
        metadata.get('multiplier', ''),
        metadata.get('comment', ''),
    ]


def build_transactions_csv(transactions: Iterable[CreditTransactionEntity]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=';')
    writer.writerow(HEADER)
    for transaction in transactions:
        writer.writerow(_row(transaction))
    return BOM + buffer.getvalue()
