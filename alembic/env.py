from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app.config.settings import get_settings
from app.database.config import resolve_sqlite_url
from app.models import Base


# Alembic Config object, which provides access to the values in alembic.ini.
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


# Import the complete model package so every mapped table is registered on Base.metadata.
target_metadata = Base.metadata


settings = get_settings()
database_url = resolve_sqlite_url(settings.database_url)

# Keep credentials out of alembic.ini. The application remains the source of truth
# for DATABASE_URL, including the production PostgreSQL URL supplied by the environment.
config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))


def run_migrations_offline() -> None:
    """Run migrations without creating a database connection."""
    url = database_url
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations using a real database connection."""
    connectable = create_engine(
        database_url,
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()

    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
