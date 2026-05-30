# Backend Global Performance Report

## Scope

Audited and optimized backend-wide FastAPI performance symptoms:

- slow startup
- slow `/health`
- slow `/docs`
- slow admin pages
- Windows `uvicorn --reload` overhead
- blocking startup operations
- sync SQLAlchemy inside async routes

## Changes Implemented

### OpenAI Import And Startup Cost

Updated:

- `app/ai/__init__.py`
- `app/ai/startup_validation.py`
- `app/routes/openai_diagnostic.py`
- `app/services/chat_service.py`
- `app/config/settings.py`

Changes:

- Made `app.ai` package exports lazy.
- Deferred OpenAI SDK import for chat until the first chat request.
- Deferred OpenAI SDK import for `/test-openai` until that endpoint is called.
- Removed eager `OpenAIService()` construction during `chat_service` import.
- Changed startup OpenAI validation to check configuration only by default.
- Added `OPENAI_STARTUP_CLIENT_CHECK=false` setting support.
  - If set to `true`, startup will initialize an `AsyncOpenAI` client as before.
  - Default is faster and avoids OpenAI SDK startup overhead on `/health`, `/docs`, and non-AI routes.

### Health Endpoint

Updated:

- `app/services/health_service.py`
- `app/routes/health.py`

Changes:

- Converted `/health` route from `async def` to `def`.
- Cached the health response with a one-entry `lru_cache`.
- Kept the existing response shape, including email configuration summary.

### Profiling Tools

Added:

- `tools/profile_backend_startup.py`
- `tools/profile_backend_requests.py`

These are lightweight local scripts for measuring startup segments and request-level costs.

## Startup Profile

Before global optimization:

| Step | Time |
| --- | ---: |
| settings import | 797.49 ms |
| `get_settings()` | 0.22 ms |
| `app.main` import / app creation | 11061.15 ms |
| JWT validation | 0.01 ms |
| SMTP validation | 0.43 ms |
| OpenAI validation | 1871.32 ms |
| `init_db()` | 214.16 ms |
| health response construction | 0.11 ms |
| close DB | 2.15 ms |

After global optimization:

| Step | Time |
| --- | ---: |
| settings import | 473.24 ms |
| `get_settings()` | 0.17 ms |
| `app.main` import / app creation | 2765.90 ms |
| JWT validation | 0.01 ms |
| SMTP validation | 0.40 ms |
| OpenAI validation | 0.45 ms |
| `init_db()` | 180.18 ms |
| health response construction | 0.11 ms |
| close DB | 1.74 ms |

## Biggest Bottlenecks Found

### 1. OpenAI SDK Imported During App Startup

The initial import-time profile showed the OpenAI SDK and generated OpenAI type modules being imported before any OpenAI endpoint or chat request:

- `app.ai.startup_validation`
- `app.ai.__init__`
- `app.ai.openai_service`
- `app.services.chat_service`
- `app.routes.openai_diagnostic`
- `openai.types...`

Impact:

- Added several seconds to backend import/startup on Windows.
- Slowed first access to `/docs` and `/health` because the app had not finished starting.

Fix:

- Lazy imports and lazy service construction.

### 2. OpenAI Startup Client Initialization

Previous behavior:

- Startup validation created an `AsyncOpenAI` client.
- It did not make a network request, but importing and initializing the SDK was still expensive.

Fix:

- Startup now validates the presence of `OPENAI_API_KEY` only by default.
- Optional client initialization remains available with:

```env
OPENAI_STARTUP_CLIENT_CHECK=true
```

### 3. `/docs` First Render

Measured:

| Operation | Time |
| --- | ---: |
| OpenAPI first generation | 926.95 ms |
| OpenAPI cached generation | 0.01 ms |

Cause:

- FastAPI generates a large OpenAPI schema for 46 paths the first time `/docs` or `/openapi.json` needs it.
- This is normal, but it is visible during development.

Recommendation:

- Do not judge steady-state backend speed from the first `/docs` load after startup.
- In production, disable docs unless needed.
- For development, first `/docs` load will remain slower than `/health`.

### 4. `uvicorn --reload` On Windows

Measured controlled startup to first healthy `/health`:

| Mode | Time To Healthy |
| --- | ---: |
| reload disabled | 4559 ms |
| reload enabled | 6997 ms |

Finding:

- `--reload` adds about 2.4 seconds in this local Windows test.
- Uvicorn reload watches the backend directory and starts a reloader parent plus child server process.
- On Windows, process startup and file watching are noticeably slower.

Recommendation:

- Use `--reload` only during active backend development.
- For testing frontend/backend integration speed, run without reload:

```powershell
uvicorn app.main:app --port 8001
```

### 5. SQLite Startup Work

