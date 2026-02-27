import logging
from urllib.parse import quote_plus

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from .core.settings import settings
from .models.assistant_models import AssistantBase

logger = logging.getLogger(__name__)

_assistant_engine = None
_assistant_session_local = None
_assistant_initialized = False
_assistant_available = True


def _build_assistant_database_url() -> str:
    if settings.ASSISTANT_DATABASE_URL:
        return settings.ASSISTANT_DATABASE_URL

    if not settings.AZURE_PG_HOST:
        return ""

    encoded_password = quote_plus(settings.AZURE_PG_PASSWORD)
    return (
        f"postgresql+asyncpg://{settings.AZURE_PG_USER}:{encoded_password}"
        f"@{settings.AZURE_PG_HOST}:5432/{settings.ASSISTANT_PG_DATABASE}"
        f"?ssl=require"
    )


def get_assistant_engine():
    global _assistant_engine
    if _assistant_engine:
        return _assistant_engine

    db_url = _build_assistant_database_url()
    if not db_url:
        return None

    _assistant_engine = create_async_engine(
        db_url,
        pool_size=max(1, settings.DB_POOL_SIZE),
        max_overflow=max(0, settings.DB_MAX_OVERFLOW),
        pool_timeout=max(1, settings.DB_POOL_TIMEOUT),
        pool_recycle=max(60, settings.DB_POOL_RECYCLE),
        echo=False,
    )
    return _assistant_engine


def get_assistant_session_local():
    global _assistant_session_local
    if _assistant_session_local:
        return _assistant_session_local

    engine = get_assistant_engine()
    if engine is None:
        return None

    _assistant_session_local = sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )
    return _assistant_session_local


async def ensure_assistant_schema() -> bool:
    global _assistant_initialized, _assistant_available
    if _assistant_initialized:
        return _assistant_available

    engine = get_assistant_engine()
    if engine is None:
        _assistant_available = False
        _assistant_initialized = True
        logger.warning("Assistant DB is not configured. Logging will be skipped.")
        return False

    try:
        async with engine.begin() as conn:
            await conn.run_sync(AssistantBase.metadata.create_all)
        _assistant_available = True
        _assistant_initialized = True
        return True
    except Exception:
        logger.exception("Assistant DB schema initialization failed. Logging will be skipped.")
        _assistant_available = False
        _assistant_initialized = True
        return False


async def get_assistant_db():
    session_local = get_assistant_session_local()
    if session_local is None:
        return
    async with session_local() as session:
        try:
            yield session
        finally:
            await session.close()
