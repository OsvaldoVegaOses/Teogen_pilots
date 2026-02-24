from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from uuid import UUID
from sqlalchemy import select, func, and_

from ..database import get_db
from ..models.models import Code, Fragment, code_fragment_links, Interview, Project
from ..schemas.code import (
    CodeResponse,
    FragmentResponse,
    CodeEvidenceResponse,
    CodeEvidenceCode,
    CodeEvidencePagination,
    CodeEvidenceItem,
    CodeEvidenceInterview,
    CodeEvidenceFragment,
)
from ..core.auth import CurrentUser, get_current_user

router = APIRouter(prefix="/codes", tags=["Codes"])

@router.get("/project/{project_id}", response_model=List[CodeResponse])
async def list_codes(
    project_id: UUID, 
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # Verify project ownership
    project_result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.owner_id == user.user_uuid,
        )
    )
    if not project_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Project not found")

    result = await db.execute(select(Code).filter(Code.project_id == project_id))
    return result.scalars().all()

@router.post("/auto-code/{interview_id}")
async def trigger_auto_coding(
    interview_id: UUID, 
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Triggers the AI Coding Engine to process an individual interview."""
    from ..engines.coding_engine import coding_engine

    # 1. Get interview joined with Project to verify ownership
    result = await db.execute(
        select(Interview, Project)
        .join(Project, Interview.project_id == Project.id)
        .where(
            Interview.id == interview_id,
            Project.owner_id == user.user_uuid
        )
    )
    
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Interview not found")
    
    interview, project = row

    if not interview.full_text:
        raise HTTPException(status_code=400, detail="Interview has no transcript to code")

    # 2. Run Engine
    await coding_engine.auto_code_interview(interview.project_id, interview_id, db)

    return {"message": "Coding completed successfully"}

@router.get("/{code_id}/fragments", response_model=List[FragmentResponse])
async def get_code_fragments(
    code_id: UUID, 
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Retrieve all fragments linked to a specific code via the code_fragment_links table."""
    
    # Verify code belongs to a project owned by user
    code_result = await db.execute(
        select(Code)
        .join(Project, Code.project_id == Project.id)
        .where(
            Code.id == code_id,
            Project.owner_id == user.user_uuid
        )
    )
    if not code_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Code not found")

    result = await db.execute(
        select(Fragment)
        .join(code_fragment_links, Fragment.id == code_fragment_links.c.fragment_id)
        .filter(code_fragment_links.c.code_id == code_id)
        .order_by(Fragment.created_at)
    )
    return result.scalars().all()


@router.get("/{code_id}/evidence", response_model=CodeEvidenceResponse)
async def get_code_evidence(
    code_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    interview_id: UUID | None = Query(None),
    speaker_id: str | None = Query(None),
    source: str | None = Query(None, pattern="^(ai|human|hybrid)$"),
    order: str = Query("created_at_desc", pattern="^(created_at_desc|created_at_asc|confidence_desc)$"),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    code_result = await db.execute(
        select(Code)
        .join(Project, Code.project_id == Project.id)
        .where(Code.id == code_id, Project.owner_id == user.user_uuid)
    )
    code = code_result.scalar_one_or_none()
    if not code:
        raise HTTPException(status_code=404, detail="Code not found")

    where_clauses = [code_fragment_links.c.code_id == code_id]
    if interview_id:
        where_clauses.append(Fragment.interview_id == interview_id)
    if speaker_id:
        where_clauses.append(Fragment.speaker_id == speaker_id)
    if source:
        where_clauses.append(code_fragment_links.c.source == source)

    base_from = (
        Fragment.__table__
        .join(code_fragment_links, Fragment.id == code_fragment_links.c.fragment_id)
        .join(Interview, Fragment.interview_id == Interview.id)
        .join(Project, Interview.project_id == Project.id)
    )
    owner_filter = Project.owner_id == user.user_uuid
    composed_where = and_(*where_clauses, owner_filter)

    total_q = select(func.count()).select_from(base_from).where(composed_where)
    total = (await db.execute(total_q)).scalar_one() or 0

    order_by = Fragment.created_at.desc()
    if order == "created_at_asc":
        order_by = Fragment.created_at.asc()
    elif order == "confidence_desc":
        order_by = code_fragment_links.c.confidence.desc().nullslast()

    offset = (page - 1) * page_size
    rows_q = (
        select(
            Fragment,
            Interview.id.label("interview_id"),
            Interview.participant_pseudonym.label("participant_pseudonym"),
            Interview.created_at.label("interview_created_at"),
            code_fragment_links.c.confidence.label("link_confidence"),
            code_fragment_links.c.source.label("link_source"),
            code_fragment_links.c.char_start.label("char_start"),
            code_fragment_links.c.char_end.label("char_end"),
        )
        .select_from(base_from)
        .where(composed_where)
        .order_by(order_by)
        .offset(offset)
        .limit(page_size)
    )
    rows = (await db.execute(rows_q)).all()

    items: List[CodeEvidenceItem] = []
    for row in rows:
        fragment: Fragment = row[0]
        evidence_interview = CodeEvidenceInterview(
            id=row.interview_id,
            participant_pseudonym=row.participant_pseudonym,
            created_at=row.interview_created_at,
        )
        evidence_fragment = CodeEvidenceFragment(
            id=fragment.id,
            paragraph_index=fragment.paragraph_index,
            speaker_id=fragment.speaker_id,
            text=fragment.text,
            start_offset=fragment.start_offset,
            end_offset=fragment.end_offset,
            char_start=row.char_start,
            char_end=row.char_end,
            start_ms=fragment.start_ms,
            end_ms=fragment.end_ms,
            created_at=fragment.created_at,
        )
        items.append(
            CodeEvidenceItem(
                link_id=f"{code_id}:{fragment.id}",
                confidence=row.link_confidence,
                source=row.link_source,
                interview=evidence_interview,
                fragment=evidence_fragment,
            )
        )

    return CodeEvidenceResponse(
        code=CodeEvidenceCode(
            id=code.id,
            project_id=code.project_id,
            label=code.label,
            definition=code.definition,
            created_by=code.created_by,
        ),
        pagination=CodeEvidencePagination(
            page=page,
            page_size=page_size,
            total=total,
            has_next=offset + len(items) < total,
        ),
        items=items,
    )
