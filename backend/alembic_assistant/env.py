from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.assistant_database import _build_assistant_database_url
from app.models.assistant_models import AssistantBase

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = AssistantBase.metadata


def _db_url() -> str:
    url = _build_assistant_database_url().replace("+asyncpg", "+psycopg2")
    # asyncpg uses ?ssl=require; psycopg2 needs ?sslmode=require
    return url.replace("?ssl=require", "?sslmode=require").replace("&ssl=require", "&sslmode=require")


def run_migrations_offline() -> None:
    context.configure(
        url=_db_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    config.set_main_option("sqlalchemy.url", _db_url().replace("%", "%%"))
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
