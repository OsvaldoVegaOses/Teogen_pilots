from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from .core.settings import settings

# PostgreSQL only — no SQLite fallback
# The ORM uses Postgres-specific types (UUID, ARRAY, JSON) that are incompatible with SQLite.
_engine = None
_AsyncSessionLocal = None

def get_engine():
    global _engine
    if _engine:
        return _engine

    if not settings.AZURE_PG_HOST:
        raise RuntimeError(
            "AZURE_PG_HOST is not set. "
            "TheoGen requires PostgreSQL — SQLite is not supported. "
            "Set AZURE_PG_HOST, AZURE_PG_USER, AZURE_PG_PASSWORD in your .env file."
        )

    DATABASE_URL = (
        f"postgresql+asyncpg://{settings.AZURE_PG_USER}:{settings.AZURE_PG_PASSWORD}"
        f"@{settings.AZURE_PG_HOST}:5432/{settings.AZURE_PG_DATABASE}"
        f"?ssl=require"
    )

    _engine = create_async_engine(
        DATABASE_URL,
        pool_size=20,
        max_overflow=10,
        pool_timeout=30,
        pool_recycle=1800,
        echo=False,
    )
    return _engine

def get_session_local():
    global _AsyncSessionLocal
    if _AsyncSessionLocal:
        return _AsyncSessionLocal

    _AsyncSessionLocal = sessionmaker(
        get_engine(),
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )
    return _AsyncSessionLocal

# Export these as aliases to avoid breaking imports
@property
def AsyncSessionLocal():
    return get_session_local()

@property
def engine():
    return get_engine()

async def get_db():
    session_local = get_session_local()
    async with session_local() as session:
        try:
            yield session
        finally:
            await session.close()
