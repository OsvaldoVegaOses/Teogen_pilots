from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from uuid import UUID
from sqlalchemy import select

from ..database import get_db
from ..models.models import Code, Fragment, code_fragment_links, Interview, Project
from ..schemas.code import CodeResponse, FragmentResponse
from ..core.auth import CurrentUser, get_current_user

router = APIRouter(prefix="/codes", tags=["Codes"])

@router.get("/project/{project_id}", response_model=List[CodeResponse])
async def list_codes(
    project_id: UUID, 
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # Verify project ownership
    project_result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.owner_id == user.user_uuid,
        )
    )
    if not project_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Project not found")

    result = await db.execute(select(Code).filter(Code.project_id == project_id))
    return result.scalars().all()

@router.post("/auto-code/{interview_id}")
async def trigger_auto_coding(
    interview_id: UUID, 
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Triggers the AI Coding Engine to process an individual interview."""
    from ..engines.coding_engine import coding_engine

    # 1. Get interview joined with Project to verify ownership
    result = await db.execute(
        select(Interview, Project)
        .join(Project, Interview.project_id == Project.id)
        .where(
            Interview.id == interview_id,
            Project.owner_id == user.user_uuid
        )
    )
    
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Interview not found")
    
    interview, project = row

    if not interview.full_text:
        raise HTTPException(status_code=400, detail="Interview has no transcript to code")

    # 2. Run Engine
    await coding_engine.auto_code_interview(interview.project_id, interview_id, db)

    return {"message": "Coding completed successfully"}

@router.get("/{code_id}/fragments", response_model=List[FragmentResponse])
async def get_code_fragments(
    code_id: UUID, 
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Retrieve all fragments linked to a specific code via the code_fragment_links table."""
    
    # Verify code belongs to a project owned by user
    code_result = await db.execute(
        select(Code)
        .join(Project, Code.project_id == Project.id)
        .where(
            Code.id == code_id,
            Project.owner_id == user.user_uuid
        )
    )
    if not code_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Code not found")

    result = await db.execute(
        select(Fragment)
        .join(code_fragment_links, Fragment.id == code_fragment_links.c.fragment_id)
        .filter(code_fragment_links.c.code_id == code_id)
        .order_by(Fragment.created_at)
    )
    return result.scalars().all()
