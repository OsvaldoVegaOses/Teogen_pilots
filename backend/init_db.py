import asyncio
from app.database import engine
from app.models.models import Base
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def init_db():
    logger.info("Initializing TheoGen Database in axialpg...")
    try:
        async with engine.begin() as conn:
            # This will create all tables defined in models.models
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created successfully!")
    except Exception as e:
        logger.error(f"Error creating database: {e}")

if __name__ == "__main__":
    asyncio.run(init_db())
