# LearnPSC FastAPI Backend Audit

Date: 2026-05-29  
Scope: `C:\Users\user\chazy project\Aboki_backend`  
Mode: Inspection only. No backend code was modified.

## Executive Summary

The backend is a functional FastAPI application with a broad learning feature set: authentication, chat, learning analytics, pronunciation practice, speaking challenges, vocabulary notebook, placement assessment, achievements, recommendations, and a server-rendered admin dashboard.

It is not yet frontend-integration-ready for the current LearnPSC web app without an API contract alignment pass. The largest gaps are route naming mismatches, missing frontend-oriented endpoints such as `/auth/me`, missing onboarding and lessons/course APIs, inconsistent response envelopes, no real audio upload/transcription pipeline, and remaining legacy Chazy branding.

## A. Project Structure

### Root Layout

| Area | Status | Notes |
| --- | --- | --- |
| `main.py` | Present | Root entrypoint likely imports/runs `app.main`. |
| `app/main.py` | Present | Creates FastAPI app, lifespan startup/shutdown, CORS, static files, admin middleware, API router. |
| `app/routes` | Present | Feature routers plus HTML admin dashboard routes. |
| `app/models` | Present | SQLAlchemy 2 typed ORM models. |
| `app/schemas` | Present | Pydantic v2 schemas grouped by feature. |
| `app/services` | Present | Business logic layer for auth, chat, analytics, admin, learning features. |
| `app/database` | Present | Engine/session setup and `init_db()` schema creation/upgrade logic. |
| `app/config` | Present | Environment settings via `pydantic-settings`. |
| `app/ai` | Present | OpenAI client/service, fallback response engine, English learning prompt pipeline. |
| `app/dependencies` | Present | User bearer auth and admin auth dependencies. |
| `app/middleware` | Present | Admin authorization middleware. |
| `app/templates/admin` | Present | Jinja admin pages. |
| `app/static/admin` | Present | Admin CSS/JS assets. |
| `tests` | Present | Startup security, auth authorization, admin security, email service tests. |

### Route Organization

All JSON API routers are mounted under `settings.api_v1_prefix`, currently `/api/v1`, through `app/routes/router.py`.

HTML admin dashboard routes and the OpenAI diagnostic route are mounted directly on the app:

- `/admin/*`
- `/test-openai`

### Database Layer

- ORM: SQLAlchemy 2.
- Session model: synchronous `SessionLocal`.
- Startup schema management: `Base.metadata.create_all()` plus ad hoc SQLite `ALTER TABLE` upgrades.
- Default database: `sqlite:///./chazy.db`.
- Migrations: no Alembic migration system found.

### AI Modules

- `app/ai/openai_service.py` uses `AsyncOpenAI` and the Responses API.
- The service validates configuration on startup and falls back to `temporary_response_engine` when OpenAI is unavailable.
- Prompts and defaults still reference the older English coach/Chazy product concept.

### Admin Modules

- Server-rendered Jinja admin dashboard.
- Admin API endpoints for analytics and user management.
- Admin auth supports bearer token or `chazy_admin_access` cookie.
- CSRF protection exists for admin mutation endpoints.

## B. API Endpoints

Base API prefix: `/api/v1`.

Status legend:

- Ready: usable now with minor frontend mapping.
- Partial: usable but missing expected behavior, polish, or contract alignment.
- Missing: not implemented for the requested LearnPSC frontend scope.
- Admin: intended for admin use.

### Health

| Method | Route | Auth | Request Schema | Response Schema | Status |
| --- | --- | --- | --- | --- | --- |
| GET | `/api/v1/health` | Public | None | `HealthResponse` | Ready |

### Auth

| Method | Route | Auth | Request Schema | Response Schema | Status |
| --- | --- | --- | --- | --- | --- |
| POST | `/api/v1/auth/signup` | Public | `SignUpRequest` | `AuthResponse` | Ready, route name mismatch with frontend `/register` |
| POST | `/api/v1/auth/signin` | Public | `SignInRequest` | `AuthResponse` | Ready, route name mismatch with frontend `/login` |
| POST | `/api/v1/auth/refresh` | Public | `RefreshTokenRequest` | `TokenResponse` | Ready |
| POST | `/api/v1/auth/forgot-password` | Public | `ForgotPasswordRequest` | `BasicResponse` | Ready |
| POST | `/api/v1/auth/reset-password` | Public | `ResetPasswordRequest` | `BasicResponse` | Ready |
| GET | `/api/v1/auth/profile/{user_id}` | Bearer + self | Path `user_id` | `UserRead` | Partial, frontend needs `/auth/me` or `/users/me` |
| PATCH | `/api/v1/auth/profile/{user_id}/response-length` | Bearer + self | `ResponseLengthPreferenceUpdate` | `UserRead` | Partial |
| DELETE | `/api/v1/auth/profile/{user_id}` | Bearer + self | Path `user_id` | `BasicResponse` | Ready |

