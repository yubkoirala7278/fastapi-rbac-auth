import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.pagination import PaginationParams
from app.common.response import ApiResponse, PaginatedResponse
from app.core.exceptions import ConflictError, ForbiddenError, UnauthorizedError
from app.core.security import hash_password, verify_password
from app.common.utils import utc_now
from app.modules.auth.repository import RefreshTokenRepository
from app.modules.auth.models import User
from app.modules.users.dtos import (
    UserCreateRequest,
    UserPasswordUpdateRequest,
    UserResponse,
    UserUpdateRequest,
)
from app.modules.users.repository import UserRepository


class UserController:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.user_repo = UserRepository(db)

    async def create_user(self, payload: UserCreateRequest) -> ApiResponse[UserResponse]:
        existing = await self.user_repo.get_by_email(payload.email, include_deleted=True)
        if existing is not None:
            raise ConflictError(f"User with email '{payload.email}' already exists.")

        user = await self.user_repo.create(
            name=payload.name,
            email=payload.email,
            password=hash_password(payload.password),
            is_active=payload.is_active,
        )
        user = await self.user_repo.get_by_id_or_raise(user.id)
        return ApiResponse(message="User created successfully.", data=UserResponse.model_validate(user))

    async def list_users(self, params: PaginationParams) -> PaginatedResponse[UserResponse]:
        result = await self.user_repo.list(params)
        return PaginatedResponse.from_result(result, serializer=UserResponse.model_validate)

    async def get_user(self, user_id: uuid.UUID) -> ApiResponse[UserResponse]:
        user = await self.user_repo.get_by_id_or_raise(user_id)
        return ApiResponse(message="User fetched successfully.", data=UserResponse.model_validate(user))

    async def update_user(
        self, user_id: uuid.UUID, payload: UserUpdateRequest, current_user: User
    ) -> ApiResponse[UserResponse]:
        user = await self.user_repo.get_by_id_or_raise(user_id)

        if user.id == current_user.id and payload.is_active is not None and payload.is_active != user.is_active:
            raise ForbiddenError("You cannot change your own account status.")

        if payload.email is not None and payload.email != user.email:
            existing = await self.user_repo.get_by_email(payload.email, include_deleted=True)
            if existing is not None:
                raise ConflictError(f"User with email '{payload.email}' already exists.")

        update_fields = payload.model_dump(exclude_unset=True)
        user = await self.user_repo.update(user, **update_fields)
        user = await self.user_repo.get_by_id_or_raise(user.id)
        return ApiResponse(message="User updated successfully.", data=UserResponse.model_validate(user))

    async def update_password(
        self, user_id: uuid.UUID, payload: UserPasswordUpdateRequest
    ) -> ApiResponse[None]:
        user = await self.user_repo.get_by_id_or_raise(user_id)
        if not verify_password(payload.current_password, user.password):
            raise UnauthorizedError("Current password is incorrect.")

        await self.user_repo.update(
            user,
            password=hash_password(payload.new_password),
            password_changed_at=utc_now().replace(microsecond=0),
        )
        await RefreshTokenRepository(self.db).delete_all_for_user(user.id)
        return ApiResponse(message="Password updated successfully.", data=None)

    async def delete_user(self, user_id: uuid.UUID, current_user: User) -> ApiResponse[None]:
        user = await self.user_repo.get_by_id_or_raise(user_id)
        if user.id == current_user.id:
            raise ForbiddenError("You cannot delete your own account.")

        await self.user_repo.delete(user)
        return ApiResponse(message="User deleted successfully.", data=None)