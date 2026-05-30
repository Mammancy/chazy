# Admin User Purge Strategy Report

## Current Delete Model

The existing admin `DELETE /api/v1/admin/users/{user_id}` endpoint remains a soft delete plus anonymization flow. It does not remove the `users` row.

The new purge operation is separate:

- `DELETE /api/v1/admin/users/{user_id}/purge`
- Admin-only
- Requires the user to already be inactive and deleted/anonymized
- Returns `{ "success": true, "message": "User permanently removed" }`

## Foreign-Key Audit

The `users` table is referenced by:

- `refresh_tokens.user_id` with `ondelete="CASCADE"`
- `conversations.user_id`
- `messages.user_id`
- `memories.user_id`
- `memory_summaries.user_id`
- `achievement_awards.user_id`
- `learning_issues.user_id`
- `speaking_challenge_completions.user_id`
- `pronunciation_practice_sessions.user_id`
- `pronunciation_practice_attempts.user_id`
- `placement_assessment_sessions.user_id`
- `conversation_scenario_sessions.user_id`
- `vocabulary_notebook_entries.user_id`
- `vocabulary_review_sessions.user_id`
- optional historical emotional tables if present: `emotional_memories`, `message_emotional_tags`

Other dependent tables reference user-owned rows:

- `messages.conversation_id -> conversations.id`
- `conversation_scenario_turns.scenario_session_id -> conversation_scenario_sessions.id`
- `conversation_scenario_turns.user_message_id / assistant_message_id -> messages.id`
- `placement_assessment_answers.assessment_session_id -> placement_assessment_sessions.id`
- `pronunciation_practice_attempts.practice_session_id -> pronunciation_practice_sessions.id`
- `vocabulary_review_session_items.review_session_id -> vocabulary_review_sessions.id`
- `vocabulary_review_session_items.entry_id -> vocabulary_notebook_entries.id`
- `vocabulary_notebook_entries.source_message_id -> messages.id`

## Cascade Behavior

Some ORM relationships define cascade behavior, such as user conversations and conversation messages, but many database foreign keys do not define `ondelete`. A safe purge cannot rely on ORM cascade alone.

SQLite foreign keys are enabled by the database session setup, so deleting a user before dependent rows can fail with FK constraint errors.

## Recommended Deletion Order

The purge implementation deletes dependent rows before parent rows:

1. Resolve user-owned conversation, message, scenario session, placement session, pronunciation session, vocabulary entry, and review session IDs.
2. Delete conversation scenario turns.
3. Delete vocabulary review session items.
4. Delete placement assessment answers.
5. Delete pronunciation attempts.
6. Delete optional emotional message/tag rows if those tables exist.
7. Delete refresh tokens.
8. Delete achievement awards.
9. Delete learning issues.
10. Delete speaking challenge completions.
11. Delete remaining pronunciation attempts and sessions.
12. Delete vocabulary review sessions and notebook entries.
13. Delete placement assessment sessions.
14. Delete conversation scenario sessions.
15. Delete memories and memory summaries.
16. Delete messages.
17. Delete conversations.
18. Delete the user row.

## Safety Rules

- Active users cannot be purged.
- Users must first pass the existing soft delete/anonymization flow.
- Admins cannot purge their own account.
- Admin UI shows the purge button only for inactive deleted/anonymized users.
- Admin UI requires explicit confirmation and typing `DELETE` or `PURGE`.
- Purge writes an audit log action: `admin_user_purged`.

## Remaining Considerations

- If new user-linked tables are added later, they must be added to the purge deletion order.
- For long-term maintainability, future migrations should define explicit `ondelete` behavior for all user-owned tables.
- A test fixture should cover purge for a user with conversations, messages, vocabulary entries, pronunciation sessions, speaking completions, achievements, refresh tokens, and assessment data.
