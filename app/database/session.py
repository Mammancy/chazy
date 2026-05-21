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
    if "messages" not in inspector.get_table_names():
        return

    message_columns = {column["name"] for column in inspector.get_columns("messages")}
    with engine.begin() as connection:
        if "metadata_json" not in message_columns:
            connection.execute(text("ALTER TABLE messages ADD COLUMN metadata_json JSON"))
