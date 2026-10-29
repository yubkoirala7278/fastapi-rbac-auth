import uuid

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.pagination import PaginationParams
from app.common.response import ApiResponse, PaginatedResponse
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.dependencies import DbSession
from app.modules.auth.controller import get_current_user
from app.modules.auth.models import User
from app.modules.rbac.dtos import (
    PermissionCreateRequest,
    PermissionResponse,
    RoleCreateRequest,
    RoleResponse,
    RoleSummaryResponse,
    RoleUpdateRequest,
    SyncPermissionsRequest,
    SyncRolesRequest,
    UserRolesResponse,
)
from app.modules.rbac.models import Permission, Role
from app.modules.rbac.repository import PermissionRepository, RoleRepository
from app.modules.users.repository import UserRepository


class RBACController:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.role_repo = RoleRepository(db)
        self.permission_repo = PermissionRepository(db)
        self.user_repo = UserRepository(db)

    # --- Permissions ----------------------------------------------------------

    async def create_permission(self, payload: PermissionCreateRequest) -> ApiResponse[PermissionResponse]:
        permission = await self.permission_repo.create_permission(
            module=payload.module.strip().lower(),
            action=payload.action.strip().lower()
        )
        return ApiResponse(
            message="Permission created successfully.",
            data=PermissionResponse.model_validate(permission),
        )

    async def list_permissions(self, params: PaginationParams) -> PaginatedResponse[PermissionResponse]:
        result = await self.permission_repo.list(params)
        return PaginatedResponse.from_result(result, serializer=PermissionResponse.model_validate)

    async def delete_permission(self, permission_id: uuid.UUID) -> ApiResponse[None]:
        permission = await self.permission_repo.get_by_id_or_raise(permission_id)
        await self.permission_repo.delete(permission)
        return ApiResponse(message="Permission deleted successfully.", data=None)

    # --- Roles ------------------------------------------------------------------

    async def create_role(self, payload: RoleCreateRequest) -> ApiResponse[RoleResponse]:
        existing = await self.role_repo.get_by_name(payload.name, include_deleted=True)

        if existing is not None and existing.deleted_at is None:
            raise ConflictError(f"Role '{payload.name}' already exists.")

        if existing is not None and existing.deleted_at is not None:
            # Soft-deleted role with the same name — restore it instead of inserting a duplicate
            existing.deleted_at = None
            await self.db.flush()
            role = existing
        else:
            role = await self.role_repo.create(name=payload.name)

        role = await self.role_repo.get_by_id_with_permissions(role.id)
        return ApiResponse(message="Role created successfully.", data=RoleResponse.model_validate(role))

    async def update_role(self, role_id: uuid.UUID, payload: RoleUpdateRequest) -> ApiResponse[RoleResponse]:
        role = await self.role_repo.get_by_id_with_permissions(role_id)
        role = await self.role_repo.update(role, name=payload.name)
        return ApiResponse(message="Role updated successfully.", data=RoleResponse.model_validate(role))

    async def get_role(self, role_id: uuid.UUID) -> ApiResponse[RoleResponse]:
        role = await self.role_repo.get_by_id_with_permissions(role_id)
        return ApiResponse(message="Role fetched successfully.", data=RoleResponse.model_validate(role))

    async def list_roles(self, params: PaginationParams) -> PaginatedResponse[RoleSummaryResponse]:
        result = await self.role_repo.list(params)
        return PaginatedResponse.from_result(result, serializer=RoleSummaryResponse.model_validate)

    async def delete_role(self, role_id: uuid.UUID) -> ApiResponse[None]:
        role = await self.role_repo.get_by_id_or_raise(role_id)
        await self.role_repo.delete(role)
        return ApiResponse(message="Role deleted successfully.", data=None)

    # --- Role <-> Permission assignment -----------------------------------

    async def sync_role_permissions(
        self, role_id: uuid.UUID, payload: SyncPermissionsRequest
    ) -> ApiResponse[RoleResponse]:
        role = await self.role_repo.get_by_id_or_raise(role_id)

        requested_ids = set(payload.permission_ids)
        permissions = await self.permission_repo.get_many_by_ids(list(requested_ids))
        missing = requested_ids - {p.id for p in permissions}
        if missing:
            raise NotFoundError(f"Permission id(s) not found: {', '.join(str(m) for m in missing)}")

        await self.role_repo.set_permissions(role.id, list(requested_ids))
        role = await self.role_repo.get_by_id_with_permissions(role.id)
        return ApiResponse(message="Role permissions updated.", data=RoleResponse.model_validate(role))

    # --- User <-> Role assignment -------------------------------------------

    async def sync_user_roles(
        self, user_id: uuid.UUID, payload: SyncRolesRequest, current_user: User
    ) -> ApiResponse[UserRolesResponse]:
        if user_id == current_user.id:
            raise ForbiddenError("You cannot change your own roles.")

        await self.user_repo.get_by_id_or_raise(user_id)

        requested_ids = set(payload.role_ids)
        roles = await self.role_repo.list_all(extra_filters=[Role.id.in_(requested_ids)]) if requested_ids else []
        missing = requested_ids - {r.id for r in roles}
        if missing:
            raise NotFoundError(f"Role id(s) not found: {', '.join(str(m) for m in missing)}")

        await self.role_repo.set_roles_for_user(user_id, list(requested_ids))
        updated_roles = await self.role_repo.get_roles_for_user(user_id)
        return ApiResponse(
            message="User roles updated.",
            data=UserRolesResponse(
                user_id=user_id,
                roles=[RoleSummaryResponse.model_validate(r) for r in updated_roles],
            ),
        )

    async def get_user_roles(self, user_id: uuid.UUID) -> ApiResponse[UserRolesResponse]:
        roles = await self.role_repo.get_roles_for_user(user_id)
        return ApiResponse(
            data=UserRolesResponse(
                user_id=user_id,
                roles=[RoleSummaryResponse.model_validate(r) for r in roles],
            )
        )


# --- Authorization dependency, for use by ANY module's routes -----------------

def require_permission(permission_code: str):
    """
    FastAPI dependency factory. Usage on any route in any module:

        @router.post("/sifarish")
        async def create_sifarish(
            db: DbSession,
            _: None = Depends(require_permission("sifarish:create_sifarish")),
        ):
            ...

    Raises ForbiddenError (403) if the current user doesn't hold the
    given permission through any of their assigned roles.
    """

    async def _check(
        db: DbSession,
        current_user: User = Depends(get_current_user),
    ) -> None:
        codes = await RoleRepository(db).get_permission_codes_for_user(current_user.id)
        if permission_code not in codes:
            raise ForbiddenError("You do not have permission to perform this action.")

    return _check