Missing auth endpoints for frontend integration:

- `POST /api/v1/auth/logout`
- `GET /api/v1/auth/me`
- cookie-based user session endpoints, if the frontend will use HttpOnly cookies

### Users / Profile

There is no standalone `/users` router for regular users. User profile functionality currently lives under `/auth/profile/{user_id}`.

| Frontend Need | Backend Status |
| --- | --- |
| Current user profile | Partial through `/auth/profile/{user_id}` |
| Update general profile | Missing |
| Profile statistics | Partial through analytics/achievement endpoints |
| Settings | Missing |

### Chat / AI Conversation

| Method | Route | Auth | Request Schema | Response Schema | Status |
| --- | --- | --- | --- | --- | --- |
| POST | `/api/v1/chat/` | Bearer | `ChatRequest` | `ChatResponse` | Ready, response contract is backend-specific |
| POST | `/api/v1/chat/stream` | Bearer | `ChatRequest` | SSE stream | Partial, simulates streaming after full processing |
| GET | `/api/v1/chat/history` | Bearer | Query: `session_id`, `conversation_id`, `limit`, `offset` | `ConversationHistoryResponse` | Ready |
| GET | `/api/v1/chat/history/{conversation_id}` | Bearer | Path + query | `ConversationHistoryResponse` | Ready |

Notes:

- Backend overrides client `session_id` and `user_id` with authenticated user context.
- `ChatResponse` includes coaching fields: correction, explanation, reply, vocabulary, confidence tip, fluency score, guided session, and message IDs.
- Streaming is not true OpenAI token streaming; it returns word-level chunks after the full chat service completes.

### Onboarding

No onboarding endpoints were found.

| Frontend Need | Backend Status |
| --- | --- |
| Save onboarding preferences | Missing |
| Retrieve personalization profile | Missing |
| Generate onboarding-based plan | Partial through recommendations, but no onboarding storage |

### Lessons / Courses

No generic lesson/course endpoints were found.

Related learning APIs exist:

- Placement assessment
- Speaking challenges
- Pronunciation exercises
- Conversation scenarios
- Vocabulary notebook
- Recommendations

The frontend's course listing and lesson detail pages need new APIs or a mapping to existing learning modules.

### Pronunciation / Voice

| Method | Route | Auth | Request Schema | Response Schema | Status |
| --- | --- | --- | --- | --- | --- |
| GET | `/api/v1/pronunciation/words` | Bearer | Query: `difficulty`, `limit` | `list[PronunciationExerciseResponse]` | Ready |
| POST | `/api/v1/pronunciation/sessions` | Bearer | `PronunciationSessionCreate` | `PronunciationSessionResponse` | Ready |
| POST | `/api/v1/pronunciation/sessions/{practice_session_id}/attempts` | Bearer | `PronunciationAttemptCreate` | `PronunciationAttemptResponse` | Partial |
| GET | `/api/v1/pronunciation/progress` | Bearer | Query: `session_id`, `user_id` | `PronunciationProgressResponse` | Ready |

Voice gap:

- No `UploadFile` audio upload endpoint found.
- No transcription endpoint found.
- No real pronunciation scoring pipeline found.
- Attempts store `recorded_audio_url`, duration, and notes, then return scoring status/score fields.

### Speaking Challenges

| Method | Route | Auth | Request Schema | Response Schema | Status |
| --- | --- | --- | --- | --- | --- |
| GET | `/api/v1/speaking-challenges/daily` | Bearer | Query: `session_id`, `user_id`, `challenge_date` | `DailySpeakingChallengesResponse` | Ready |
| POST | `/api/v1/speaking-challenges/{challenge_id}/complete` | Bearer | `SpeakingChallengeCompletionCreate` | `SpeakingChallengeCompletionResponse` | Ready |
| GET | `/api/v1/speaking-challenges/streak` | Bearer | Query: `session_id`, `user_id` | `SpeakingChallengeStreakResponse` | Ready |
| POST | `/api/v1/speaking-challenges/streak/sync` | Bearer | `DailySpeakingStreakSyncCreate` | `BasicResponse` | Partial |

