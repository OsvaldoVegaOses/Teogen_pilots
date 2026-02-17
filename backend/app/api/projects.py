from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from ..database import get_db
from ..models.models import Project
from ..schemas.project import ProjectCreate, ProjectResponse, ProjectUpdate
from ..core.auth import CurrentUser, get_current_user
import uuid

router = APIRouter(prefix="/projects", tags=["projects"])

@router.post("/", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    project_in: ProjectCreate,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    new_project = Project(
        name=project_in.name,
        description=project_in.description,
        methodological_profile=project_in.methodological_profile,
        language=project_in.language,
        owner_id=user.user_uuid,  # ← Linked to authenticated user
    )
    if project_in.id:
        new_project.id = project_in.id
    db.add(new_project)
    await db.commit()
    await db.refresh(new_project)
    return new_project

@router.get("/", response_model=List[ProjectResponse])
async def list_projects(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Only return projects owned by the authenticated user
    result = await db.execute(
        select(Project)
        .where(Project.owner_id == user.user_uuid)
        .order_by(Project.created_at.desc())
    )
    return result.scalars().all()

@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
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

@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: uuid.UUID,
    project_in: ProjectUpdate,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.owner_id == user.user_uuid,
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    update_data = project_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(project, field, value)
    
    await db.commit()
    await db.refresh(project)
    return project

@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.owner_id == user.user_uuid,
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    await db.delete(project)
    await db.commit()
    return None
