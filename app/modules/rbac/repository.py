import uuid

from sqlalchemy import delete, func, insert, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.base_repository import BaseRepository
from app.core.exceptions import ConflictError, DependencyExistsError, NotFoundError
from app.modules.rbac.models import Permission, Role, role_permissions, user_roles


class PermissionRepository(BaseRepository[Permission]):
    model = Permission
    eager_load_options = [selectinload(Permission.roles)]
    search_columns = [Permission.module, Permission.action, Permission.code]
    soft_delete = False  # permissions have no deleted_at column; hard delete only

    async def get_by_code(self, code: str) -> Permission | None:
        stmt = select(Permission).where(Permission.code == code)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_many_by_ids(self, ids: list[uuid.UUID]) -> list[Permission]:
        stmt = select(Permission).where(Permission.id.in_(ids))
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def create_permission(self, module: str, action: str) -> Permission:
        code = f"{module}:{action}"
        existing = await self.get_by_code(code)
        if existing is not None:
            raise ConflictError(f"Permission '{code}' already exists.")

        permission = Permission(module=module, action=action, code=code)
        self.db.add(permission)
        await self.db.flush()
        await self.db.refresh(permission)
        return permission

    async def assert_no_dependents(self, obj: Permission) -> None:
        stmt = select(func.count()).select_from(role_permissions).where(
            role_permissions.c.permission_id == obj.id
        )
        count = (await self.db.execute(stmt)).scalar_one()
        if count > 0:
            raise DependencyExistsError(
                f"Cannot delete permission '{obj.code}': it is still assigned to {count} role(s)."
            )


class RoleRepository(BaseRepository[Role]):
    model = Role
    eager_load_options = [selectinload(Role.permissions)]
    search_columns = [Role.name]

    async def get_by_name(self, name: str, *, include_deleted: bool = False) -> Role | None:
       if include_deleted:
           stmt = select(Role).where(Role.name == name)
       else:
           stmt = self._base_select().where(Role.name == name)
       result = await self.db.execute(stmt)
       return result.scalar_one_or_none()

    async def get_by_id_with_permissions(self, role_id: uuid.UUID) -> Role:
        # populate_existing: the role may already be in the session's identity map
        # with a stale `permissions` collection (add/set_permissions write the
        # association table directly), so force a refresh from the database.
        stmt = (
            self._base_select()
            .where(Role.id == role_id)
            .execution_options(populate_existing=True)
        )
        result = await self.db.execute(stmt)
        role = result.scalar_one_or_none()
        if role is None:
            raise NotFoundError(f"Role with id '{role_id}' was not found.")
        return role

    async def assert_no_dependents(self, obj: Role) -> None:
        stmt = select(func.count()).select_from(user_roles).where(user_roles.c.role_id == obj.id)
        count = (await self.db.execute(stmt)).scalar_one()
        if count > 0:
            raise DependencyExistsError(
                f"Cannot delete role '{obj.name}': it is still assigned to {count} user(s)."
            )

    # --- Role <-> Permission assignment (direct association-table ops) ------
    # Operates directly on role_permissions instead of loading Role.permissions
    # into memory, so this stays O(1) regardless of how many permissions exist.

    async def add_permissions(self, role_id: uuid.UUID, permission_ids: list[uuid.UUID]) -> None:
        if not permission_ids:
            return
        stmt = pg_insert(role_permissions).values(
            [{"role_id": role_id, "permission_id": pid} for pid in permission_ids]
        ).on_conflict_do_nothing(index_elements=["role_id", "permission_id"])
        await self.db.execute(stmt)
        await self.db.flush()

    async def set_permissions(self, role_id: uuid.UUID, permission_ids: list[uuid.UUID]) -> None:
        """Makes the role hold exactly `permission_ids`: removes the rest, adds the missing."""
        stmt = delete(role_permissions).where(role_permissions.c.role_id == role_id)
        if permission_ids:
            stmt = stmt.where(role_permissions.c.permission_id.notin_(permission_ids))
        await self.db.execute(stmt)
        await self.add_permissions(role_id, permission_ids)
        await self.db.flush()

    # --- User <-> Role assignment --------------------------------------------

    async def add_roles_to_user(self, user_id: uuid.UUID, role_ids: list[uuid.UUID]) -> None:
        if not role_ids:
            return
        stmt = pg_insert(user_roles).values(
            [{"user_id": user_id, "role_id": rid} for rid in role_ids]
        ).on_conflict_do_nothing(index_elements=["user_id", "role_id"])
        await self.db.execute(stmt)
        await self.db.flush()

    async def set_roles_for_user(self, user_id: uuid.UUID, role_ids: list[uuid.UUID]) -> None:
        """Makes the user hold exactly `role_ids`: removes the rest, adds the missing."""
        stmt = delete(user_roles).where(user_roles.c.user_id == user_id)
        if role_ids:
            stmt = stmt.where(user_roles.c.role_id.notin_(role_ids))
        await self.db.execute(stmt)
        await self.add_roles_to_user(user_id, role_ids)
        await self.db.flush()

    async def get_roles_for_user(self, user_id: uuid.UUID) -> list[Role]:
        stmt = self._base_select().join(user_roles, user_roles.c.role_id == Role.id).where(
            user_roles.c.user_id == user_id
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().unique().all())

    async def get_permission_codes_for_user(self, user_id: uuid.UUID) -> set[str]:
        """
        Returns the flat set of permission codes a user holds across all
        their roles. Used by the `require_permission` authorization dependency.
        """
        stmt = (
            select(Permission.code)
            .join(role_permissions, role_permissions.c.permission_id == Permission.id)
            .join(user_roles, user_roles.c.role_id == role_permissions.c.role_id)
            .where(user_roles.c.user_id == user_id)
        )
        result = await self.db.execute(stmt)
        return set(result.scalars().all())