from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime

class InterviewBase(BaseModel):
    project_id: UUID
    participant_pseudonym: Optional[str] = None
    metadata_json: Dict[str, Any] = {}

class InterviewCreate(InterviewBase):
    pass

class InterviewResponse(InterviewBase):
    id: UUID
    audio_blob_url: Optional[str] = None
    transcription_status: str
    transcription_method: Optional[str] = None
    full_text: Optional[str] = None
    word_count: Optional[int] = None
    language: Optional[str] = None
    speakers: List[Dict[str, Any]] = []
    created_at: datetime

    class Config:
        from_attributes = True
