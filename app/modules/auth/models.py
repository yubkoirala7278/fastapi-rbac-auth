import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.modules.rbac.models import Role


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "users"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    password_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # secondary="user_roles" resolves against Base.metadata at mapper-configure
    # time, so no direct import of the rbac module's association table is
    # needed here (avoids a circular import between auth <-> rbac).
    roles: Mapped[list["Role"]] = relationship(
        secondary="user_roles",
        back_populates="users",
        lazy="raise",
    )


class RefreshToken(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Tracks issued refresh tokens so they can be individually revoked on logout.
    `jti` is the token's unique id (from the JWT payload), not the token string itself.
    """

    __tablename__ = "refresh_tokens"

    jti: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    expires_at: Mapped["DateTime"] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class RevokedAccessToken(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Denylist of access tokens revoked before their natural expiry (e.g. on logout).
    Rows are only needed until `expires_at`; after that the JWT is rejected anyway,
    so expired rows are purged opportunistically (see repository).
    """

    __tablename__ = "revoked_access_tokens"

    jti: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    user = relationship("User", lazy="raise")  # never lazy-load; use selectinload explicitly