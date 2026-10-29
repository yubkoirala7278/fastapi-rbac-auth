import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.auth.models import RefreshToken, RevokedAccessToken, User


class UserRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_email(self, email: str, *, include_inactive: bool = False) -> User | None:
        stmt = select(User).options(selectinload(User.roles)).where(User.email == email)
        if not include_inactive:
            stmt = stmt.where(User.is_active.is_(True))
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        stmt = (
            select(User)
            .options(selectinload(User.roles))
            .where(User.id == user_id, User.is_active.is_(True))
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def update(self, user: User, **fields: object) -> User:
        for field, value in fields.items():
            setattr(user, field, value)
        await self.db.flush()
        return user


class RefreshTokenRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, jti: str, user_id: uuid.UUID, expires_at: datetime) -> RefreshToken:
        token = RefreshToken(jti=jti, user_id=user_id, expires_at=expires_at)
        self.db.add(token)
        await self.db.flush()
        return token

    async def get_by_jti(self, jti: str) -> RefreshToken | None:
        stmt = select(RefreshToken).where(RefreshToken.jti == jti)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def revoke(self, jti: str) -> None:
        stmt = update(RefreshToken).where(RefreshToken.jti == jti).values(revoked=True)
        await self.db.execute(stmt)
        await self.db.flush()

    async def revoke_all_for_user(self, user_id: uuid.UUID) -> None:
        stmt = update(RefreshToken).where(RefreshToken.user_id == user_id).values(revoked=True)
        await self.db.execute(stmt)
        await self.db.flush()

    async def delete_all_for_user(self, user_id: uuid.UUID) -> None:
        stmt = delete(RefreshToken).where(RefreshToken.user_id == user_id)
        await self.db.execute(stmt)
        await self.db.flush()

class RevokedAccessTokenRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def revoke(self, jti: str, user_id: uuid.UUID, expires_at: datetime) -> None:
        # Idempotent: revoking an already-revoked token is a no-op.
        stmt = (
            pg_insert(RevokedAccessToken)
            .values(id=uuid.uuid4(), jti=jti, user_id=user_id, expires_at=expires_at)
            .on_conflict_do_nothing(index_elements=[RevokedAccessToken.jti])
        )
        await self.db.execute(stmt)
        await self.purge_expired()

    async def is_revoked(self, jti: str) -> bool:
        stmt = select(RevokedAccessToken.id).where(RevokedAccessToken.jti == jti)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def purge_expired(self) -> None:
        stmt = delete(RevokedAccessToken).where(RevokedAccessToken.expires_at < datetime.now(timezone.utc))
        await self.db.execute(stmt)
        await self.db.flush()
