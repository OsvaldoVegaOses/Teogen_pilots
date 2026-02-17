from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..database import get_db
from ..models.models import Code, Fragment, code_fragment_links
from ..schemas.code import CodeResponse, FragmentResponse

router = APIRouter(prefix="/codes", tags=["Codes"])

@router.get("/project/{project_id}", response_model=List[CodeResponse])
async def list_codes(project_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Code).filter(Code.project_id == project_id))
    return result.scalars().all()

@router.post("/auto-code/{interview_id}")
async def trigger_auto_coding(interview_id: UUID, db: AsyncSession = Depends(get_db)):
    """Triggers the AI Coding Engine to process an individual interview."""
    from ..engines.coding_engine import coding_engine
    from ..models.models import Interview

    # 1. Get interview
    result = await db.execute(select(Interview).filter(Interview.id == interview_id))
    interview = result.scalar_one_or_none()

    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")

    if not interview.full_text:
        raise HTTPException(status_code=400, detail="Interview has no transcript to code")

    # 2. Run Engine
    await coding_engine.auto_code_interview(interview.project_id, interview_id, db)

    return {"message": "Coding completed successfully"}

@router.get("/{code_id}/fragments", response_model=List[FragmentResponse])
async def get_code_fragments(code_id: UUID, db: AsyncSession = Depends(get_db)):
    """Retrieve all fragments linked to a specific code via the code_fragment_links table."""
    # ← FIXED: Actually query the many-to-many relationship instead of returning []
    result = await db.execute(
        select(Fragment)
        .join(code_fragment_links, Fragment.id == code_fragment_links.c.fragment_id)
        .filter(code_fragment_links.c.code_id == code_id)
        .order_by(Fragment.created_at)
    )
    return result.scalars().all()