### Learning Analytics

| Method | Route | Auth | Request Schema | Response Schema | Status |
| --- | --- | --- | --- | --- | --- |
| GET | `/api/v1/learning-analytics/` | Bearer | Query: `session_id`, `user_id` | `LearningAnalyticsResponse` | Ready |
| GET | `/api/v1/fluency-dashboard/` | Bearer | Query: `session_id`, `user_id` | `FluencyDashboardResponse` | Ready |
| GET | `/api/v1/recommendations/personalized` | Bearer | Query: `session_id`, `user_id` | `PersonalizedRecommendationResponse` | Ready |

Frontend dashboard will likely need a consolidated `/dashboard` or `/analytics/dashboard` endpoint to avoid multiple parallel calls.

### Placement Assessment

| Method | Route | Auth | Request Schema | Response Schema | Status |
| --- | --- | --- | --- | --- | --- |
| POST | `/api/v1/placement-assessment/start` | Bearer | `PlacementAssessmentStartRequest` | `PlacementAssessmentStartResponse` | Ready |
| POST | `/api/v1/placement-assessment/{assessment_session_id}/answers` | Bearer | `PlacementAnswerSubmitRequest` | `PlacementAnswerFeedbackResponse` | Ready |
| GET | `/api/v1/placement-assessment/{assessment_session_id}` | Bearer | Path | `PlacementAssessmentStateResponse` | Ready |
| GET | `/api/v1/placement-assessment/{assessment_session_id}/result` | Bearer | Path | `PlacementAssessmentResultResponse` | Ready |

### Conversation Scenarios

| Method | Route | Auth | Request Schema | Response Schema | Status |
| --- | --- | --- | --- | --- | --- |
| GET | `/api/v1/conversation-scenarios/` | Bearer | None | `ConversationScenarioListResponse` | Ready |
| POST | `/api/v1/conversation-scenarios/sessions` | Bearer | `ScenarioSessionCreate` | `ScenarioSessionResponse` | Ready |
| POST | `/api/v1/conversation-scenarios/sessions/{scenario_session_id}/turns` | Bearer | `ScenarioTurnRequest` | `ScenarioTurnResponse` | Ready |

### Vocabulary Notebook

| Method | Route | Auth | Request Schema | Response Schema | Status |
| --- | --- | --- | --- | --- | --- |
| GET | `/api/v1/vocabulary-notebook/` | Bearer | Query filters | `VocabularyNotebookResponse` | Ready |
| POST | `/api/v1/vocabulary-notebook/` | Bearer | `VocabularyEntryCreate` | `VocabularyEntryResponse` | Ready |
| POST | `/api/v1/vocabulary-notebook/bookmark-from-conversation` | Bearer | `VocabularyBookmarkFromConversationRequest` | `VocabularyEntryResponse` | Ready |
| PATCH | `/api/v1/vocabulary-notebook/{entry_id}` | Bearer | `VocabularyEntryUpdate` | `VocabularyEntryResponse` | Ready |
| POST | `/api/v1/vocabulary-notebook/{entry_id}/review` | Bearer | `VocabularyReviewRequest` | `VocabularyEntryResponse` | Ready |
| GET | `/api/v1/vocabulary-notebook/stats` | Bearer | Query: `session_id`, `user_id` | `VocabularyNotebookStatsResponse` | Ready |
| POST | `/api/v1/vocabulary-notebook/review-sessions` | Bearer | `VocabularyReviewSessionCreate` | `VocabularyReviewSessionResponse` | Ready |
| GET | `/api/v1/vocabulary-notebook/review-sessions/{review_session_id}` | Bearer | Path | `VocabularyReviewSessionResponse` | Ready |
| POST | `/api/v1/vocabulary-notebook/review-sessions/{review_session_id}/submit` | Bearer | `VocabularyReviewSessionSubmit` | `VocabularyReviewSessionResponse` | Ready |

### Achievements / Gamification

