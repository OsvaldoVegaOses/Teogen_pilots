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
    start_offset: Optional[int] = None
    end_offset: Optional[int] = None
    paragraph_index: Optional[int] = None
    start_ms: Optional[int] = None
    end_ms: Optional[int] = None
    speaker_id: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class CodeEvidenceInterview(BaseModel):
    id: UUID
    participant_pseudonym: Optional[str] = None
    created_at: datetime


class CodeEvidenceFragment(BaseModel):
    id: UUID
    paragraph_index: Optional[int] = None
    speaker_id: Optional[str] = None
    text: str
    start_offset: Optional[int] = None
    end_offset: Optional[int] = None
    char_start: Optional[int] = None
    char_end: Optional[int] = None
    start_ms: Optional[int] = None
    end_ms: Optional[int] = None
    created_at: datetime


class CodeEvidenceItem(BaseModel):
    link_id: str
    confidence: Optional[float] = None
    source: Optional[str] = None
    interview: CodeEvidenceInterview
    fragment: CodeEvidenceFragment


class CodeEvidencePagination(BaseModel):
    page: int
    page_size: int
    total: int
    has_next: bool


class CodeEvidenceCode(BaseModel):
    id: UUID
    project_id: UUID
    label: str
    definition: Optional[str] = None
    created_by: str


class CodeEvidenceResponse(BaseModel):
    code: CodeEvidenceCode
    pagination: CodeEvidencePagination
    items: List[CodeEvidenceItem]
