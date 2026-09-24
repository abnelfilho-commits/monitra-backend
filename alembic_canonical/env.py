"""Separate canonical lineage; never selects a deployment URL implicitly."""
import os

from alembic import context
from sqlalchemy import create_engine, pool


def run(connection):
    if connection.dialect.name != "postgresql":
        raise RuntimeError("Canonical baseline requires PostgreSQL")
    context.configure(connection=connection, target_metadata=None, version_table_schema="public")
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    raise RuntimeError("Baseline requires online empty-schema verification")
else:
    supplied = context.config.attributes.get("connection")
    if supplied is not None:
        run(supplied)
    else:
        url = os.environ.get("M0_DATABASE_URL")
        if not url:
            raise RuntimeError("Explicit M0_DATABASE_URL is required")
        engine = create_engine(url, poolclass=pool.NullPool)
        try:
            with engine.connect() as connection:
                run(connection)
        finally:
            engine.dispose()
