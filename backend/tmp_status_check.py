import asyncio
from sqlalchemy import select, func
from app.database import get_session_local
from app.models.models import Interview, Code, Category

PROJECT_ID = "73f3d7e3-5233-49d5-a7f0-76f011885b39"

async def main():
    session_local = get_session_local()
    async with session_local() as db:
        interview_rows = (
            await db.execute(
                select(Interview.id, Interview.participant_pseudonym, Interview.transcription_status)
                .where(Interview.project_id == PROJECT_ID)
            )
        ).all()

        print(f"Interviews: {len(interview_rows)}")
        for row in interview_rows:
            print(f"- {row.id} | {row.participant_pseudonym} | {row.transcription_status}")

        codes = (
            await db.execute(
                select(func.count()).select_from(Code).where(Code.project_id == PROJECT_ID)
            )
        ).scalar()

        categories = (
            await db.execute(
                select(func.count()).select_from(Category).where(Category.project_id == PROJECT_ID)
            )
        ).scalar()

        print(f"Codes: {codes}")
        print(f"Categories: {categories}")

if __name__ == "__main__":
    asyncio.run(main())
