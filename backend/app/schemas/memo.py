from pydantic import BaseModel
from typing import Optional
from uuid import UUID
from datetime import datetime

class MemoBase(BaseModel):
    title: str
    content: str
    memo_type: str = "analytical"
    project_id: UUID
    interview_id: Optional[UUID] = None
    code_id: Optional[UUID] = None

class MemoCreate(MemoBase):
    pass

class MemoUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    memo_type: Optional[str] = None

class MemoResponse(MemoBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
