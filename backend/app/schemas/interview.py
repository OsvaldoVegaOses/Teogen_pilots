from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Literal
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


class TranscriptSegmentResponse(BaseModel):
    fragment_id: UUID
    paragraph_index: Optional[int] = None
    speaker_id: Optional[str] = None
    text: str
    start_offset: Optional[int] = None
    end_offset: Optional[int] = None
    start_ms: Optional[int] = None
    end_ms: Optional[int] = None
    created_at: datetime


class TranscriptPaginationResponse(BaseModel):
    page: int
    page_size: int
    total_segments: int
    has_next: bool


class TranscriptInterviewResponse(BaseModel):
    id: UUID
    project_id: UUID
    participant_pseudonym: Optional[str] = None
    transcription_status: str
    transcription_method: Optional[str] = None
    language: Optional[str] = None


class InterviewTranscriptResponse(BaseModel):
    interview: TranscriptInterviewResponse
    pagination: TranscriptPaginationResponse
    segments: List[TranscriptSegmentResponse]
    full_text: Optional[str] = None


class InterviewExportRequest(BaseModel):
    project_id: UUID
    interview_ids: List[UUID] = Field(default_factory=list)
    scope: Literal["selected", "all_project"] = "selected"
    format: Literal["txt", "json", "pdf", "xlsx"] = "pdf"
    include_metadata: bool = True
    include_codes: bool = True
    include_timestamps: bool = True
    language: str = "es"


class InterviewExportTaskCreated(BaseModel):
    task_id: str
    status: str
    created_at: str


class InterviewExportTaskStatusResponse(BaseModel):
    task_id: str
    status: str
    progress: int
    message: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
