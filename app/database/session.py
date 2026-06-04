from collections.abc import Generator

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from app.config.settings import get_settings
from app.database.config import resolve_sqlite_url, sqlite_connect_args
from app.models import Base

settings = get_settings()
database_url = resolve_sqlite_url(settings.database_url)
connect_args = sqlite_connect_args(database_url)

engine = create_engine(
    database_url,
    pool_pre_ping=True,
    connect_args=connect_args,
)


@event.listens_for(engine, "connect")
def enable_sqlite_foreign_keys(dbapi_connection, _) -> None:
    if database_url.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA temp_store=MEMORY")
        cursor.close()


SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False,
)


async def init_db() -> None:
    # Ensures model metadata from all imported model modules is registered.
    import app.models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _seed_default_data()
    _upgrade_sqlite_schema()


async def close_db() -> None:
    engine.dispose()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _upgrade_sqlite_schema() -> None:
    if not database_url.startswith("sqlite"):
        return

    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())

    with engine.begin() as connection:
        if "messages" in table_names:
            message_columns = {column["name"] for column in inspector.get_columns("messages")}
            if "metadata_json" not in message_columns:
                connection.execute(text("ALTER TABLE messages ADD COLUMN metadata_json JSON"))

        if "users" in table_names:
            user_columns = {column["name"] for column in inspector.get_columns("users")}
            user_column_sql = {
                "phone_number": "ALTER TABLE users ADD COLUMN phone_number VARCHAR(32)",
                "country": "ALTER TABLE users ADD COLUMN country VARCHAR(100)",
                "state": "ALTER TABLE users ADD COLUMN state VARCHAR(100)",
                "bio": "ALTER TABLE users ADD COLUMN bio TEXT",
                "learning_goal": "ALTER TABLE users ADD COLUMN learning_goal TEXT",
                "password_hash": "ALTER TABLE users ADD COLUMN password_hash VARCHAR(255)",
                "password_reset_token_hash": "ALTER TABLE users ADD COLUMN password_reset_token_hash VARCHAR(255)",
                "password_reset_expires_at": "ALTER TABLE users ADD COLUMN password_reset_expires_at DATETIME",
                "response_length_preference": "ALTER TABLE users ADD COLUMN response_length_preference VARCHAR(32) DEFAULT 'SHORT'",
                "role": "ALTER TABLE users ADD COLUMN role VARCHAR(32) DEFAULT 'user'",
                "public_profile_visible": "ALTER TABLE users ADD COLUMN public_profile_visible BOOLEAN DEFAULT 1",
            }
            for column_name, statement in user_column_sql.items():
                if column_name not in user_columns:
                    connection.execute(text(statement))

        if "vocabulary_notebook_entries" in table_names:
            vocabulary_columns = {column["name"] for column in inspector.get_columns("vocabulary_notebook_entries")}
            vocabulary_column_sql = {
                "retention_score": "ALTER TABLE vocabulary_notebook_entries ADD COLUMN retention_score FLOAT DEFAULT 0.0",
                "ease_factor": "ALTER TABLE vocabulary_notebook_entries ADD COLUMN ease_factor FLOAT DEFAULT 2.5",
                "review_interval_days": "ALTER TABLE vocabulary_notebook_entries ADD COLUMN review_interval_days INTEGER DEFAULT 1",
                "consecutive_correct": "ALTER TABLE vocabulary_notebook_entries ADD COLUMN consecutive_correct INTEGER DEFAULT 0",
            }
            for column_name, statement in vocabulary_column_sql.items():
                if column_name not in vocabulary_columns:
                    connection.execute(text(statement))

        if "pronunciation_practice_attempts" in table_names:
            attempt_columns = {column["name"] for column in inspector.get_columns("pronunciation_practice_attempts")}
            attempt_column_sql = {
                "display_name": "ALTER TABLE pronunciation_practice_attempts ADD COLUMN display_name VARCHAR(160)",
                "is_favorite": "ALTER TABLE pronunciation_practice_attempts ADD COLUMN is_favorite BOOLEAN DEFAULT 0",
            }
            for column_name, statement in attempt_column_sql.items():
                if column_name not in attempt_columns:
                    connection.execute(text(statement))

        if "lesson_progress" not in table_names:
            connection.execute(text("""
                CREATE TABLE IF NOT EXISTS lesson_progress (
                    id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    lesson_id VARCHAR(120) NOT NULL,
                    progress INTEGER NOT NULL DEFAULT 0,
                    xp_awarded INTEGER NOT NULL DEFAULT 0,
                    badge VARCHAR(160),
                    completed_at DATETIME,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    PRIMARY KEY (id),
                    CONSTRAINT uq_lesson_progress_user_lesson UNIQUE (user_id, lesson_id),
                    FOREIGN KEY(user_id) REFERENCES users (id)
                )
            """))
            table_names.add("lesson_progress")

        if "practice_room_messages" not in table_names:
            connection.execute(text("""
                CREATE TABLE IF NOT EXISTS practice_room_messages (
                    id INTEGER NOT NULL,
                    room_id INTEGER NOT NULL,
                    session_id INTEGER NOT NULL,
                    sender_user_id INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    message_type VARCHAR(32) DEFAULT 'message' NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    PRIMARY KEY (id),
                    FOREIGN KEY(room_id) REFERENCES practice_rooms (id),
                    FOREIGN KEY(session_id) REFERENCES practice_sessions (id),
                    FOREIGN KEY(sender_user_id) REFERENCES users (id)
                )
            """))
            table_names.add("practice_room_messages")

        if "partner_reviews" not in table_names:
            connection.execute(text("""
                CREATE TABLE IF NOT EXISTS partner_reviews (
                    id INTEGER NOT NULL,
                    session_id INTEGER NOT NULL,
                    reviewer_id INTEGER NOT NULL,
                    reviewed_user_id INTEGER NOT NULL,
                    rating INTEGER NOT NULL,
                    comment TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    PRIMARY KEY (id),
                    CONSTRAINT uq_partner_reviews_session_reviewer UNIQUE (session_id, reviewer_id),
                    FOREIGN KEY(session_id) REFERENCES practice_sessions (id),
                    FOREIGN KEY(reviewer_id) REFERENCES users (id),
                    FOREIGN KEY(reviewed_user_id) REFERENCES users (id)
                )
            """))
            table_names.add("partner_reviews")

        if "speaking_evaluations" not in table_names:
            connection.execute(text("""
                CREATE TABLE IF NOT EXISTS speaking_evaluations (
                    id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    transcript TEXT NOT NULL,
                    duration_seconds INTEGER NOT NULL,
                    overall_score INTEGER NOT NULL,
                    grammar_score INTEGER NOT NULL,
                    fluency_score INTEGER NOT NULL,
                    vocabulary_score INTEGER NOT NULL,
                    confidence_score INTEGER NOT NULL,
                    coach_feedback TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    PRIMARY KEY (id),
                    FOREIGN KEY(user_id) REFERENCES users (id)
                )
            """))
            table_names.add("speaking_evaluations")

        if "retention_states" not in table_names:
            connection.execute(text("""
                CREATE TABLE IF NOT EXISTS retention_states (
                    id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    freeze_tokens INTEGER DEFAULT 0 NOT NULL,
                    last_checkin_date DATE,
                    last_freeze_earned_date DATE,
                    last_freeze_used_date DATE,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    PRIMARY KEY (id),
                    CONSTRAINT uq_retention_states_user UNIQUE (user_id),
                    FOREIGN KEY(user_id) REFERENCES users (id)
                )
            """))
            table_names.add("retention_states")
        else:
            retention_columns = {column["name"] for column in inspector.get_columns("retention_states")}
            if "last_freeze_used_date" not in retention_columns:
                connection.execute(text("ALTER TABLE retention_states ADD COLUMN last_freeze_used_date DATE"))

        _create_performance_indexes(connection, table_names)


