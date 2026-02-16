import asyncio
from app.database import AsyncSessionLocal
from app.models.models import Interview, Project
from app.api.interviews import process_transcription
from sqlalchemy import select

async def force_process():
    async with AsyncSessionLocal() as db:
        r = await db.execute(select(Interview).order_by(Interview.created_at.desc()))
        interview = r.scalars().first()
        if not interview:
            print("No interviews found.")
            return
        
        print(f"Forcing transcription for: {interview.id}")
        await process_transcription(interview.id, interview.audio_blob_url)
        print("Done.")

if __name__ == "__main__":
    asyncio.run(force_process())
