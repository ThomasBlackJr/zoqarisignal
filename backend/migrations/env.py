from alembic import context

from app.config import Settings
from app.db import Base, make_database
from app import models  # noqa: F401

config = context.config
settings = Settings()
if context.is_offline_mode():
    context.configure(url=settings.database_url, target_metadata=Base.metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    engine, _ = make_database(settings.database_url)
    with engine.connect() as connection:
        # SQLite batch migrations rebuild parent tables. Suspend FK enforcement
        # on this migration connection only, then verify every reference before
        # returning. Normal application connections always enforce FKs.
        sqlite = settings.database_url.startswith("sqlite")
        if sqlite:
            connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
            connection.commit()
        context.configure(
            connection=connection,
            target_metadata=Base.metadata,
            render_as_batch=settings.database_url.startswith("sqlite"),
        )
        with context.begin_transaction():
            context.run_migrations()

        if sqlite:
            if connection.exec_driver_sql("PRAGMA foreign_key_check").first():
                raise RuntimeError("Migration left invalid foreign keys")
            connection.commit()
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