`init_db()` currently:

- calls `Base.metadata.create_all()`
- seeds default pronunciation exercises
- seeds default speaking challenges
- runs SQLite schema upgrade/index creation logic

Measured:

- about 180-220 ms locally.

This is not the biggest bottleneck after OpenAI lazy-loading, but it still runs on every reload child startup.

Recommendation:

- Keep this for development.
- For production, move schema changes to migrations and run seed tasks separately.

## Request-Level Profile

Measured locally:

| Operation | Time |
| --- | ---: |
| health first | 0.16 ms |
| health cached | 0.00 ms |
| OpenAPI first generation | 926.95 ms |
| OpenAPI cached generation | 0.01 ms |

Conclusion:

- `/health` itself is fast.
- Slow health perception usually means the server is still starting or reload is restarting.
- `/docs` first load is dominated by OpenAPI schema generation.

## Async Architecture Audit

Current pattern:

- Many routes are declared `async def`.
- Several call synchronous SQLAlchemy sessions and blocking DB methods.

Risk:

- Blocking sync DB work inside `async def` can block the event loop.
- This is most visible under concurrent requests.

Already improved in prior admin pass:

- DB-heavy admin routes were converted to regular `def` handlers so FastAPI can run them in the threadpool.

Remaining recommendation:

- Audit non-admin routes next:
  - chat
  - recommendations
  - learning analytics
  - fluency dashboard
  - pronunciation
  - achievements
  - speaking challenges
  - vocabulary notebook

Safe options:

1. Convert sync-DB route handlers to `def` when they do not need true async behavior.
2. Keep `async def` only around real async work, such as OpenAI calls.
3. For mixed routes, isolate blocking DB sections with threadpool execution or move to an async SQLAlchemy engine in a larger refactor.

## Middleware Audit

Middleware stack:

- CORS middleware
- Admin authorization middleware
- Static file mount

Admin middleware:

- Checks admin paths only.
- Decodes JWT for `/admin/*` and `/api/v1/admin/*`.
- Does not affect `/health`.

No recursive scans or heavy middleware work were found.

## Logging Audit

Logging configuration is simple:

- `logging.basicConfig(...)`
- no file logging
- no recursive setup

No major startup overhead found.

OpenAI request logging can be verbose during chat requests, but it is not a startup or health bottleneck after lazy loading.

## SQLite Audit

Already improved in the admin pass:

- WAL mode
- normal synchronous mode
- memory temp store
- admin-focused indexes

Remaining SQLite limitations:

- Limited write concurrency.
- Admin analytics can still contend with active writes.
- JSON metadata queries are limited compared to PostgreSQL `jsonb`.
- Full-text search is not optimized yet.

Recommendation:

- SQLite is acceptable for local development.
- PostgreSQL is strongly recommended for staging/production.

## Startup Bottleneck Summary

Fixed:

- Eager OpenAI SDK imports.
- OpenAI client startup initialization.
- Chat OpenAI service construction during import.
- OpenAI diagnostic SDK import during app import.
- Health response repeated recomputation.

Still present:

- FastAPI/OpenAPI/Pydantic import cost.
- SQLAlchemy model/session import cost.
- `init_db()` schema/seed work.
- Windows process and reload overhead.
- First `/docs` OpenAPI schema generation.

## Estimated Speed Improvements

Measured startup segment improvements:

- `app.main` import/app creation:
  - before: 11061.15 ms
  - after: 2765.90 ms
  - improvement: about 75%

- OpenAI startup validation:
  - before: 1871.32 ms
  - after: 0.45 ms
  - improvement: effectively removed from startup path

- Time to healthy without reload:
  - measured: 4559 ms

- Time to healthy with reload:
  - measured: 6997 ms

## Validation

Passed:

```powershell
.venv\Scripts\python.exe -m compileall app tools
```

Profiling commands passed:

```powershell
.venv\Scripts\python.exe tools\profile_backend_startup.py
.venv\Scripts\python.exe tools\profile_backend_requests.py
```

Controlled uvicorn checks passed on temporary ports:

- no reload: port `8011`
- reload: port `8012`

## Production Recommendations

1. Run production without `--reload`.
2. Use PostgreSQL instead of SQLite.
3. Disable docs in production by setting `DEBUG=false`.
4. Keep `OPENAI_STARTUP_CLIENT_CHECK=false` unless startup-time OpenAI client validation is explicitly required.
5. Move schema mutation out of application startup and into migrations.
6. Convert sync-DB `async def` routes to regular `def` or adopt async SQLAlchemy consistently.
7. Add request timing middleware for local profiling, disabled by default in production.
8. Add a lightweight `/ready` endpoint if production readiness needs DB checks, while keeping `/health` instant.

