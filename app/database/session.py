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
                "password_hash": "ALTER TABLE users ADD COLUMN password_hash VARCHAR(255)",
                "password_reset_token_hash": "ALTER TABLE users ADD COLUMN password_reset_token_hash VARCHAR(255)",
                "password_reset_expires_at": "ALTER TABLE users ADD COLUMN password_reset_expires_at DATETIME",
                "response_length_preference": "ALTER TABLE users ADD COLUMN response_length_preference VARCHAR(32) DEFAULT 'SHORT'",
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


def _seed_default_data() -> None:
    from app.services.pronunciation_service import PronunciationService
    from app.services.speaking_challenge_service import SpeakingChallengeService

    with SessionLocal() as db:
        PronunciationService(db).seed_default_exercises()
        SpeakingChallengeService(db).seed_default_challenges()


