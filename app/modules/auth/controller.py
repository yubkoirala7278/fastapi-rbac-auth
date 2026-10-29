import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response import ApiResponse
from app.core.exceptions import ConflictError, ForbiddenError, UnauthorizedError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    token_issued_before,
    verify_password,
)
from app.dependencies import DbSession
from app.modules.auth.dtos import (
    LoginRequest,
    LogoutRequest,
    ProfileUpdateRequest,
    RefreshRequest,
    TokenResponse,
    UserResponse,
)
from app.modules.auth.models import User
from app.modules.auth.repository import (
    RefreshTokenRepository,
    RevokedAccessTokenRepository,
    UserRepository,
)

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass
class AuthContext:
    """The authenticated user plus the decoded access-token payload of the request."""

    user: User
    token_payload: dict[str, Any]


class AuthController:
    """
    Owns the full auth business logic: login, token refresh (with rotation),
    logout (refresh-token revocation), and current-user resolution.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.user_repo = UserRepository(db)
        self.refresh_token_repo = RefreshTokenRepository(db)
        self.revoked_access_repo = RevokedAccessTokenRepository(db)

    # --- Public use-cases, called directly by the router ---------------------

    async def login(self, payload: LoginRequest) -> ApiResponse[TokenResponse]:
        user = await self.user_repo.get_by_email(payload.email, include_inactive=True)
        if user is None or not verify_password(payload.password, user.password):
            raise UnauthorizedError("Invalid email or password.")

        # Only revealed after the password is verified, so it can't be used to
        # probe which accounts exist or are deactivated.
        if not user.is_active:
            raise ForbiddenError(
                "Your account has been deactivated. Please contact the administrator."
            )

        tokens = await self._issue_tokens(user)
        return ApiResponse(message="Login successful.", data=tokens)

    async def refresh(self, payload: RefreshRequest) -> ApiResponse[TokenResponse]:
        token_payload = decode_token(payload.refresh_token, expected_type="refresh")
        jti = token_payload["jti"]

        stored = await self.refresh_token_repo.get_by_jti(jti)
        if stored is None or stored.revoked:
            raise UnauthorizedError("Refresh token has been revoked or does not exist.")

        if stored.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
            raise UnauthorizedError("Refresh token has expired.")

        user = await self.user_repo.get_by_id(stored.user_id)
        if user is None:
            raise UnauthorizedError("User account is no longer active.")

        # Rotate: revoke the old refresh token and issue a brand new pair.
        await self.refresh_token_repo.revoke(jti)
        tokens = await self._issue_tokens(user)
        return ApiResponse(message="Token refreshed successfully.", data=tokens)

    async def logout(self, auth: AuthContext, payload: LogoutRequest) -> ApiResponse[None]:
        # Expired refresh tokens are accepted here so the user can always sign out.
        refresh_payload = decode_token(payload.refresh_token, expected_type="refresh", verify_exp=False)
        if refresh_payload.get("sub") != str(auth.user.id):
            raise ForbiddenError("Refresh token does not belong to the current user.")

        await self.refresh_token_repo.revoke(refresh_payload["jti"])

        # Revoke the access token used for this request so it stops working immediately.
        await self.revoked_access_repo.revoke(
            jti=auth.token_payload["jti"],
            user_id=auth.user.id,
            expires_at=datetime.fromtimestamp(auth.token_payload["exp"], tz=timezone.utc),
        )
        return ApiResponse(message="Logout successful.", data=None)

    async def me(self, user: User) -> ApiResponse[UserResponse]:
        return ApiResponse(message="Current user fetched.", data=UserResponse.model_validate(user))

    async def update_profile(
        self, user: User, payload: ProfileUpdateRequest
    ) -> ApiResponse[UserResponse]:
        if payload.email is not None and payload.email != user.email:
            existing = await self.user_repo.get_by_email(payload.email, include_inactive=True)
            if existing is not None and existing.id != user.id:
                raise ConflictError("That email address is already in use.")

        update_fields = payload.model_dump(exclude_unset=True, exclude_none=True)
        await self.user_repo.update(user, **update_fields)
        updated_user = await self.user_repo.get_by_id(user.id)
        return ApiResponse(
            message="Profile updated successfully.",
            data=UserResponse.model_validate(updated_user),
        )

    # --- Internal helpers ---------------------------------------------------

    async def _issue_tokens(self, user: User) -> TokenResponse:
        access_token = create_access_token(user.id)
        refresh_token, jti, expires_at = create_refresh_token(user.id)
        await self.refresh_token_repo.create(jti=jti, user_id=user.id, expires_at=expires_at)
        return TokenResponse(access_token=access_token, refresh_token=refresh_token)


# --- FastAPI dependency: protects routes, resolves the current user ---------

async def get_auth_context(
    db: DbSession,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> AuthContext:
    if credentials is None:
        raise UnauthorizedError("Missing bearer token.")

    payload = decode_token(credentials.credentials, expected_type="access")
    jti = payload.get("jti")
    if jti is None or await RevokedAccessTokenRepository(db).is_revoked(jti):
        raise UnauthorizedError("Access token has been revoked.")

    user_id = uuid.UUID(payload["sub"])

    user = await UserRepository(db).get_by_id(user_id)
    if user is None:
        raise UnauthorizedError("User not found or inactive.")
    if token_issued_before(payload, user.password_changed_at):
        raise UnauthorizedError("Access token was invalidated by a password change.")

    return AuthContext(user=user, token_payload=payload)


async def get_current_user(auth: AuthContext = Depends(get_auth_context)) -> User:
    return auth.user


CurrentAuth = Depends(get_auth_context)
CurrentUser = Depends(get_current_user)