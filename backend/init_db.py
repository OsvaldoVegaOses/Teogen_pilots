import asyncio
import os
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine
from app.models.models import Base
import logging

# Load environment variables
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def init_db():
    # Get database connection details from environment
    db_user = os.getenv("AZURE_PG_USER", "theogenadmin")
    db_password = os.getenv("AZURE_PG_PASSWORD", "TempPass123!")
    db_host = os.getenv("AZURE_PG_HOST", "localhost")
    db_name = os.getenv("AZURE_PG_DATABASE", "theogen")
    
    # Create database URL (URL-encode password for special chars)
    from urllib.parse import quote_plus
    DATABASE_URL = f"postgresql+asyncpg://{db_user}:{quote_plus(db_password)}@{db_host}/{db_name}?ssl=require"
    
    logger.info(f"Initializing TheoGen Database with host: {db_host}...")
    try:
        engine = create_async_engine(DATABASE_URL)
        async with engine.begin() as conn:
            # This will create all tables defined in models.models
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created successfully!")
    except Exception as e:
        logger.error(f"Error creating database: {e}")
        raise
    finally:
        await engine.dispose()

if __name__ == "__main__":
    asyncio.run(init_db())