| Method | Route | Auth | Request Schema | Response Schema | Status |
| --- | --- | --- | --- | --- | --- |
| GET | `/api/v1/achievements/` | Bearer | Query: `session_id`, `user_id` | `AchievementSummaryResponse` | Ready |
| POST | `/api/v1/achievements/evaluate` | Bearer | `AchievementEvaluateRequest` | `AchievementSummaryResponse` | Ready |

Missing gamification endpoints:

- Leaderboard
- XP ledger
- Daily missions
- Badge catalogue
- Profile-level gamification summary

### Admin API

| Method | Route | Auth | Request Schema | Response Schema | Status |
| --- | --- | --- | --- | --- | --- |
| GET | `/api/v1/admin/analytics/dashboard` | Admin bearer/cookie | Query: `window_days` | `AdminAnalyticsDashboardResponse` | Admin |
| GET | `/api/v1/admin/users/` | Admin bearer/cookie | Query: search/status/limit/offset | `AdminUserListResponse` | Admin |
| POST | `/api/v1/admin/users/admins` | Admin + CSRF | `AdminCreateRequest` | `AdminUserStatusResponse` | Admin |
| GET | `/api/v1/admin/users/{user_id}` | Admin bearer/cookie | Path | `AdminUserProfileResponse` | Admin |
| PATCH | `/api/v1/admin/users/{user_id}/status` | Admin + CSRF | `AdminUserStatusUpdate` | `AdminUserStatusResponse` | Admin |
| DELETE | `/api/v1/admin/users/{user_id}` | Admin + CSRF | Path | `AdminUserStatusResponse` | Admin |

### Admin Dashboard HTML

| Method | Route | Auth | Status |
| --- | --- | --- | --- |
| GET | `/admin` | Admin cookie/bearer | Admin |
| GET | `/admin/login` | Public | Admin |
| GET | `/admin/setup` | Public/setup-gated | Admin |
| POST | `/admin/setup` | Public/setup-gated | Admin |
| POST | `/admin/login` | Public | Admin |
| POST | `/admin/logout` | Admin + CSRF | Admin |
| GET | `/admin/dashboard` | Admin | Admin |
| GET | `/admin/users` | Admin | Admin |
| GET | `/admin/learning` | Admin | Admin |
| GET | `/admin/conversations` | Admin | Admin |
| GET | `/admin/openai-usage` | Admin | Admin |
| GET | `/admin/user-management` | Admin | Admin |

### AI Diagnostics

| Method | Route | Auth | Request Schema | Response Schema | Status |
| --- | --- | --- | --- | --- | --- |
| GET | `/test-openai` | Public | None | None declared | Partial/security concern |

This route is useful in development but should be disabled or admin-protected in production.

## C. Authentication System

### JWT Flow

- Access and refresh tokens are issued on signup/signin.
- Tokens are custom HMAC-SHA256 JWTs implemented in `TokenService`.
- Claims include `iss`, `sub`, `typ`, `iat`, `exp`, `jti`, `email`, and `role`.
- Access token expiry defaults to 30 minutes.
- Refresh token expiry defaults to 30 days.
- Issuer defaults to `chazy-api`.

### Refresh Token Flow

- Refresh tokens are stored server-side by SHA256 hash.
- Refresh token rotation is implemented.
- Reuse detection revokes all user refresh tokens.
- Expired/revoked tokens are rejected.

### Cookie vs Bearer Auth

- User API auth uses bearer tokens through `HTTPBearer`.
- Admin dashboard uses an HttpOnly cookie named `chazy_admin_access`.
- There is no cookie-based user auth flow for the web frontend yet.

### Permissions

- Standard user endpoints require active authenticated users.
- Self-profile enforcement exists for `/auth/profile/{user_id}`.
- Admin endpoints require `role == "admin"`.
- Admin mutating endpoints require CSRF validation.

### Password Hashing

- PBKDF2-HMAC-SHA256.
- 120,000 iterations.
- Per-password random 16-byte salt.
- Constant-time comparison with `hmac.compare_digest`.

### Auth Gaps

- No `/auth/me`.
- No `/auth/logout` for user sessions.
- No token audience claim.
- User auth is not yet cookie-ready.
- Product naming in issuer/cookies remains Chazy.

## D. Database

### ORM and Tables

ORM: SQLAlchemy 2 typed declarative models.

Major tables:

