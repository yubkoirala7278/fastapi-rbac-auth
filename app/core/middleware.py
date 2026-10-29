import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("app.request")


class RequestContextMiddleware(BaseHTTPMiddleware):
    """
    - Assigns a unique request_id to every request (also returned in the
      X-Request-ID response header, for client-side correlation).
    - Logs method, path, status code, and duration for every request.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id

        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.perf_counter() - start) * 1000
            logger.exception(
                "request_id=%s %s %s failed after %.2fms",
                request_id, request.method, request.url.path, duration_ms,
            )
            raise

        duration_ms = (time.perf_counter() - start) * 1000
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "request_id=%s %s %s -> %s (%.2fms)",
            request_id, request.method, request.url.path, response.status_code, duration_ms,
        )
        return response