from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException, Query, status

from apps.api.src.config import config
from apps.api.src.container import DependencyContainer
from apps.api.src.routers.auth.dependencies import get_current_user
from apps.api.src.routers.notifications.schema import (
    CreateTelegramLinkResponse,
    NotificationDeliveryListResponse,
    NotificationDeliveryResponse,
    NotificationEventListResponse,
    NotificationEventResponse,
    NotificationPreferencesResponse,
    TemplateVariableResponse,
    UpdatePreferencesRequest,
)
from apps.api.src.routers.schema import PaginationMeta
from packages.notifications.src.entities import NotificationEventPreference
from packages.notifications.src.exceptions import (
    InvalidNotificationFieldFilterError,
    InvalidNotificationTemplateError,
    UnknownNotificationEventError,
)
from packages.notifications.src.service import NotificationService
from packages.notifications.src.template_catalog import get_template_variables
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
            NotificationEventResponse(
                event_code=event.event_code,
                description=event.description,
                available_fields=event.available_fields,
                template_variables={
                    variable_name: TemplateVariableResponse(
                        field=variable_info.field,
                        description=variable_info.description,
                        is_money=variable_info.is_money,
                    )
                    for variable_name, variable_info in get_template_variables(
                        event_code=event.event_code,
                    ).items()
                } or None,
            )
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
                    channels=item.channels, fields=item.fields, template=item.template,
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
    except InvalidNotificationTemplateError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail='template variables must be a subset of the event\'s template_variables',
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


@router.post('/telegram/link')
@inject
async def create_telegram_link(
    current_user: UserEntity = Depends(get_current_user),
    notification_service: NotificationService = Depends(
        Provide[DependencyContainer.notification_service],
    ),
) -> CreateTelegramLinkResponse:
    code = await notification_service.create_telegram_link_code(
        user_id=current_user.id,
        ttl_seconds=config.TELEGRAM.LINK_CODE_TTL_SECONDS,
    )
    return CreateTelegramLinkResponse(
        deep_link=f'https://t.me/{config.TELEGRAM.BOT_USERNAME}?start={code}',
        expires_in_seconds=config.TELEGRAM.LINK_CODE_TTL_SECONDS,
    )