- `users`
- `refresh_tokens`
- `conversations`
- `messages`
- `memories`
- `memory_summaries`
- `emotional_memories`
- `emotional_tags`
- `achievement_awards`
- `pronunciation_exercises`
- `pronunciation_practice_sessions`
- `pronunciation_practice_attempts`
- `speaking_challenges`
- `speaking_challenge_completions`
- `learning_issues`
- `conversation_scenario_sessions`
- `conversation_scenario_turns`
- `placement_assessment_sessions`
- `placement_assessment_answers`
- `vocabulary_notebook_entries`
- `vocabulary_review_sessions`
- `vocabulary_review_session_items`
- `admin_audit_logs`

### Relationships

Observed relationships include:

- User to conversations/messages/memories/memory summaries.
- Conversation to messages/memories/memory summaries.
- Pronunciation session to attempts.
- Pronunciation exercise to attempts.
- Conversation scenario session to turns.
- Vocabulary review session to review items.

### Indexes and Constraints

Examples found:

- `users.email` unique index.
- `users.external_id` unique index.
- `users.role` indexed.
- `refresh_tokens.token_hash` unique index.
- `refresh_tokens.token_jti` unique index.
- `refresh_tokens.user_id`, `expires_at`, `revoked_at` indexed.

The model set uses foreign keys and cascade behavior in several places, but full relational integrity should be verified before switching to PostgreSQL.

### Migrations

No Alembic migration stack was found. Startup uses `create_all()` and SQLite-specific ad hoc schema upgrades. This is acceptable for prototyping but is a production blocker.

### Enums / Constraints

Most statuses and categories appear to be stored as strings rather than database-level enums. This is flexible but increases reliance on service-level validation.

## E. AI & Voice Infrastructure

### OpenAI Integration

- Uses `openai==2.36.0`.
- `AsyncOpenAI` is used in `app/ai/openai_service.py`.
- Model default: `gpt-4.1-mini`.
- Startup validation checks OpenAI configuration.
- Retries use exponential backoff with jitter.
- JSON parsing and fallback behavior are implemented.
- Fallback response engine allows mock-like behavior when OpenAI is unavailable.

### Chat AI

- Chat service persists user and assistant messages.
- AI response includes correction, explanation, reply, vocabulary, confidence tips, and coaching metrics.
- Prompting currently focuses on English learning and retains older product voice/branding.

### Speech / Voice

- Pronunciation APIs support exercises, sessions, attempts, and progress.
- No file upload support was found.
- No transcription pipeline was found.
- No OpenAI speech-to-text or text-to-speech integration was found.
- No streaming voice response endpoint was found.
- Current scoring appears scaffolded/manual rather than real audio analysis.

### Async Tasks / Background Workers

- FastAPI async endpoints and async OpenAI calls exist.
- No Celery/RQ/Arq/background worker stack found.
- No durable queue for long-running speech analysis or AI jobs found.

### WebSockets / Streaming

- SSE chat route exists at `/api/v1/chat/stream`.
- No WebSocket endpoint found.
- SSE implementation simulates chunking after full response generation rather than streaming directly from OpenAI.

## F. Admin Dashboard

### Admin Routes

Admin HTML routes:

- Login/setup/logout
- Dashboard
- User analytics
- Learning analytics
- Conversation analytics
- OpenAI usage
- User management

Admin API routes:

- Analytics dashboard
- User listing/profile/status/delete/admin creation

### Permissions and Security

- Admin status is based on `User.role == "admin"`.
- Initial admin role assignment can derive from configured admin emails.
- Admin cookies are HttpOnly.
- Secure cookie flag is environment-aware.
- CSRF cookie/header validation exists for mutations.
- Admin audit service exists.

### Admin Gaps

- Templates and cookies still use Chazy naming.
- Admin pages are separate from the new LearnPSC frontend.
- Fine-grained admin permissions beyond role are not visible.
- Moderation tools appear limited to user management and analytics.

## G. Frontend Integration Readiness

### Ready for Frontend

- Signup/signin/refresh token.
- Bearer-authenticated chat.
- Chat history.
- Learning analytics.
- Fluency dashboard.
- Recommendations.
- Pronunciation exercise/session scaffolding.
- Daily speaking challenges and streaks.
- Vocabulary notebook.
- Placement assessment.
- Achievements.
- Health check.

### Incomplete or Missing for Current LearnPSC Frontend

