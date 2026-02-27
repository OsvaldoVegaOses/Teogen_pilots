from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import CurrentUser, get_current_user
from ..database import get_db
from ..models.models import UserProfile
from ..schemas.profile import UserProfileResponse, UserProfileUpdate

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("/me", response_model=UserProfileResponse)
async def get_my_profile(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(UserProfile).where(UserProfile.user_id == user.user_uuid))
    profile = result.scalar_one_or_none()
    if profile:
        return profile

    return UserProfileResponse(
        email=user.email,
        display_name=user.name or user.email or "Usuario TheoGen",
        organization=None,
        updated_at=None,
    )


@router.patch("/me", response_model=UserProfileResponse)
async def update_my_profile(
    payload: UserProfileUpdate,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(UserProfile).where(UserProfile.user_id == user.user_uuid))
    profile = result.scalar_one_or_none()

    if profile is None:
        profile = UserProfile(
            user_id=user.user_uuid,
            email=user.email,
            display_name=payload.display_name.strip(),
            organization=(payload.organization.strip() if payload.organization else None),
        )
        db.add(profile)
    else:
        profile.email = user.email
        profile.display_name = payload.display_name.strip()
        profile.organization = payload.organization.strip() if payload.organization else None

    await db.commit()
    await db.refresh(profile)
    return profile
