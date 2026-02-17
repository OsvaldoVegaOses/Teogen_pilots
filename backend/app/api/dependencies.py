"""
Shared dependency helpers for verifying project ownership.
Used by sub-resource endpoints (interviews, codes, memos, theories)
to ensure the authenticated user owns the parent project.
"""

from uuid import UUID

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import CurrentUser, get_current_user
from ..database import get_db
from ..models.models import Project


async def verify_project_ownership(
    project_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Project:
    """
    Verify that the authenticated user owns the given project.
    Returns the Project object if authorized, raises 404 otherwise.
    
    Usage:
        @router.get("/{project_id}/items")
        async def list_items(project: Project = Depends(verify_project_ownership)):
            ...
    """
    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.owner_id == user.user_uuid,
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project