- `/auth/login` and `/auth/register` aliases or frontend mapping to `/signin` and `/signup`.
- `/auth/me` or `/users/me`.
- General profile update endpoint.
- Settings endpoint.
- Onboarding preferences endpoint.
- Lessons/course listing and lesson detail endpoints.
- Dashboard aggregate endpoint.
- Leaderboard endpoint.
- Daily missions endpoint.
- Real audio upload endpoint.
- Real pronunciation analysis endpoint.
- Speech transcription endpoint.
- Voice AI response/TTS endpoint.

### Inconsistent Response Formats

The backend uses feature-specific schemas directly. Some responses include `success/message`; many do not. There is no global envelope like:

```ts
ApiResponse<T> = {
  success: boolean;
  data: T;
  message?: string;
  error?: ApiError;
}
```

This is workable but requires frontend services to normalize every endpoint individually.

### Pagination

- Chat history supports `limit` and `offset`.
- Admin user list supports `limit` and `offset`.
- Many list endpoints lack explicit pagination.

### CORS

- CORS middleware is configured.
- Default CORS origin is `"*"`.
- `allow_credentials=True` is set.

This combination is not production-ready for credentialed browser requests. Production should use explicit frontend origins.

### Upload Support

No file upload route was found for voice recordings.

### WebSocket Support

No WebSocket route was found. SSE exists for chat.

## H. Security Audit

### Strengths

- Bearer auth dependency rejects missing/invalid/inactive users.
- Refresh token rotation and reuse detection are implemented.
- Refresh tokens are stored as hashes.
- Password hashing uses PBKDF2-HMAC-SHA256 with salt and constant-time verify.
- Production JWT secret validation exists.
- Admin CSRF protection exists for mutations.
- Admin cookies are HttpOnly and environment-aware for secure flag.
- Forgot-password response avoids email enumeration.
- Tests exist for startup security, auth authorization, admin security, and email service.

### Risks

- Default CORS `"*"` with credentials is not safe for production.
- No rate limiting found for login, signup, password reset, chat, or AI-heavy endpoints.
- `/test-openai` is public and outside the API prefix.
- User auth tokens are returned in response bodies; no HttpOnly user cookie option yet.
- JWT lacks audience claim.
- Secret/cookie names still use Chazy.
- No file upload safety because upload feature is not implemented yet.
- No centralized error response contract.
- SQLite default is unsuitable for concurrent production workloads.

### SQL Injection Protections

SQLAlchemy ORM is used consistently in inspected modules. No obvious raw SQL API endpoints were identified, though startup schema upgrade logic performs raw SQLite DDL internally.

## I. Performance Audit

### Strengths

- OpenAI calls are async.
- Database engine uses `pool_pre_ping=True`.
- Chat history uses `limit` and `offset`.
- Admin analytics appear separated into a service layer.

### Risks

- Sync SQLAlchemy sessions are used inside async FastAPI routes, which can block the event loop under load.
- SQLite is the default database.
- No caching layer found.
- No background job queue for expensive AI/audio work.
- No true streaming from OpenAI.
- Analytics endpoints may become expensive as data grows unless queries are indexed and optimized.
- No WebSocket or pub/sub infrastructure for scalable real-time voice/chat.

## J. Frontend Integration Map

| Frontend Page / Feature | Backend Endpoint(s) | Readiness |
| --- | --- | --- |
| Landing page | None required, optional `GET /api/v1/health` | Ready |
| Login | `POST /api/v1/auth/signin` | Ready with route mapping |
| Register | `POST /api/v1/auth/signup` | Ready with route mapping |
| Session restore | `POST /api/v1/auth/refresh`, missing `GET /auth/me` | Partial |
| Logout | Missing user logout endpoint | Missing |
| Dashboard overview | `GET /api/v1/fluency-dashboard/`, `GET /api/v1/learning-analytics/`, `GET /api/v1/recommendations/personalized`, `GET /api/v1/achievements/`, `GET /api/v1/speaking-challenges/streak` | Partial, needs aggregation |
| Chat page | `POST /api/v1/chat/`, `POST /api/v1/chat/stream`, `GET /api/v1/chat/history` | Ready |
| Speaking page | `GET /api/v1/speaking-challenges/daily`, `POST /api/v1/speaking-challenges/{id}/complete`, pronunciation endpoints | Partial, no audio upload/analysis |
| Pronunciation score | `POST /api/v1/pronunciation/sessions/{id}/attempts` | Partial, scaffold only |
| Lessons list | No direct endpoint; possible mapping to scenarios/challenges/pronunciation | Missing |
| Lesson detail | No direct endpoint | Missing |
| Vocabulary page | `GET/POST/PATCH /api/v1/vocabulary-notebook/*` | Ready |
| Placement/onboarding | `POST /api/v1/placement-assessment/start`, answer/result endpoints | Partial, no onboarding preferences |
| Profile | `GET /api/v1/auth/profile/{user_id}` | Partial, needs `/me` and update |
| Settings | Missing | Missing |
| Progress page | Analytics + fluency + pronunciation progress + achievements | Partial |
| Achievements page | `GET /api/v1/achievements/`, `POST /api/v1/achievements/evaluate` | Ready |
| Leaderboard page | Missing | Missing |
| Admin dashboard | `/admin/*`, `/api/v1/admin/*` | Ready/admin only |

