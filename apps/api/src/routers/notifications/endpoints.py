from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException, Query, status

from apps.api.src.container import DependencyContainer
from apps.api.src.routers.auth.dependencies import get_current_user
from apps.api.src.routers.notifications.schema import (
    NotificationDeliveryListResponse,
    NotificationDeliveryResponse,
    NotificationEventListResponse,
    NotificationEventResponse,
    NotificationPreferencesResponse,
    UpdatePreferencesRequest,
)
from apps.api.src.routers.schema import PaginationMeta
from packages.notifications.src.entities import NotificationEventPreference
from packages.notifications.src.exceptions import (
    InvalidNotificationFieldFilterError,
    UnknownNotificationEventError,
)
from packages.notifications.src.service import NotificationService
from packages.user.src.entities import UserEntity

router = APIRouter(prefix='/notifications', tags=['Notifications'])


@router.get('/events')
@inject
async def list_events(
    _current_user: UserEntity = Depends(get_current_user),
    notification_service: NotificationService = Depends(
        Provide[DependencyContainer.notification_service],
    ),
) -> NotificationEventListResponse:
    events = await notification_service.list_events()
    return NotificationEventListResponse(
        items=[
            NotificationEventResponse.model_validate(obj=event, from_attributes=True)
            for event in events
        ],
    )


@router.get('/preferences')
@inject
async def get_preferences(
    current_user: UserEntity = Depends(get_current_user),
    notification_service: NotificationService = Depends(
        Provide[DependencyContainer.notification_service],
    ),
) -> NotificationPreferencesResponse:
    setting = await notification_service.get_preferences(user_id=current_user.id)
    return NotificationPreferencesResponse.model_validate(obj=setting, from_attributes=True)


@router.put('/preferences')
@inject
async def update_preferences(
    body: UpdatePreferencesRequest,
    current_user: UserEntity = Depends(get_current_user),
    notification_service: NotificationService = Depends(
        Provide[DependencyContainer.notification_service],
    ),
) -> NotificationPreferencesResponse:
    try:
        setting = await notification_service.update_preferences(
            user_id=current_user.id,
            preferences={
                event_code: NotificationEventPreference(
                    channels=item.channels, fields=item.fields,
                )
                for event_code, item in body.preferences.items()
            },
        )
    except UnknownNotificationEventError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail='Unknown or inactive event_code in preferences',
        ) from error
    except InvalidNotificationFieldFilterError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail='fields must be a subset of the event\'s available_fields',
        ) from error
    return NotificationPreferencesResponse.model_validate(obj=setting, from_attributes=True)


@router.get('/deliveries')
@inject
async def list_deliveries(
    limit: int = Query(default=100, ge=1, le=500, description='Размер страницы'),
    offset: int = Query(default=0, ge=0, description='Смещение страницы'),
    current_user: UserEntity = Depends(get_current_user),
    notification_service: NotificationService = Depends(
        Provide[DependencyContainer.notification_service],
    ),
) -> NotificationDeliveryListResponse:
    items, total = await notification_service.list_deliveries(
        user_id=current_user.id, limit=limit, offset=offset,
    )
    return NotificationDeliveryListResponse(
        items=[
            NotificationDeliveryResponse.model_validate(obj=item, from_attributes=True)
            for item in items
        ],
        meta=PaginationMeta(total=total, limit=limit, offset=offset),
    )
