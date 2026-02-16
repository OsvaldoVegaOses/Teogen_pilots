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
    central_category_id: Optional[UUID]
    model: Dict[str, Any]
    propositions: List[Dict[str, Any]] = []
    validation: Dict[str, Any] = {}
    gaps: List[Dict[str, Any]] = []
    confidence_score: float
    generated_by: str
    created_at: datetime

    class Config:
        from_attributes = True
