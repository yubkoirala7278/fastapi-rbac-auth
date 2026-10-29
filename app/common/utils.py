import re
import unicodedata
import uuid
from datetime import datetime, timezone


def slugify(value: str) -> str:
    """
    Convert a string into a URL-safe slug.
    e.g. "eSifarish Request 2026!" -> "esifarish-request-2026"
    """
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^\w\s-]", "", value).strip().lower()
    return re.sub(r"[-\s]+", "-", value)


def is_valid_uuid(value: str) -> bool:
    """
    Safely check whether a string is a valid UUID (any version).
    Useful for validating path params before hitting the database.
    """
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, AttributeError, TypeError):
        return False


def utc_now() -> datetime:
    """Timezone-aware current UTC timestamp."""
    return datetime.now(timezone.utc)


def normalize_str(value: str | None) -> str | None:
    """Trim whitespace and collapse internal whitespace runs; None-safe."""
    if value is None:
        return None
    return re.sub(r"\s+", " ", value.strip()) or None


def mask_email(email: str) -> str:
    """
    Mask an email for logs/notifications, e.g. 'yubraj@example.com' -> 'yu***@example.com'.
    """
    try:
        local, domain = email.split("@", 1)
    except ValueError:
        return email
    visible = local[:2]
    return f"{visible}{'*' * max(len(local) - 2, 1)}@{domain}"


def chunk_list(items: list, size: int) -> list[list]:
    """Split a list into chunks of at most `size` items each."""
    return [items[i : i + size] for i in range(0, len(items), size)]


def bool_from_query(value: str | bool | None, default: bool = False) -> bool:
    """
    Normalize a query-param-ish value ('true', '1', 'yes', True, ...) into bool.
    """
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "y"}