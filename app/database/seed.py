"""
Database seeder entry point.

Run from the project root:

    python -m app.database.seed

Runs each seeder in order (each is idempotent — safe to re-run):
  1. RBAC: permissions + Super Admin role      (seeders/rbac_seeder.py)
  2. Admin user, assigned the Super Admin role (seeders/admin_user_seeder.py)
"""

import asyncio
import logging

from app.database.seeders.admin_user_seeder import seed_admin_user
from app.database.seeders.rbac_seeder import seed_rbac

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("seeder")


async def run_all_seeders() -> None:
    logger.info("Starting database seeding...")
    role = await seed_rbac()
    await seed_admin_user(role)
    logger.info("Seeding complete.")


if __name__ == "__main__":
    asyncio.run(run_all_seeders())