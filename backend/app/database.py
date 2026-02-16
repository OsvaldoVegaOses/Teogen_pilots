from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from .core.settings import settings

# Construct the database URL from settings
# For local dev, a simple sqlite or local pg can be used if vars are empty
if not settings.AZURE_PG_HOST:
    # Use absolute path for consistency
    import os
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    db_path = os.path.join(base_dir, "test.db")
    DATABASE_URL = f"sqlite+aiosqlite:///{db_path}"
else:
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
