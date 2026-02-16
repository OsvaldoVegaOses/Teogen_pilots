from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from uuid import UUID
from sqlalchemy import select

from ..database import get_db
from ..models.models import Code, Fragment
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

    # 2. Run Engine (In a real scenario, this would be a background task)
    await coding_engine.auto_code_interview(interview.project_id, interview_id, db)
    
    return {"message": "Coding completed successfully"}

@router.get("/{code_id}/fragments", response_model=List[FragmentResponse])
async def get_code_fragments(code_id: UUID, db: AsyncSession = Depends(get_db)):
    # In a real implementation, we would have a many-to-many table or linking logic
    # Here we assume a simple lookup for the sake of the structural skeleton
    # result = await db.execute(select(Fragment).join(CodeFragmentLink)...)
    return [] # Placeholder until Link table is finalized in models
