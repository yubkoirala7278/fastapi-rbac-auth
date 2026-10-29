"""
RBAC seeder: permissions + the Super Admin role.

Seeds, in order (idempotent — safe to re-run):
  1. A set of module-wise permissions (e.g. "user:create_user", "product:edit_product")
  2. A "Super Admin" role holding every seeded permission

Note: role/permission assignment goes through RoleRepository's direct
association-table operations (add_permissions) rather than touching
Role.permissions as an ORM collection. That relationship is declared
lazy="raise" on purpose (see modules/rbac/models.py) — accessing it
without an explicit selectinload raises by design, even on freshly
constructed objects. Going through the repository sidesteps that entirely
and matches how the rest of the app performs assignment.
"""

import logging

from sqlalchemy import select

from app.database.session import AsyncSessionLocal
from app.modules.rbac.models import Permission, Role
from app.modules.rbac.repository import RoleRepository

logger = logging.getLogger("seeder.rbac")

SUPER_ADMIN_ROLE_NAME = "Super Admin"

# --- Module-wise permission catalog ----------------------------------------
# Extend this dict as new modules are built. Each (module, action) pair
# becomes a Permission row with code = f"{module}:{action}".
PERMISSION_CATALOG: dict[str, list[str]] = {
    "user": ["view_user", "create_user", "edit_user", "delete_user"],
    "role": ["view_role", "create_role", "edit_role", "delete_role"],
    "permission": ["view_permission", "create_permission", "delete_permission"],
    # "product": ["view_product", "create_product", "edit_product", "delete_product"],
}
# ---------------------------------------------------------------------------


async def seed_permissions() -> list[Permission]:
    """Creates any missing permissions from PERMISSION_CATALOG. Returns ALL of them."""
    async with AsyncSessionLocal() as db:
        for module, actions in PERMISSION_CATALOG.items():
            for action in actions:
                code = f"{module}:{action}"
                existing = await db.execute(select(Permission).where(Permission.code == code))
                if existing.scalar_one_or_none() is None:
                    db.add(Permission(module=module, action=action, code=code))
                    logger.info("Created permission '%s'", code)

        await db.commit()

        # Re-fetch fresh, fully-committed rows in one query.
        all_codes = [f"{m}:{a}" for m, actions in PERMISSION_CATALOG.items() for a in actions]
        result = await db.execute(select(Permission).where(Permission.code.in_(all_codes)))
        return list(result.scalars().all())


async def seed_super_admin_role(permissions: list[Permission]) -> Role:
    """Creates the Super Admin role if missing, and ensures it holds every given permission."""
    async with AsyncSessionLocal() as db:
        existing = await db.execute(select(Role).where(Role.name == SUPER_ADMIN_ROLE_NAME))
        role = existing.scalar_one_or_none()

        if role is None:
            role = Role(name=SUPER_ADMIN_ROLE_NAME)
            db.add(role)
            await db.flush()
            logger.info("Created role '%s'", SUPER_ADMIN_ROLE_NAME)

        role_repo = RoleRepository(db)
        await role_repo.add_permissions(role.id, [p.id for p in permissions])
        await db.commit()

        logger.info("Ensured '%s' holds all %d seeded permissions.", SUPER_ADMIN_ROLE_NAME, len(permissions))
        return role


async def seed_rbac() -> Role:
    """Runs the full RBAC seed (permissions, then the Super Admin role) and returns the role."""
    permissions = await seed_permissions()
    role = await seed_super_admin_role(permissions)
    return role