import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.config import settings
from app.core.exceptions import AppError
from app.core.middleware import RequestContextMiddleware
from app.core.rate_limiter import limiter
from app.database.session import check_db_connection, dispose_engine
    
# --- Routers ---
from app.modules.auth.router import router as auth_router 
from app.modules.rbac.router import router as rbac_router  
from app.modules.users.router import router as users_router  

logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup ---
    logger.info("Starting %s (env=%s)", settings.APP_NAME, settings.APP_ENV)

    db_ok = await check_db_connection()
    if db_ok:
        logger.info("Database connection established successfully.")
    else:
        logger.error(
            "Could not connect to the database at startup. "
            "Check DB_CONNECTION in your .env file and ensure PostgreSQL is running."
        )
        raise RuntimeError("Database connection failed during startup.")

    yield

    # --- Shutdown ---
    logger.info("Shutting down %s", settings.APP_NAME)
    await dispose_engine()


app = FastAPI(
    title=settings.APP_NAME,
    debug=settings.DEBUG,
    lifespan=lifespan,
)

# --- Rate limiting ---
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# --- Request logging / correlation ---
app.add_middleware(RequestContextMiddleware)

# --- CORS (tighten allow_origins for production) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.DEBUG else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Global exception handlers ---

@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    logger.warning("AppError on %s %s: %s", request.method, request.url.path, exc.message)
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "message": exc.message, "detail": None},
    )


@app.exception_handler(IntegrityError)
async def integrity_error_handler(request: Request, exc: IntegrityError) -> JSONResponse:
    logger.warning("IntegrityError on %s %s: %s", request.method, request.url.path, str(exc.orig))
    return JSONResponse(
        status_code=409,
        content={
            "success": False,
            "message": "This action violates a data integrity constraint (e.g. duplicate or referenced record).",
            "detail": None,
        },
    )


@app.exception_handler(SQLAlchemyError)
async def sqlalchemy_error_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:
    logger.exception("Unhandled SQLAlchemyError on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=503,
        content={"success": False, "message": "A database error occurred.", "detail": None},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"success": False, "message": "Internal server error.", "detail": None},
    )


@app.get("/health", tags=["Health"])
async def health_check():
    db_ok = await check_db_connection()
    return {
        "success": db_ok,
        "message": "OK" if db_ok else "Database unavailable",
        "data": {"database": "connected" if db_ok else "disconnected"},
    }


# --- Routers ---
app.include_router(auth_router, prefix="/api/v1/auth", tags=["Auth"])
app.include_router(rbac_router, prefix="/api/v1", tags=["RBAC"])
app.include_router(users_router, prefix="/api/v1/users", tags=["Users"])