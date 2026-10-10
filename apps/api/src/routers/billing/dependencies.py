from fastapi import Depends, HTTPException, Query, status

from apps.api.src.routers.auth.dependencies import get_current_user
from apps.api.src.routers.dependencies import get_date_range
from apps.api.src.routers.schema import DateRange
from packages.billing.src.entities import TransactionFilters
from packages.billing.src.enums import ReferenceType, TransactionKind
from packages.user.src.entities import UserEntity
from packages.user.src.enums import UserRole


async def get_current_admin_user(
    current_user: UserEntity = Depends(get_current_user),
) -> UserEntity:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Admin access required')
    return current_user


def get_transaction_filters(
    reference_type: ReferenceType | None = Query(
        default=None, description='Тип источника: task / automation / direct',
    ),
    reference_id: str | None = Query(default=None, description='Идентификатор источника'),
    kind: TransactionKind | None = Query(
        default=None, description='spend — только списания, grant — только начисления',
    ),
    date_range: DateRange = Depends(get_date_range),
) -> TransactionFilters:
    """Общие фильтры журнала транзакций пользователя (AND) для списка, группировки и экспорта."""
    return TransactionFilters(
        reference_type=reference_type,
        reference_id=reference_id,
        kind=kind,
        date_from=date_range.date_from,
        date_to=date_range.date_to,
    )
