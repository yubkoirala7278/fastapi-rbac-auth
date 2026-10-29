# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

Async FastAPI + SQLAlchemy 2.0 (asyncpg) + PostgreSQL 17, Python 3.13+. A local `venv/` exists (`venv\Scripts\activate` on Windows). Config comes from `.env` (copy `.env.example`); `DB_CONNECTION` and `JWT_SECRET` are required or the app won't import.

```bash
pip install -r requirements.txt
alembic upgrade head                                  # apply migrations
alembic revision --autogenerate -m "<message>"        # new migration (see note on env.py below)
python -m app.database.seed                           # idempotent: permissions, Super Admin role, admin user
uvicorn app.main:app --reload                         # dev server; docs at http://localhost:8000/docs
```

`Dockerfile` and `docker-compose.yml` are in the project root (`docker compose up -d --build`). The compose file has no Postgres service — `DB_CONNECTION` must point to an external DB reachable from the container; for a Postgres on the host machine use `host.docker.internal` (compose maps it via `host-gateway`), and `localhost` when running uvicorn directly on the host. Run migrations/seed inside with `docker compose exec app alembic upgrade head` / `docker compose exec app python -m app.database.seed`, or set `RUN_MIGRATIONS=true` to migrate on start (`docker-entrypoint.sh`). The container is `read_only` with `cap_drop: ALL` — anything that writes to disk must use `/tmp` (tmpfs). Worker count and trusted proxy IPs come from `WEB_CONCURRENCY` / `FORWARDED_ALLOW_IPS`, which uvicorn reads natively.

There is no test suite, linter, or formatter configured.

The app fails startup (raises in `lifespan`) if the DB is unreachable.

## Architecture

### Module layout and layering

Each feature lives in `app/modules/<name>/` with the same files: `router.py` → `controller.py` → `repository.py`, plus `models.py` (SQLAlchemy) and `dtos.py` (Pydantic). Routers are thin: they instantiate a controller per request (`XController(db).method(...)`) and return its result. Controllers hold the business logic and build the response envelope. Repositories hold all queries. New routers must be registered in `app/main.py` under `/api/v1/...`.

- `users` has no `models.py` — it operates on the `User` model from `app/modules/auth/models.py`.
- There are two different `UserRepository` classes: `auth/repository.py` (standalone, filters `is_active=True`, used for login/current-user) and `users/repository.py` (extends `BaseRepository`, used for admin CRUD). Pick the right one.

### Transactions

`get_db_session` (`app/database/session.py`, injected via the `DbSession` annotated type in `app/dependencies.py`) commits on successful request completion and rolls back on any exception. Repositories therefore only `flush()`, never `commit()`. Seeders are the exception: they open their own `AsyncSessionLocal()` and commit explicitly.

### BaseRepository (`app/core/base_repository.py`)

Generic CRUD/list for repositories. Subclasses set `model`, `eager_load_options`, `search_columns`, and optionally `soft_delete = False`. Key behaviors:
- `_base_select()` applies eager-load options and filters `deleted_at IS NULL` when the model has that column (`SoftDeleteMixin`). Use it as the starting point for custom queries.
- `update()` skips `None` values — it cannot be used to null out a field.
- `delete()` calls `assert_no_dependents()` first (override it to raise `DependencyExistsError` when child rows exist), then soft-deletes if possible, else hard-deletes.
- `list()` handles search (ILIKE across `search_columns`) + pagination ordered by `created_at desc`.

### Relationships are `lazy="raise"`

All ORM relationships (`User.roles`, `Role.permissions`, etc.) use `lazy="raise"` to prevent `MissingGreenlet` errors in async code. Any relationship you touch must be eager-loaded (`selectinload`) in the query, typically via the repository's `eager_load_options`. Modify M2M associations through repository methods operating on the association tables (e.g. `RoleRepository.add_permissions`), not by mutating ORM collections — this applies even to freshly constructed objects (see `rbac_seeder.py` docstring). Because those writes bypass the ORM, an object already in the session keeps its stale collection; re-read it with `.execution_options(populate_existing=True)` (as `RoleRepository.get_by_id_with_permissions` does) before returning it.

### Models

Compose from mixins in `app/database/base.py`: `UUIDPrimaryKeyMixin`, `TimestampMixin`, `SoftDeleteMixin`. Currently `Role` is soft-deletable; `User` and `Permission` are not (hard delete). When adding a new models module, import its models in `alembic/env.py` so autogenerate sees them. Cross-module relationships use string references (e.g. `secondary="user_roles"`) to avoid circular imports between modules.

### Auth & RBAC

- JWT access + refresh tokens (`app/core/security.py`); passwords hashed with argon2 via pwdlib. Refresh tokens are persisted by `jti` in `refresh_tokens` and rotated on `/refresh` (old one revoked). Changing a password sets `password_changed_at`, which invalidates access tokens issued earlier and deletes the user's refresh tokens.
- Logout requires the Bearer access token plus the refresh token in the body (must belong to the same user). It revokes the refresh token and adds the access token's `jti` to `revoked_access_tokens`, which `get_auth_context` checks on every authenticated request; expired rows are purged on each logout.
- `CurrentUser` (from `auth/controller.py`) is the dependency for "logged-in user"; `CurrentAuth` gives an `AuthContext` with both the user and the decoded access-token payload.
- Authorization uses permission codes of the form `"<module>:<action>"` (e.g. `user:create_user`). Protect a route with `dependencies=[Depends(require_permission("module:action"))]` from `app/modules/rbac/controller.py`; it implies authentication.
- Assignments use a single "sync" endpoint that replaces the whole set: `PUT /roles/{id}/permissions` (`permission_ids`) and `PUT /users/{id}/roles` (`role_ids`); missing IDs are removed, new ones added, `[]` clears all, unknown IDs 404 with no change. Users cannot change their own roles. Follow this pattern for new many-to-many assignments.
- When adding a module, add its permissions to `PERMISSION_CATALOG` in `app/database/seeders/rbac_seeder.py` and re-run the seeder — Super Admin is granted every catalog permission.

### Responses and errors

- Single-object endpoints return `ApiResponse[T]` (`{success, message, data}`); list endpoints return `PaginatedResponse[T]` built with `PaginatedResponse.from_result(result, serializer=Dto.model_validate)`. List endpoints take `params: PaginationParams = Depends(pagination_params)` (`page`, `per_page` up to 500 or `"all"`, `search`).
- Raise domain exceptions from `app/core/exceptions.py` (`NotFoundError`, `ConflictError`, `ForbiddenError`, ...); global handlers in `app/main.py` convert them to `{success: false, message, detail}`. `IntegrityError` maps to 409, other `SQLAlchemyError` to 503.

### Cross-cutting

Rate limiting via slowapi (`app/core/rate_limiter.py`, in-memory by default; default limit from `RATE_LIMIT_DEFAULT`, per-route with `@limiter.limit(...)` which requires a `request: Request` parameter). `RequestContextMiddleware` adds an `X-Request-ID` header and logs each request. CORS allows all origins only when `DEBUG=True`.
