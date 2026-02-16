import asyncio
from app.database import AsyncSessionLocal
from app.models.models import Project, Interview, Fragment
from sqlalchemy import select

async def debug():
    async with AsyncSessionLocal() as db:
        try:
            print("--- PROJECTS ---")
            r = await db.execute(select(Project))
            for p in r.scalars().all():
                print(f"{p.id}: {p.name}")

            print("\n--- INTERVIEWS ---")
            r_int = await db.execute(select(Interview))
            for i in r_int.scalars().all():
                print(f"{i.id} | {i.transcription_status} | {i.participant_pseudonym}")
            
            print("\n--- FRAGMENTS ---")
            r_frag = await db.execute(select(Fragment))
            print(f"Total Fragments: {len(r_frag.scalars().all())}")

        except Exception as e:
            print(f"ERROR: {e}")

if __name__ == "__main__":
    asyncio.run(debug())
