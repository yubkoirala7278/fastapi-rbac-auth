"""
Admin user seeder: creates the initial admin account and grants it a role.

Depends on the RBAC seeder having already created the target role
(pass it in — see seed_admin_user below).
"""

import logging

from sqlalchemy import select

from app.core.security import hash_password
from app.database.session import AsyncSessionLocal
from app.modules.auth.models import User
from app.modules.rbac.models import Role
from app.modules.rbac.repository import RoleRepository

logger = logging.getLogger("seeder.admin_user")

# --- Admin credentials ----------------------------------------------------
# Change these before running in a real environment.
ADMIN_EMAIL = "admin@admin.com"
ADMIN_NAME = "Administrator"
ADMIN_PASSWORD = "adminsecret"
# ---------------------------------------------------------------------------


async def seed_admin_user(role: Role) -> None:
    """Creates the admin user if missing, and ensures they hold the given role."""
    async with AsyncSessionLocal() as db:
        existing = await db.execute(select(User).where(User.email == ADMIN_EMAIL))
        admin = existing.scalar_one_or_none()

        if admin is None:
            admin = User(
                name=ADMIN_NAME,
                email=ADMIN_EMAIL,
                password=hash_password(ADMIN_PASSWORD),
                is_active=True,
            )
            db.add(admin)
            await db.flush()
            logger.info("Created admin user '%s'", ADMIN_EMAIL)
        else:
            logger.info("Admin user '%s' already exists.", ADMIN_EMAIL)

        role_repo = RoleRepository(db)
        await role_repo.add_roles_to_user(admin.id, [role.id])
        await db.commit()

        logger.info("Ensured admin user holds role '%s'.", role.name)
        logger.info("Admin credentials:")
        logger.info("  email:    %s", ADMIN_EMAIL)
        logger.info("  password: %s  (change this after first login)", ADMIN_PASSWORD)