from __future__ import annotations

from logging.config import fileConfig
from urllib.parse import quote_plus

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.settings import settings
from app.models.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _db_url() -> str:
    pwd = quote_plus(settings.AZURE_PG_PASSWORD)
    return (
        f"postgresql+psycopg2://{settings.AZURE_PG_USER}:{pwd}"
        f"@{settings.AZURE_PG_HOST}:5432/{settings.AZURE_PG_DATABASE}"
        "?sslmode=require"
    )


def run_migrations_offline() -> None:
    url = _db_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # configparser treats '%' as interpolation markers.
    # Passwords encoded with quote_plus can include '%' (e.g. %21),
    # so we must escape it for set_main_option.
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
