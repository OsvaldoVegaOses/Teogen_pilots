from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from .core.settings import settings

# PostgreSQL only — no SQLite fallback
# The ORM uses Postgres-specific types (UUID, ARRAY, JSON) that are incompatible with SQLite.
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

engine = create_async_engine(
    DATABASE_URL,
    pool_size=20,
    max_overflow=10,
    pool_timeout=30,
    pool_recycle=1800,
    echo=False,
)

AsyncSessionLocal = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
