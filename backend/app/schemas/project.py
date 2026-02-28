from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

ALLOWED_DOMAIN_TEMPLATES = {
    "generic",
    "education",
    "ngo",
    "government",
    "market_research",
    "b2c",
    "consulting",
}


def _normalize_domain_template(value: Optional[str], *, allow_none: bool = False) -> Optional[str]:
    if value is None:
        return None if allow_none else "generic"
    normalized = str(value).strip().lower() or "generic"
    if normalized not in ALLOWED_DOMAIN_TEMPLATES:
        allowed = ", ".join(sorted(ALLOWED_DOMAIN_TEMPLATES))
        raise ValueError(f"domain_template must be one of: {allowed}")
    return normalized


class ProjectBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    methodological_profile: str = "straussian"
    domain_template: str = "generic"
    language: str = "es"

    @field_validator("domain_template", mode="before")
    @classmethod
    def validate_domain_template(cls, value):
        return _normalize_domain_template(value, allow_none=False)


class ProjectCreate(ProjectBase):
    id: Optional[UUID] = None


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    methodological_profile: Optional[str] = None
    domain_template: Optional[str] = None
    language: Optional[str] = None

    @field_validator("domain_template", mode="before")
    @classmethod
    def validate_domain_template(cls, value):
        return _normalize_domain_template(value, allow_none=True)


class ProjectResponse(ProjectBase):
    id: UUID
    owner_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime

    @field_validator("methodological_profile", mode="before")
    @classmethod
    def default_methodological_profile(cls, value):
        return value or "straussian"

    @field_validator("language", mode="before")
    @classmethod
    def default_language(cls, value):
        return value or "es"

    class Config:
        from_attributes = True
