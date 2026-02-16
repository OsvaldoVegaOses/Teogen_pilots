from pydantic import BaseModel, Field
from typing import Optional, List
from uuid import UUID
from datetime import datetime

class ProjectBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    methodological_profile: str = "straussian" # 'straussian', 'constructivist', 'glaserian'
    language: str = "es"

class ProjectCreate(ProjectBase):
    id: Optional[UUID] = None

class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    methodological_profile: Optional[str] = None
    language: Optional[str] = None

class ProjectResponse(ProjectBase):
    id: UUID
    owner_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
