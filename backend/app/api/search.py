
from fastapi import APIRouter, Depends, HTTPException
from typing import List, Optional, Dict
from uuid import UUID
from pydantic import BaseModel

from ..services.qdrant_service import qdrant_service
from ..services.azure_openai import foundry_openai
from ..core.auth import CurrentUser, get_current_user
from ..database import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from ..models.models import Project, Fragment, Interview
from sqlalchemy import select

router = APIRouter(prefix="/search", tags=["Search"])

class SearchResult(BaseModel):
    fragment_id: UUID
    score: float
    text: str
    project_id: UUID
    codes: List[str] = []

class SearchRequest(BaseModel):
    query: str
    limit: int = 5
    project_filter: Optional[UUID] = None  # If None, search across all user's projects (future)


class FragmentLookupRequest(BaseModel):
    project_id: UUID
    fragment_ids: List[UUID]


class FragmentLookupResult(BaseModel):
    fragment_id: UUID
    interview_id: UUID
    paragraph_index: Optional[int] = None
    speaker_id: Optional[str] = None
    start_ms: Optional[int] = None
    end_ms: Optional[int] = None


@router.post("/fragments", response_model=List[SearchResult])
async def search_fragments(
    request: SearchRequest,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Semantic search for fragments using Qdrant.
    Requires the project_filter to be set to a project owned by the user.
    """
    
    if not request.project_filter:
        raise HTTPException(status_code=400, detail="Project filter is required for now.")
    
    # Verify ownership
    project_result = await db.execute(
        select(Project).where(
            Project.id == request.project_filter,
            Project.owner_id == user.user_uuid,
        )
    )
    if not project_result.scalar_one_or_none():
           raise HTTPException(status_code=404, detail="Project not found or access denied")

    # Generate Query Embedding
    try:
        query_embedding = await foundry_openai.generate_embeddings([request.query])
        if not query_embedding:
            raise HTTPException(status_code=500, detail="Failed to generate embedding")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Embedding service error: {str(e)}")

    # Search in Qdrant
    results = await qdrant_service.search_similar(
        project_id=request.project_filter,
        vector=query_embedding[0],
        limit=request.limit
    )
    
    response = []
    for hit in results:
        payload = hit.payload or {}
        response.append(SearchResult(
            fragment_id=UUID(hit.id),
            score=hit.score,
            text=payload.get("text", ""),
            project_id=UUID(payload.get("project_id")) if payload.get("project_id") else request.project_filter,
            codes=payload.get("codes", [])
        ))
        
    return response


@router.post("/fragments/lookup", response_model=List[FragmentLookupResult])
async def lookup_fragments(
    request: FragmentLookupRequest,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not request.fragment_ids:
        return []

    # Verify ownership via project_id and owner_id, and constrain fragments to the project.
    project_result = await db.execute(
        select(Project).where(
            Project.id == request.project_id,
            Project.owner_id == user.user_uuid,
        )
    )
    if not project_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Project not found or access denied")

    rows = await db.execute(
        select(Fragment, Interview.id.label("interview_id"))
        .join(Interview, Fragment.interview_id == Interview.id)
        .where(
            Fragment.id.in_(request.fragment_ids[:200]),
            Interview.project_id == request.project_id,
        )
    )

    out: List[FragmentLookupResult] = []
    for frag, interview_id in rows.all():
        out.append(
            FragmentLookupResult(
                fragment_id=frag.id,
                interview_id=interview_id,
                paragraph_index=getattr(frag, "paragraph_index", None),
                speaker_id=getattr(frag, "speaker_id", None),
                start_ms=getattr(frag, "start_ms", None),
                end_ms=getattr(frag, "end_ms", None),
            )
        )
    return out

