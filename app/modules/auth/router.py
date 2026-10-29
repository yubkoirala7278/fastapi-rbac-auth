from fastapi import APIRouter, Request

from app.common.response import ApiResponse
from app.core.rate_limiter import limiter
from app.dependencies import DbSession
from app.modules.auth.controller import AuthContext, AuthController, CurrentAuth, CurrentUser
from app.modules.auth.dtos import (
    LoginRequest,
    LogoutRequest,
    ProfileUpdateRequest,
    RefreshRequest,
    TokenResponse,
    UserResponse,
)
from app.modules.auth.models import User

router = APIRouter()


@router.post("/login", response_model=ApiResponse[TokenResponse])
@limiter.limit("5/minute")  # brute-force protection on login specifically
async def login(request: Request, payload: LoginRequest, db: DbSession):
    return await AuthController(db).login(payload)


@router.post("/refresh", response_model=ApiResponse[TokenResponse])
async def refresh(payload: RefreshRequest, db: DbSession):
    return await AuthController(db).refresh(payload)


@router.post("/logout", response_model=ApiResponse[None])
async def logout(payload: LogoutRequest, db: DbSession, auth: AuthContext = CurrentAuth):
    return await AuthController(db).logout(auth, payload)


@router.get("/me", response_model=ApiResponse[UserResponse])
async def me(db: DbSession, current_user: User = CurrentUser):
    return await AuthController(db).me(current_user)


@router.patch("/profile", response_model=ApiResponse[UserResponse])
async def update_profile(
    payload: ProfileUpdateRequest,
    db: DbSession,
    current_user: User = CurrentUser,
):
    return await AuthController(db).update_profile(current_user, payload)