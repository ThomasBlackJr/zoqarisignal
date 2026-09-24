"""Rehearse upgrades on a private SQLite backup; never migrate the source database."""

import os
import sqlite3
import time
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.engine import make_url

from app.config import Settings


def snapshot(connection):
    result = {}
    tables = [
        row[0]
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    ]
    for table in tables:
        if table == "alembic_version":
            continue
        columns = [row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')]
        result[table] = (columns, sorted(connection.execute(f'SELECT * FROM "{table}"').fetchall(), key=repr))
    return result


def main():
    settings = Settings()
    url = make_url(settings.database_url)
    if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
        raise SystemExit("This rehearsal supports a local SQLite database only.")
    source = Path(url.database).resolve()
    if not source.is_file():
        raise SystemExit("No existing SQLite database found. Run isolated migration tests instead.")
    directory = Path("data/rehearsals") / str(time.time_ns())
    directory.mkdir(parents=True)
    target = (directory / "customer-entry.db").resolve()
    with sqlite3.connect(source.as_uri() + "?mode=ro", uri=True) as live, sqlite3.connect(target) as copy:
        live.backup(copy)
    with sqlite3.connect(target) as copy:
        original = snapshot(copy)
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = "sqlite:///" + target.as_posix()
    try:
        config = Config("alembic.ini")
        command.upgrade(config, "head")
        command.check(config)
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous
    with sqlite3.connect(target) as copy:
        for table, (columns, rows) in original.items():
            fields = ", ".join(f'"{column}"' for column in columns)
            current = sorted(copy.execute(f'SELECT {fields} FROM "{table}"').fetchall(), key=repr)
            if current != rows:
                raise SystemExit(f"Preservation check failed for {table}")
        if copy.execute("PRAGMA foreign_key_check").fetchall():
            raise SystemExit("Foreign key check failed")
        for table in ("users", "calls", "transcripts", "qa_evaluations"):
            print(f"{table}: {len(original.get(table, ([], []))[1])} original rows preserved exactly")
        print("All original columns/rows preserved; foreign keys and schema check passed.")
        print("Only the private rehearsal copy was migrated. Source database unchanged.")


if __name__ == "__main__":
    main()
