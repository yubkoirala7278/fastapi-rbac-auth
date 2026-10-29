from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Central application configuration.
    Values are loaded from environment variables / .env file.
    """

    # --- App ---
    APP_NAME: str = "eSifarish API"
    APP_ENV: str = "development"
    DEBUG: bool = True

    # --- Database ---
    DB_CONNECTION: str

    # --- JWT / Auth ---
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_DELTA: int = 900  # seconds (access token)
    REFRESH_TOKEN_EXPIRATION_DELTA: int = 604800  # seconds (refresh token)

    # --- Rate limiting ---
    RATE_LIMIT_DEFAULT: str = "100/minute"
    RATE_LIMIT_STORAGE_URI: str = "memory://"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """
    Cached settings instance so we don't re-parse the .env file
    on every import / dependency injection call.
    """
    return Settings()


settings = get_settings()