import asyncio
from app.database import AsyncSessionLocal
from app.models.models import Interview, Fragment
from sqlalchemy import select

async def run_coding():
    async with AsyncSessionLocal() as db:
        try:
            r = await db.execute(select(Interview).filter(Interview.transcription_status == 'completed'))
            interviews = r.scalars().all()
            
            if not interviews:
                print("No interviews ready for coding (completed status). Run upload script first.")
                return

            for interview in interviews:
                print(f"--- Coding Interview: {interview.id} ---")
                from app.engines.coding_engine import coding_engine
                await coding_engine.auto_code_interview(interview.project_id, interview.id, db)
                print(f"✅ Finished coding for {interview.id}")
                
        except Exception as e:
            print(f"ERROR: {e}")

if __name__ == "__main__":
    asyncio.run(run_coding())
