from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime

class TheoryBase(BaseModel):
    project_id: UUID
    version: int = 1
    status: str = "draft"

class TheoryGenerateRequest(BaseModel):
    min_interviews: int = 5
    use_model_router: bool = True

class TheoryResponse(TheoryBase):
    id: UUID
    central_category_id: Optional[UUID] = None
    model_json: Dict[str, Any]  # ← FIXED: was "model", ORM column is "model_json"
    propositions: List[Dict[str, Any]] = []
    validation: Dict[str, Any] = {}
    gaps: List[Dict[str, Any]] = []
    confidence_score: Optional[float] = None
    generated_by: Optional[str] = None  # ← FIXED: now Optional (may be null)
    created_at: datetime

    class Config:
        from_attributes = True


class ClaimEvidenceItem(BaseModel):
    fragment_id: str
    score: Optional[float] = None
    rank: Optional[int] = None
    text: Optional[str] = None
    interview_id: Optional[str] = None


class ClaimExplainItem(BaseModel):
    claim_id: str
    claim_type: str
    section: str
    order: int
    text: str
    categories: List[Dict[str, Optional[str]]] = []
    evidence: List[ClaimEvidenceItem] = []
    path_examples: List[str] = []


class TheoryClaimsExplainResponse(BaseModel):
    project_id: UUID
    theory_id: UUID
    source: str
    total: int = 0
    limit: int = 0
    offset: int = 0
    has_more: bool = False
    section_filter: Optional[str] = None
    claim_type_filter: Optional[str] = None
    claim_count: int
    claims: List[ClaimExplainItem] = []


class TheoryJudgeRolloutResponse(BaseModel):
    project_id: UUID
    policy: Dict[str, Any]
    latest_theory_id: Optional[UUID] = None
    latest_created_at: Optional[datetime] = None
    latest_validation: Dict[str, Any] = {}


class TheoryPipelineSloResponse(BaseModel):
    project_id: UUID
    window_size: int
    sample_size: int
    latest_theory_id: Optional[UUID] = None
    latest_created_at: Optional[datetime] = None
    latency_p95_ms: Dict[str, float] = {}
    latency_p50_ms: Dict[str, float] = {}
    quality: Dict[str, Any] = {}
    reliability: Dict[str, Any] = {}
