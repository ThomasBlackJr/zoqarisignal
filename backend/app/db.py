from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


def database_url(value: str):
    """Select the installed psycopg 3 driver without exposing credentials in errors."""
    try:
        url = make_url(value)
        if url.drivername in {"postgres", "postgresql"}:
            url = url.set(drivername="postgresql+psycopg")
        if url.drivername not in {"sqlite", "sqlite+pysqlite", "postgresql+psycopg"}:
            raise ValueError
        return url
    except (ValueError, TypeError, ArgumentError):
        raise ValueError("DATABASE_URL must be a valid SQLite or PostgreSQL URL using psycopg") from None


def make_database(url: str):
    url = database_url(url)
    sqlite = url.get_backend_name() == "sqlite"
    if sqlite:
        filename = url.database
        if filename and filename != ":memory:":
            Path(filename).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        url, connect_args={"check_same_thread": False, "timeout": 30} if sqlite else {}, pool_pre_ping=True
    )
    if sqlite:

        @event.listens_for(engine, "connect")
        def sqlite_pragmas(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA journal_mode=WAL")

    return engine, sessionmaker(engine, expire_on_commit=False)
