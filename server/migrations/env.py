"""Alembic environment, wired to the app's own models and settings.

The schema is defined once, in the SQLAlchemy models — this points Alembic
at that same metadata, so `alembic revision --autogenerate` diffs the models
against the database. The URL comes from app settings (an async asyncpg URL),
overridable with ALEMBIC_URL for one-off runs against another database.

Dev and tests still build the schema directly with create_all for speed;
Alembic is the migration path for a database that must evolve without being
dropped — a real deployment.
"""

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.config import settings
from app.db import Base

# Import every model module so its tables register on Base.metadata before
# autogenerate compares them against the database.
from app.addresses import store as _addresses  # noqa: F401
from app.orders import store as _orders  # noqa: F401
from app.products import store as _products  # noqa: F401
from app.reviews import store as _reviews  # noqa: F401
from app.shops import store as _shops  # noqa: F401
from app.users import store as _users  # noqa: F401

config = context.config
config.set_main_option(
    "sqlalchemy.url", os.environ.get("ALEMBIC_URL", settings.database_url)
)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
