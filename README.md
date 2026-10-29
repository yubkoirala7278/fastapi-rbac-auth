# eSifarish Backend

Backend API for eSifarish (Kathmandu Metropolitan City).

## Tech Stack

- **Framework:** FastAPI
- **Database:** PostgreSQL (async, via SQLAlchemy + asyncpg)
- **Auth:** JWT access + refresh tokens
- **Containerization:** Docker

---

## Requirements

- **Python 3.13+** (matches the version used in `Dockerfile`)
- **PostgreSQL 17+**
- pip (bundled with Python) — no specific version required

## Getting Started (Local Development)

### 1. Create a virtual environment (if you don't want to use Docker)

```bash
python -m venv venv
```

Activate it:

```bash
# Windows
venv\scripts\activate

# Linux / macOS
source venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment variables

Create a `.env` file in the project root by copying the example file:

```bash
cp .env.example .env
```

Then create a new PostgreSQL database and update the `.env` file with your
connection details (`DB_CONNECTION`, JWT secrets, etc.).

### 4. Run database migrations

Applies all Alembic migrations to bring the database schema up to date.

```bash
alembic upgrade head
```

### 5. Seed the database

Populates the initial permission catalog, the Super Admin role, and the
default admin user. Safe to re-run — each step is idempotent.

```bash
python -m app.database.seed
```

### 6. Run the development server

```bash
uvicorn app.main:app --reload
```

The API will be available at `http://localhost:8000`, with interactive
docs at `http://localhost:8000/docs`.

---

## Docker Setup

> **Note:** This setup does not include a PostgreSQL container. The app
> connects to an external/existing PostgreSQL instance — make sure
> `DB_CONNECTION` in your `.env` points to a database that's reachable
> from inside the container. To reach a PostgreSQL running on your host
> machine, use `host.docker.internal` as the host, e.g.
> `postgresql+asyncpg://<user>:<password>@host.docker.internal:5432/<db>`
> (use `localhost` instead when running uvicorn directly on the host).

All commands below are run from the project root (where `Dockerfile` and
`docker-compose.yml` live).

Build and start in the background (rebuilds when code or the Dockerfile change):

```bash
docker compose up -d --build
```

Follow logs / stop:

```bash
docker compose logs -f app
docker compose down
```

Open a shell inside the running container:

```bash
docker compose exec app sh
```

Run database migrations inside the container (the external database must
already exist and be reachable):

```bash
docker compose exec app alembic upgrade head
```

Alternatively, set `RUN_MIGRATIONS=true` to apply migrations automatically
on container start (runs once, before the workers start).

Seed the database inside the container:

```bash
docker compose exec app python -m app.database.seed
```

### Container options

These can be set in the shell or in `.env` (compose reads both):

| Variable | Default | Description |
|---|---|---|
| `APP_PORT` | `8000` | Host port mapped to the container |
| `WEB_CONCURRENCY` | `4` | Number of uvicorn worker processes |
| `FORWARDED_ALLOW_IPS` | `127.0.0.1` | IPs trusted for `X-Forwarded-*` headers — set to your reverse proxy's IP (or `*` if only reachable through it) |
| `RUN_MIGRATIONS` | `false` | Run `alembic upgrade head` on container start |

The container runs as a non-root user with a read-only filesystem, all
Linux capabilities dropped, and `tini` as PID 1 for clean shutdowns.

> **Note:** rate limits use in-memory storage by default, so each worker
> keeps its own counters. For accurate limits across workers/instances, set
> `RATE_LIMIT_STORAGE_URI` to a Redis URI.

---

## Environment Variables

Create a new PostgreSQL database, then set the following in `.env`
(see `.env.example` for the full list):

| Variable | Description |
|---|---|
| `DB_CONNECTION` | Async PostgreSQL connection string (`postgresql+asyncpg://...`) |
| `JWT_SECRET` | Secret key used to sign access/refresh tokens |
| `JWT_ALGORITHM` | JWT signing algorithm (e.g. `HS256`) |
| `JWT_EXPIRATION_DELTA` | Access token lifetime, in seconds |
| `REFRESH_TOKEN_EXPIRATION_DELTA` | Refresh token lifetime, in seconds |

---

## Project Structure

```
app/
  core/           # Shared utilities: security, exceptions, base repository
  database/       # DB session, base models, seeders
  modules/
    auth/         # Authentication (login, tokens, current user)
    rbac/         # Roles & permissions
    users/        # User account CRUD
  main.py         # FastAPI app entrypoint
alembic/          # Migration scripts
Dockerfile
docker-compose.yml
docker-entrypoint.sh  # Optional migrations, then starts uvicorn
requirements.txt
.env
```