# Backend Admin Performance Report

## Scope

Optimized slow-loading FastAPI admin pages and the backing admin analytics/user APIs while keeping existing behavior unchanged.

Admin pages reviewed:

- `/admin/dashboard`
- `/admin/users`
- `/admin/conversations`
- `/admin/openai-usage`
- `/api/v1/admin/analytics/dashboard`
- `/api/v1/admin/users`

## Changes Implemented

### Admin Analytics

Updated `app/services/admin_analytics_service.py`.

- Replaced full-table ORM loading with SQL aggregate queries.
- Removed the most expensive pattern:
  - before: `self.db.query(User).all()`, `Message.all()`, `Conversation.all()`, and multiple other full table loads.
  - now: targeted `COUNT`, `SUM`, `GROUP BY`, date trend, and token aggregate queries.
- Added a short 20-second in-process cache for admin dashboard analytics.
- Moved OpenAI usage token totals to SQL aggregation.
- Reduced Python-side processing to the data that still needs JSON metadata inspection, mainly recent user-message metadata.
- Reused already computed totals in system-health counts.

### Admin Users

Updated `app/services/admin_user_service.py`.

- Removed N+1 summary queries in user listing.
- `list_users()` now uses:
  - one count query for pagination total.
  - one user page query.
  - batched aggregate queries for conversation counts.
  - batched aggregate queries for message counts.
  - batched aggregate queries for last activity timestamps.
- Avoids loading all matching users just to count them.

### Route Execution

Updated:

- `app/routes/admin_analytics.py`
- `app/routes/admin_users.py`
- `app/routes/admin_dashboard.py`

Changes:

- Converted DB-heavy admin API route handlers from `async def` to regular `def`.
- This lets FastAPI run synchronous SQLAlchemy work in the threadpool instead of doing blocking DB work directly in the event loop.
- Converted GET-only HTML admin routes to regular `def` for the same reason.

### Template Rendering

Updated `app/routes/admin_dashboard.py`.

- Enabled Jinja template caching:
  - before: `cache_size=0`
  - after: `cache_size=100`

This avoids recompiling admin templates on every request.

### SQLite Performance

Updated `app/database/session.py`.

Added SQLite pragmas on connection:

- `PRAGMA journal_mode=WAL`
- `PRAGMA synchronous=NORMAL`
- `PRAGMA temp_store=MEMORY`

Added startup-created indexes for admin-heavy filters and aggregations:

- `users(created_at)`
- `users(is_active)`
- `messages(created_at)`
- `messages(role, created_at)`
- `messages(user_id, created_at)`
- `messages(conversation_id, created_at)`
- `conversations(created_at)`
- `conversations(user_id, updated_at)`
- `speaking_challenge_completions(completed_at)`
- `speaking_challenge_completions(user_id, client_session_id)`
- `vocabulary_notebook_entries(created_at)`
- `vocabulary_notebook_entries(mastery_status)`
- `vocabulary_review_sessions(created_at)`
- `placement_assessment_sessions(status)`
- `pronunciation_practice_sessions(status)`

## Profile Results

Local database size at test time:

- users: 25
- messages: 40
- conversations: 15
- challenge completions: 2
- vocabulary entries: 6

Measured backend service/template timings:

| Path / Operation | Result |
| --- | ---: |
| Admin analytics cold generation | 91.27 ms |
| Admin analytics cached generation | 0.01 ms |
| Admin users list | 15.26 ms |
| `admin/dashboard.html` render | 8.66 ms |
| `admin/users.html` render | 5.16 ms |
| `admin/conversations.html` render | 4.67 ms |
| `admin/openai_usage.html` render | 4.73 ms |

Earlier pre-route-threadpool timing after the first optimization pass:

- analytics cold: 100.65 ms
- analytics cached: 0.02 ms
- admin users list: 14.76 ms

The largest practical gain is not visible on the tiny local dataset. It comes from avoiding memory growth and response-time growth as message/user tables grow.

## Slowest Routes

Current slowest backend operation:

