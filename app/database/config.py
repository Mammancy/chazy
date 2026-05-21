from pathlib import Path


def resolve_sqlite_url(database_url: str) -> str:
    """
    Normalize SQLite URLs for stable local development paths.
    Keeps absolute SQLite URLs as-is and resolves relative file paths.
    """
    if not database_url.startswith("sqlite:///"):
        return database_url

    raw_path = database_url.replace("sqlite:///", "", 1)
    if raw_path == ":memory:":
        return database_url

    db_path = Path(raw_path)
    if db_path.is_absolute():
        return database_url

    return f"sqlite:///{db_path.resolve()}"


def sqlite_connect_args(database_url: str) -> dict:
    if database_url.startswith("sqlite"):
        return {"check_same_thread": False}
    return {}

