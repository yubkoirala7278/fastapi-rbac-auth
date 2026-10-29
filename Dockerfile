# syntax=docker/dockerfile:1

ARG PYTHON_VERSION=3.13

# =============================================================================
# Builder: install Python dependencies into an isolated virtualenv
# =============================================================================
FROM python:${PYTHON_VERSION}-slim-bookworm AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install -r requirements.txt


# =============================================================================
# Runtime: minimal image with only the virtualenv and application code
# =============================================================================
FROM python:${PYTHON_VERSION}-slim-bookworm AS runtime

LABEL org.opencontainers.image.title="esifarish-api" \
      org.opencontainers.image.description="eSifarish backend API (Kathmandu Metropolitan City)"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    # Read natively by uvicorn: worker count and trusted proxy IPs.
    WEB_CONCURRENCY=4 \
    FORWARDED_ALLOW_IPS="127.0.0.1" \
    RUN_MIGRATIONS=false

# Non-root application user.
RUN groupadd --system --gid 10001 appuser \
    && useradd --system --uid 10001 --gid appuser --no-create-home --shell /usr/sbin/nologin appuser

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv

COPY --chown=appuser:appuser docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
# Strip CRLF in case the script was checked out on Windows.
RUN sed -i 's/\r$//' /usr/local/bin/docker-entrypoint.sh \
    && chmod +x /usr/local/bin/docker-entrypoint.sh

COPY --chown=appuser:appuser alembic.ini ./alembic.ini
COPY --chown=appuser:appuser alembic/ ./alembic/
COPY --chown=appuser:appuser app/ ./app/

USER appuser

EXPOSE 8000

# Liveness check without needing curl in the image.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else 1)"]

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
