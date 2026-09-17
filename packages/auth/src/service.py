from datetime import datetime, timezone

from core.exceptions import DuplicatedObjectError
from core.transaction_manager import AsyncTransactionManager
from packages.audit_log.src.entities import AuditLogEntity
from packages.audit_log.src.enums import AuditAction, AuditActionType, AuditStatus
from packages.audit_log.src.utils import build_create_fields
from packages.auth.src.exceptions import InvalidCredentialsError, UserAlreadyExistsError
from packages.auth.src.security import hash_password, verify_password
from packages.user.src.entities import UserEntity
from packages.user.src.enums import UserRole

TARGET_TYPE_USER = 'User'


class AuthService:
    def __init__(self, transaction_manager: AsyncTransactionManager):
        self.transaction_manager = transaction_manager

    async def register_user(
        self,
        display_name: str,
        email: str,
        password: str,
        ip_address: str | None = None,
    ) -> UserEntity:
        try:
            async with self.transaction_manager(use_user_repository=True) as transaction:
                existing_user = await transaction.user_repository.get_by_email(email=email)
                if existing_user is not None:
                    raise UserAlreadyExistsError

                # First user in an empty system becomes ADMIN, so there's always a way to
                # administer the system without a separate bootstrap/seed step. Not race-safe
                # under concurrent registration on an empty table — acceptable for a one-off
                # bootstrap action, not for the ongoing registration flow.
                is_first_user = not await transaction.user_repository.exists()
                role = UserRole.ADMIN if is_first_user else UserRole.CLIENT

                user_entity = UserEntity(
                    display_name=display_name,
                    email=email,
                    hashed_password=hash_password(password=password),
                    role=role,
                )
                try:
                    created_user = await transaction.user_repository.create(entity=user_entity)
                except DuplicatedObjectError as error:
                    raise UserAlreadyExistsError from error
                else:
                    await self.transaction_manager.commit()
        except UserAlreadyExistsError:
            await self._record_audit_event(
                action=AuditAction.AUTH_REGISTER_USER,
                action_type=AuditActionType.CREATE,
                status=AuditStatus.FAILURE,
                error_reason='user_already_exists',
                target_type=TARGET_TYPE_USER,
                ip_address=ip_address,
            )
            raise

        await self._record_audit_event(
            action=AuditAction.AUTH_REGISTER_USER,
            action_type=AuditActionType.CREATE,
            status=AuditStatus.SUCCESS,
            user_id=created_user.id,
            target_type=TARGET_TYPE_USER,
            target_id=created_user.id,
            details={'fields': build_create_fields(created_user)},
            ip_address=ip_address,
        )
        return created_user

    async def authenticate_user(
        self,
        email: str,
        password: str,
        ip_address: str | None = None,
    ) -> UserEntity:
        try:
            async with self.transaction_manager(use_user_repository=True) as transaction:
                user_entity = await transaction.user_repository.get_by_email(email=email)
                if user_entity is None or not verify_password(
                    password=password,
                    hashed_password=user_entity.hashed_password,
                ):
                    raise InvalidCredentialsError

                authenticated_user = await transaction.user_repository.update(
                    entity=UserEntity(
                        id=user_entity.id,
                        last_active_at=datetime.now(tz=timezone.utc),
                    ),
                )
                await self.transaction_manager.commit()
        except InvalidCredentialsError:
            await self._record_audit_event(
                action=AuditAction.AUTH_AUTHENTICATE_USER,
                action_type=AuditActionType.AUTH,
                status=AuditStatus.FAILURE,
                error_reason='invalid_credentials',
                target_type=TARGET_TYPE_USER,
                ip_address=ip_address,
            )
            raise

        await self._record_audit_event(
            action=AuditAction.AUTH_AUTHENTICATE_USER,
            action_type=AuditActionType.AUTH,
            status=AuditStatus.SUCCESS,
            user_id=authenticated_user.id,
            target_type=TARGET_TYPE_USER,
            target_id=authenticated_user.id,
            ip_address=ip_address,
        )
        return authenticated_user

    async def has_users(self) -> bool:
        async with self.transaction_manager(use_user_repository=True) as transaction:
            return await transaction.user_repository.exists()

    async def _record_audit_event(
        self,
        *,
        action: AuditAction,
        action_type: AuditActionType,
        status: AuditStatus,
        ip_address: str | None,
        user_id: int | None = None,
        target_type: str | None = None,
        target_id: int | None = None,
        details: dict | None = None,
        error_reason: str | None = None,
    ) -> None:
        # Audit events are written in their own transaction, independent of the business
        # transaction above: a failed registration/login must still be recorded even though
        # its own transaction rolled back, and a problem persisting the audit log must not
        # roll back an otherwise successful registration/login.
        async with self.transaction_manager(use_audit_log_repository=True) as transaction:
            await transaction.audit_log_repository.create(
                entity=AuditLogEntity(
                    action=action,
                    action_type=action_type,
                    status=status,
                    details=details or {'fields': {}},
                    error_reason=error_reason,
                    target_type=target_type,
                    target_id=target_id,
                    user_id=user_id,
                    ip_address=ip_address,
                ),
            )
            await self.transaction_manager.commit()