## K. Scores

| Category | Score | Reason |
| --- | --- | --- |
| Production readiness | 55 / 100 | Good feature breadth and auth scaffolding, but no migrations, SQLite default, CORS/rate-limit gaps, public diagnostic route, no production API contract. |
| Scalability | 50 / 100 | Service structure is good, but sync DB sessions in async routes, no cache, no queue, no WebSocket/streaming infrastructure, SQLite default. |
| Security | 68 / 100 | Solid JWT/refresh/admin CSRF foundations, but CORS, rate limiting, diagnostic exposure, cookie strategy, and production hardening need work. |
| Frontend integration readiness | 60 / 100 | Many usable endpoints exist, but current frontend route expectations and backend contracts do not align yet. |

## L. Final Action Plan

### 1. Immediate Fixes

1. Add frontend-compatible auth endpoints:
   - `POST /api/v1/auth/login` alias or frontend mapping to `/signin`.
   - `POST /api/v1/auth/register` alias or frontend mapping to `/signup`.
   - `GET /api/v1/auth/me`.
   - `POST /api/v1/auth/logout`.
2. Replace wildcard CORS in non-development environments with explicit frontend origins.
3. Protect or disable `/test-openai` outside development.
4. Add a central API error format and frontend normalization contract.
5. Decide bearer-token vs HttpOnly-cookie auth for the LearnPSC web frontend.
6. Rename public-facing backend metadata and admin branding from Chazy to LearnPSC.

### 2. Frontend Integration Order

1. Health check and environment config.
2. Auth: signup, signin, refresh, current user, logout.
3. Dashboard: fluency, learning analytics, recommendations, achievements, streak.
4. Chat: send message, history, optional SSE.
5. Speaking challenges and pronunciation sessions.
6. Vocabulary notebook.
7. Placement assessment / onboarding bridge.
8. Achievements and gamification.
9. Admin tools, if needed in the frontend.

### 3. Production Blockers

1. Add Alembic migrations and remove runtime schema mutation as the primary migration strategy.
2. Move production database to PostgreSQL.
3. Add rate limiting for auth, password reset, chat, OpenAI, and future upload endpoints.
4. Add real audio upload storage and validation before voice integration.
5. Add real transcription/pronunciation analysis or clearly define the third-party/provider architecture.
6. Add structured logging and request IDs across all endpoints.
7. Add monitoring for OpenAI failures, costs, latency, and fallback usage.
8. Add production CORS, cookie, and secret configuration validation.

### 4. Recommended Next Steps

1. Create an OpenAPI/API contract document for the frontend team.
2. Add a `GET /api/v1/auth/me` endpoint first; it unlocks safe frontend session hydration.
3. Create a dashboard aggregate endpoint to reduce frontend orchestration.
4. Define the LearnPSC domain model for lessons/courses versus existing scenarios/challenges.
5. Implement onboarding preferences as a first-class model and endpoint set.
6. Add a voice ingestion path:
   - upload recording
   - store file safely
   - transcribe
   - analyze pronunciation
   - return score/feedback
7. Introduce Alembic before more schema changes are made.

## Final Notes

The backend has more implemented learning functionality than the current frontend expects, but the naming and contract are still from an earlier Chazy/English-coach backend. The best next move is not a large refactor; it is a thin compatibility/API-contract layer, followed by migration hardening and voice pipeline work.
