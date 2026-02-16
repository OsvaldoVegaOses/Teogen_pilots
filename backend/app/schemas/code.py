from pydantic import BaseModel
from typing import List, Optional
from uuid import UUID
from datetime import datetime

class CodeBase(BaseModel):
    label: str
    definition: Optional[str] = None
    code_type: str = "open"
    category_id: Optional[UUID] = None
    created_by: str = "human"

class CodeCreate(CodeBase):
    project_id: UUID

class CodeResponse(CodeBase):
    id: UUID
    project_id: UUID
    created_at: datetime

    class Config:
        from_attributes = True

class FragmentResponse(BaseModel):
    id: UUID
    interview_id: UUID
    text: str
    speaker_id: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True
