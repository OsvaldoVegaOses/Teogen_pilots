"""
Shared dependency helpers for project access control.

RBAC baseline:
- `platform_super_admin`: cross-tenant access.
- `tenant_admin` (and compatible aliases): tenant-scoped access.
- default users: owner-scoped access.

This preserves backward compatibility with legacy rows that may still have
`tenant_id` null while ownership is being migrated.
"""

from uuid import UUID

from fastapi import Depends, HTTPException
from sqlalchemy import and_, or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from ..core.auth import CurrentUser, get_current_user
from ..core.settings import settings
from ..database import get_db
from ..models.models import Project


def _parse_role_list(raw: str) -> set[str]:
    return {
        role.strip().lower()
        for role in str(raw or "").split(",")
        if role and role.strip()
    }


def platform_super_admin_roles() -> set[str]:
    return _parse_role_list(settings.PLATFORM_SUPER_ADMIN_ROLES)


def tenant_admin_roles() -> set[str]:
    return _parse_role_list(settings.TENANT_ADMIN_ROLES)


def is_platform_super_admin(user: CurrentUser) -> bool:
    return user.has_any_role(platform_super_admin_roles())


def is_tenant_admin(user: CurrentUser) -> bool:
    # Tenant admin scope is only meaningful with a concrete tenant claim.
    return bool(str(user.tenant_id or "").strip()) and user.has_any_role(tenant_admin_roles())


def resolve_project_tenant_id(user: CurrentUser) -> str:
    """
    Tenant id persisted in `projects.tenant_id`.
    Falls back to synthetic per-user scope for providers without `tid`.
    """
    return user.effective_tenant_id


def project_scope_condition(user: CurrentUser) -> ColumnElement[bool]:
    """
    Returns SQLAlchemy condition to filter visible projects for the user.
    """
    if is_platform_super_admin(user):
        return true()

    if is_tenant_admin(user):
        tenant_id = str(user.tenant_id or "").strip()
        # Compatibility path: allow tenant-admin to keep seeing their own legacy projects
        # before full tenant backfill is complete.
        return or_(
            Project.tenant_id == tenant_id,
            and_(Project.tenant_id.is_(None), Project.owner_id == user.user_uuid),
        )

    return Project.owner_id == user.user_uuid


async def verify_project_access(
    project_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Project:
    """
    Verify that the authenticated user has read access to the project.
    Returns Project if authorized, raises 404 otherwise.
    """
    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            project_scope_condition(user),
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


async def verify_project_ownership(
    project_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Project:
    """
    Backward-compatible alias. Kept to avoid breaking imports in existing routes.
    """
    return await verify_project_access(project_id=project_id, user=user, db=db)
