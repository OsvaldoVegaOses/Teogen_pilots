
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel

from ..services.qdrant_service import qdrant_service
from ..services.azure_openai import foundry_openai
from ..core.auth import CurrentUser, get_current_user
from ..database import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from ..models.models import Project
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