def _create_performance_indexes(connection, table_names: set[str]) -> None:
    index_statements = {
        "users": [
            "CREATE INDEX IF NOT EXISTS ix_users_created_at ON users(created_at)",
            "CREATE INDEX IF NOT EXISTS ix_users_is_active ON users(is_active)",
        ],
        "messages": [
            "CREATE INDEX IF NOT EXISTS ix_messages_created_at ON messages(created_at)",
            "CREATE INDEX IF NOT EXISTS ix_messages_role_created_at ON messages(role, created_at)",
            "CREATE INDEX IF NOT EXISTS ix_messages_user_created_at ON messages(user_id, created_at)",
            "CREATE INDEX IF NOT EXISTS ix_messages_conversation_created_at ON messages(conversation_id, created_at)",
        ],
        "conversations": [
            "CREATE INDEX IF NOT EXISTS ix_conversations_created_at ON conversations(created_at)",
            "CREATE INDEX IF NOT EXISTS ix_conversations_user_updated_at ON conversations(user_id, updated_at)",
        ],
        "speaking_challenge_completions": [
            "CREATE INDEX IF NOT EXISTS ix_speaking_completions_completed_at ON speaking_challenge_completions(completed_at)",
            "CREATE INDEX IF NOT EXISTS ix_speaking_completions_user_session ON speaking_challenge_completions(user_id, client_session_id)",
        ],
        "vocabulary_notebook_entries": [
            "CREATE INDEX IF NOT EXISTS ix_vocabulary_entries_created_at ON vocabulary_notebook_entries(created_at)",
            "CREATE INDEX IF NOT EXISTS ix_vocabulary_entries_mastery ON vocabulary_notebook_entries(mastery_status)",
        ],
        "vocabulary_review_sessions": [
            "CREATE INDEX IF NOT EXISTS ix_vocabulary_reviews_created_at ON vocabulary_review_sessions(created_at)",
        ],
        "placement_assessment_sessions": [
            "CREATE INDEX IF NOT EXISTS ix_placement_sessions_status ON placement_assessment_sessions(status)",
        ],
        "pronunciation_practice_sessions": [
            "CREATE INDEX IF NOT EXISTS ix_pronunciation_sessions_status ON pronunciation_practice_sessions(status)",
        ],
        "lesson_progress": [
            "CREATE INDEX IF NOT EXISTS ix_lesson_progress_user_id ON lesson_progress(user_id)",
            "CREATE INDEX IF NOT EXISTS ix_lesson_progress_lesson_id ON lesson_progress(lesson_id)",
            "CREATE INDEX IF NOT EXISTS ix_lesson_progress_completed_at ON lesson_progress(completed_at)",
        ],
        "practice_room_messages": [
            "CREATE INDEX IF NOT EXISTS ix_practice_room_messages_room_id ON practice_room_messages(room_id)",
            "CREATE INDEX IF NOT EXISTS ix_practice_room_messages_session_id ON practice_room_messages(session_id)",
            "CREATE INDEX IF NOT EXISTS ix_practice_room_messages_sender_user_id ON practice_room_messages(sender_user_id)",
            "CREATE INDEX IF NOT EXISTS ix_practice_room_messages_created_at ON practice_room_messages(created_at)",
        ],
        "partner_reviews": [
            "CREATE INDEX IF NOT EXISTS ix_partner_reviews_session_id ON partner_reviews(session_id)",
            "CREATE INDEX IF NOT EXISTS ix_partner_reviews_reviewer_id ON partner_reviews(reviewer_id)",
            "CREATE INDEX IF NOT EXISTS ix_partner_reviews_reviewed_user_id ON partner_reviews(reviewed_user_id)",
            "CREATE INDEX IF NOT EXISTS ix_partner_reviews_created_at ON partner_reviews(created_at)",
        ],
        "speaking_evaluations": [
            "CREATE INDEX IF NOT EXISTS ix_speaking_evaluations_user_id ON speaking_evaluations(user_id)",
            "CREATE INDEX IF NOT EXISTS ix_speaking_evaluations_created_at ON speaking_evaluations(created_at)",
        ],
        "retention_states": [
            "CREATE INDEX IF NOT EXISTS ix_retention_states_user_id ON retention_states(user_id)",
        ],
    }
    for table_name, statements in index_statements.items():
        if table_name not in table_names:
            continue
        for statement in statements:
            connection.execute(text(statement))


def _seed_default_data() -> None:
    from app.services.pronunciation_service import PronunciationService
    from app.services.speaking_challenge_service import SpeakingChallengeService

    with SessionLocal() as db:
        PronunciationService(db).seed_default_exercises()
        SpeakingChallengeService(db).seed_default_challenges()


