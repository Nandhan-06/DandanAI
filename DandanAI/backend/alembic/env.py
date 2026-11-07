"""Alembic environment. Migrations run against Neon's DIRECT connection (DIRECT_URL); pooled URLs are not used for DDL."""
from alembic import context
from sqlalchemy import create_engine, pool

from app import models  # noqa: F401
from app.core.config import get_settings
from app.database import Base, normalize_pg_url

s = get_settings()
url = s.direct_url or s.database_url
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(url=normalize_pg_url(url or "postgresql://user:pass@neon-host/db"), target_metadata=target_metadata, literal_binds=True,
                      dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    if not url:
        raise SystemExit("DIRECT_URL is not set. Add your Neon DIRECT connection string to .env before running migrations.")
    engine = create_engine(normalize_pg_url(url), poolclass=pool.NullPool)
    with engine.connect() as conn:
        context.configure(connection=conn, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