1. `/api/v1/admin/analytics/dashboard`
   - Still the broadest endpoint.
   - Computes dashboard, users, engagement, conversations, learning progress, OpenAI token usage, and trends.
   - Now SQL-aggregated and cached, but it remains the main admin data endpoint.

2. `/api/v1/admin/users`
   - Much improved by removing N+1 summary queries.
   - Search with multiple `ILIKE` filters can still become expensive on large SQLite datasets.

3. HTML pages: `/admin/dashboard`, `/admin/users`, `/admin/conversations`, `/admin/openai-usage`
   - These are not the main bottleneck.
   - They render quickly and load data through the analytics endpoint.

## Expensive Query Patterns Fixed

- Full table scans into ORM objects for admin analytics.
- Python-side counting and filtering across entire tables.
- Repeated count queries per user in admin user listing.
- Repeated latest-message/latest-conversation queries per user.
- Recompiling Jinja templates on every admin page request.

## Async / Sync Audit

The backend uses synchronous SQLAlchemy sessions.

Issue found:

- Several admin routes were `async def` while directly calling synchronous SQLAlchemy service methods.
- That can block the event loop during admin requests.

Fix applied:

- Converted DB-heavy admin handlers to regular `def` so FastAPI can run them in the threadpool.

Remaining note:

- Broader backend APIs still mix `async def` routes with synchronous SQLAlchemy calls. This pass focused on admin routes only.

## OpenAI / Startup Audit

- Admin page rendering does not call OpenAI.
- OpenAI validation happens during FastAPI startup.
- The validation initializes an `AsyncOpenAI` client and does not send an API request.
- It is not blocking admin page rendering after startup.

Startup warning still present:

- SMTP configuration is incomplete:
  - `SMTP_HOST`
  - `SMTP_USERNAME`
  - `SMTP_PASSWORD`
  - `SMTP_FROM_EMAIL`

## SQLite Limitations

SQLite is acceptable for local development and small admin datasets, but it will become a bottleneck when:

- messages grow into tens or hundreds of thousands of rows.
- admin analytics are requested frequently.
- multiple users/admins read and write at the same time.
- JSON metadata needs to be queried deeply.
- search/filter operations need indexed full-text behavior.

The WAL and index changes help, but SQLite still has limited write concurrency and less sophisticated query planning than PostgreSQL.

## PostgreSQL Recommendation

Migrating to PostgreSQL would significantly improve admin scalability if this app is expected to have real production traffic.

Benefits:

- Better concurrent reads/writes.
- Better indexing options.
- Better JSON querying with `jsonb`.
- Better aggregation performance on growing analytics tables.
- Cleaner migration path for materialized analytics views.
- Better full-text search for admin user/conversation search.

Recommendation:

- Keep SQLite for local development.
- Use PostgreSQL for staging/production before the admin dataset grows meaningfully.

## Estimated Speed Gains

On the current small dataset, timing improvements are modest because there is not much data.

Expected gains as data grows:

- Admin analytics memory usage: significantly lower because full ORM tables are no longer loaded.
- Admin analytics cold response: likely 2x-10x faster on larger datasets depending on row count and indexes.
- Admin analytics repeated response: near-instant within the 20-second cache window.
- Admin user list: from O(page size * summary queries) to a small fixed number of batched queries.
- Template rendering: avoids repeated template compilation.

## Validation

Passed:

- `python -m compileall app`
- Admin analytics service response generation.
- Admin users service listing.
- Admin template rendering profile.

Could not run:

- `pytest`, because `pytest` is not installed in the backend virtual environment.

Health check note:

- A controlled startup check detected that port `8001` was already occupied by the running backend, while `/api/v1/health` responded successfully during the check.

## Remaining Architectural Work

1. Add real benchmark tests with `pytest-benchmark` or a lightweight route timing test suite.
2. Add request timing middleware for admin routes.
3. Split `/api/v1/admin/analytics/dashboard` into smaller endpoint-specific payloads if pages only need subsets.
4. Consider persisted/materialized daily analytics tables for production.
5. Move production database to PostgreSQL.
6. Add full-text indexed admin search.
7. Review non-admin async routes that still call synchronous SQLAlchemy directly.

