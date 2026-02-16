import asyncio
from app.database import AsyncSessionLocal
from app.models.models import Interview, Project
from sqlalchemy import select

async def check():
    async with AsyncSessionLocal() as db:
        r = await db.execute(select(Interview))
        interviews = r.scalars().all()
        print(f"Total Interviews: {len(interviews)}")
        for i in interviews:
            print(f"- ID: {i.id} | Status: {i.transcription_status} | Proj: {i.project_id}")

        r_proj = await db.execute(select(Project))
        projects = r_proj.scalars().all()
        print(f"\nTotal Projects: {len(projects)}")
        for p in projects:
            print(f"- ID: {p.id} | Name: {p.name}")

if __name__ == "__main__":
    asyncio.run(check())
