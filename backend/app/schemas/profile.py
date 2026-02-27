from datetime import datetime

from pydantic import BaseModel, Field


class UserProfileResponse(BaseModel):
    email: str | None = None
    display_name: str
    organization: str | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


class UserProfileUpdate(BaseModel):
    display_name: str = Field(min_length=1, max_length=255)
    organization: str | None = Field(default=None, max_length=255)
