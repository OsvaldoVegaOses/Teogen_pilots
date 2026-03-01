from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from uuid import UUID
from sqlalchemy import select
import uuid

from ..database import get_db
from ..models.models import Memo, Project
from ..schemas.memo import MemoCreate, MemoResponse, MemoUpdate
from ..core.auth import CurrentUser, get_current_user
from .dependencies import project_scope_condition

router = APIRouter(prefix="/memos", tags=["Memos"])

@router.post("/", response_model=MemoResponse, status_code=status.HTTP_201_CREATED)
async def create_memo(
    memo: MemoCreate,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # Verify project ownership
    result = await db.execute(
        select(Project).where(
            Project.id == memo.project_id,
            project_scope_condition(user),
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Project not found")

    db_memo = Memo(**memo.model_dump())
    db.add(db_memo)
    await db.commit()
    await db.refresh(db_memo)
    return db_memo

@router.get("/project/{project_id}", response_model=List[MemoResponse])
async def list_memos(
    project_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # Verify project ownership
    project_result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            project_scope_condition(user),
        )
    )
    if not project_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Project not found")

    result = await db.execute(select(Memo).filter(Memo.project_id == project_id))
    return result.scalars().all()

@router.put("/{memo_id}", response_model=MemoResponse)
async def update_memo(
    memo_id: UUID,
    memo_update: MemoUpdate,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # Verify memo exists and belongs to a project owned by user
    result = await db.execute(
        select(Memo)
        .join(Project, Memo.project_id == Project.id)
        .where(
            Memo.id == memo_id,
            project_scope_condition(user),
        )
    )
    db_memo = result.scalar_one_or_none()
    
    if not db_memo:
        raise HTTPException(status_code=404, detail="Memo not found")

    for var, value in memo_update.model_dump(exclude_unset=True).items():
        setattr(db_memo, var, value)

    await db.commit()
    await db.refresh(db_memo)
    return db_memo
