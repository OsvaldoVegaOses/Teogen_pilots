import asyncio
import logging
from typing import List, Optional
from uuid import UUID

from qdrant_client import AsyncQdrantClient, models
from qdrant_client.http.exceptions import UnexpectedResponse
from ..core.settings import settings

logger = logging.getLogger(__name__)

class FoundryQdrantService:
    """
    Async Service for interacting with Qdrant Vector Database.
    Designed to be fault-tolerant: methods return gracefully if service is unconfigured.
    """

    def __init__(self):
        self.client = None
        self.enabled = False
        
        if settings.QDRANT_URL:
            try:
                # Use AsyncQdrantClient for non-blocking I/O
                self.client = AsyncQdrantClient(
                    url=settings.QDRANT_URL,
                    api_key=settings.QDRANT_API_KEY,
                    timeout=10.0
                )
                self.enabled = True
                logger.info(f"Qdrant service initialized at {settings.QDRANT_URL}")
            except Exception as e:
                logger.error(f"Failed to initialize Qdrant client: {e}")
        else:
            logger.info("Qdrant URL not set. Vector search capabilities disabled.")

    def ensure_available(self):
        """Raises if Qdrant is not configured/initialized."""
        if not self.enabled or not self.client:
            raise RuntimeError("Qdrant service is not enabled")

    async def verify_connectivity(self) -> bool:
        """Checks if Qdrant is reachable."""
        self.ensure_available()
        try:
            await self.client.get_collections()
            return True
        except Exception as e:
            logger.error(f"Qdrant connectivity check failed: {e}")
            return False

    def _get_collection_name(self, project_id: UUID) -> str:
        """Standardizes collection name format."""
        return f"project_{str(project_id)}_fragments"

    def _build_scope_filter(
        self,
        project_id: UUID,
        query_filter: models.Filter | None = None,
        owner_id: str | None = None,
    ) -> models.Filter:
        """
        Defense-in-depth scoping:
        - Always enforce `project_id`.
        - Optionally enforce `owner_id`.
        - Preserve additional caller-provided constraints.
        """
        must: list = [
            models.FieldCondition(
                key="project_id",
                match=models.MatchValue(value=str(project_id)),
            )
        ]
        if owner_id:
            must.append(
                models.FieldCondition(
                    key="owner_id",
                    match=models.MatchValue(value=str(owner_id)),
                )
            )
        if query_filter and query_filter.must:
            must.extend(list(query_filter.must))
        return models.Filter(
            must=must,
            should=(query_filter.should if query_filter else None),
            must_not=(query_filter.must_not if query_filter else None),
        )

    async def ensure_collection(self, project_id: UUID, vector_size: int = 3072):
        """
        Ensures the collection exists for the project. 
        Auto-creates if missing using text-embedding-3-large dims (3072).
        """
        if not self.enabled or not self.client:
            return

        collection_name = self._get_collection_name(project_id)
        try:
            if not await self.client.collection_exists(collection_name):
                logger.info(f"Creating Qdrant collection: {collection_name}")
                await self.client.create_collection(
                    collection_name=collection_name,
                    vectors_config=models.VectorParams(
                        size=vector_size,
                        distance=models.Distance.COSINE
                    )
                )
        except Exception as e:
            logger.error(f"Error ensuring collection {collection_name}: {e}")

    async def upsert_vectors(self, project_id: UUID, points: List[models.PointStruct]):
        """
        Upserts vectors into the project's collection.
        This handles transient errors internally.
        """
        if not self.enabled or not self.client:
            return

        collection_name = self._get_collection_name(project_id)
        try:
            await self.ensure_collection(project_id) # Ensure it exists first
            
            await self.client.upsert(
                collection_name=collection_name,
                points=points,
                wait=False # Async write for performance
            )
            logger.debug(f"Upserted {len(points)} vectors to {collection_name}")
        except Exception as e:
            logger.error(f"Failed to upsert to Qdrant: {e}")

    async def search_similar(
        self, 
        project_id: UUID, 
        vector: List[float], 
        limit: int = 5, 
        score_threshold: float = 0.7,
        query_filter: models.Filter | None = None,
        owner_id: str | None = None,
    ) -> List[models.ScoredPoint]:
        """
        Searches for similar vectors in the project's collection.
        """
        if not self.enabled or not self.client:
            return []

        collection_name = self._get_collection_name(project_id)
        scope_filter = self._build_scope_filter(
            project_id=project_id,
            query_filter=query_filter,
            owner_id=owner_id,
        )
        return await self._query_points_with_retry(
            collection_name=collection_name,
            vector=vector,
            limit=limit,
            score_threshold=score_threshold,
            scope_filter=scope_filter,
        )

    async def _query_points_with_retry(
        self,
        *,
        collection_name: str,
        vector: List[float],
        limit: int,
        score_threshold: float,
        scope_filter: models.Filter,
    ) -> List[models.ScoredPoint]:
        max_retries = max(1, int(getattr(settings, "QDRANT_SEARCH_MAX_RETRIES", 3)))
        backoff_base = max(0.0, float(getattr(settings, "QDRANT_SEARCH_BACKOFF_SECONDS", 0.25)))
        for attempt in range(1, max_retries + 1):
            try:
                results = await self.client.query_points(
                    collection_name=collection_name,
                    query=vector,
                    limit=limit,
                    score_threshold=score_threshold,
                    with_payload=True,
                    query_filter=scope_filter,
                )
                return results.points
            except UnexpectedResponse as e:
                if "Not found" in str(e):
                    logger.warning(f"Collection {collection_name} not found during search.")
                    return []
                if attempt >= max_retries:
                    logger.error(f"Qdrant search error after retries: {e}")
                    return []
                delay = backoff_base * (2 ** (attempt - 1))
                logger.warning(
                    "Qdrant search transient error (attempt %d/%d), retrying in %.2fs: %s",
                    attempt,
                    max_retries,
                    delay,
                    str(e)[:200],
                )
                if delay > 0:
                    await asyncio.sleep(delay)
            except Exception as e:
                if attempt >= max_retries:
                    logger.error(f"Qdrant search failed after retries: {e}")
                    return []
                delay = backoff_base * (2 ** (attempt - 1))
                logger.warning(
                    "Qdrant search failed (attempt %d/%d), retrying in %.2fs: %s",
                    attempt,
                    max_retries,
                    delay,
                    str(e)[:200],
                )
                if delay > 0:
                    await asyncio.sleep(delay)
        return []

    async def search_supporting_fragments(
        self,
        project_id: UUID,
        query_vector: List[float],
        limit: int = 3,
        score_threshold: float = 0.6,
        owner_id: str | None = None,
        source_types: List[str] | None = None,
        allow_legacy_fallback: bool = True,
    ) -> List[dict]:
        """
        Returns normalized semantic evidence payload for theory generation.
        """
        source_types = source_types or ["fragment"]
        source_must = [
            models.FieldCondition(
                key="source_type",
                match=models.MatchAny(any=[str(t) for t in source_types if str(t).strip()]),
            )
        ]

        # Prefer scoped source_type evidence when available.
        hits = await self.search_similar(
            project_id=project_id,
            vector=query_vector,
            limit=limit,
            score_threshold=score_threshold,
            query_filter=models.Filter(must=source_must),
            owner_id=owner_id,
        )
        if not hits and owner_id and allow_legacy_fallback:
            # Compatibility path for legacy points without owner_id payload.
            hits = await self.search_similar(
                project_id=project_id,
                vector=query_vector,
                limit=limit,
                score_threshold=score_threshold,
                query_filter=models.Filter(must=source_must),
                owner_id=None,
            )

        # Last-resort compatibility path for old payloads without source_type.
        if not hits and allow_legacy_fallback:
            hits = await self.search_similar(
                project_id=project_id,
                vector=query_vector,
                limit=limit,
                score_threshold=score_threshold,
                query_filter=None,
                owner_id=None,
            )
        evidence = []
        for hit in hits:
            payload = hit.payload or {}
            metadata = {
                "codes": payload.get("codes", []),
                "project_id": payload.get("project_id"),
                "owner_id": payload.get("owner_id"),
                "interview_id": payload.get("interview_id"),
                "source_type": payload.get("source_type"),
                "created_at": payload.get("created_at"),
                "category_id": payload.get("category_id"),
                "theory_id": payload.get("theory_id"),
                "claim_id": payload.get("claim_id"),
            }
            evidence.append({
                "id": str(hit.id),
                "fragment_id": str(hit.id),
                "score": float(hit.score),
                "text": payload.get("text", ""),
                "codes": payload.get("codes", []),
                "metadata": metadata,
            })
        return evidence

    async def delete_collection(self, project_id: UUID):
        """Deletes a project's collection (e.g. on project deletion)."""
        if not self.enabled or not self.client:
            return

        collection_name = self._get_collection_name(project_id)
        try:
            await self.client.delete_collection(collection_name)
            logger.info(f"Deleted collection {collection_name}")
        except Exception as e:
            logger.error(f"Failed to delete collection {collection_name}: {e}")

qdrant_service = FoundryQdrantService()
