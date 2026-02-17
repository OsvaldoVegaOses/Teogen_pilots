from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from uuid import UUID
from sqlalchemy import select
from datetime import datetime

from ..database import get_db
from ..models.models import Memo
from ..schemas.memo import MemoCreate, MemoResponse, MemoUpdate

router = APIRouter(prefix="/memos", tags=["Memos"])

@router.post("/", response_model=MemoResponse)
async def create_memo(memo: MemoCreate, db: AsyncSession = Depends(get_db)):
    # ← FIXED: Now works because ORM Memo has interview_id, code_id, updated_at
    db_memo = Memo(**memo.model_dump())
    db.add(db_memo)
    await db.commit()
    await db.refresh(db_memo)
    return db_memo

@router.get("/project/{project_id}", response_model=List[MemoResponse])
async def list_memos(project_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Memo).filter(Memo.project_id == project_id))
    return result.scalars().all()

@router.put("/{memo_id}", response_model=MemoResponse)
async def update_memo(memo_id: UUID, memo_update: MemoUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Memo).filter(Memo.id == memo_id))
    db_memo = result.scalar_one_or_none()
    if not db_memo:
        raise HTTPException(status_code=404, detail="Memo not found")

    for var, value in memo_update.model_dump(exclude_unset=True).items():
        setattr(db_memo, var, value)

    # updated_at will be set automatically by onupdate=datetime.utcnow in ORM
    await db.commit()
    await db.refresh(db_memo)
    return db_memo
