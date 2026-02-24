
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
        score_threshold: float = 0.7
    ) -> List[models.ScoredPoint]:
        """
        Searches for similar vectors in the project's collection.
        """
        if not self.enabled or not self.client:
            return []

        collection_name = self._get_collection_name(project_id)
        try:
            results = await self.client.query_points(
                collection_name=collection_name,
                query=vector,
                limit=limit,
                score_threshold=score_threshold,
                with_payload=True,
            )
            return results.points
        except UnexpectedResponse as e:
            if "Not found" in str(e):
                logger.warning(f"Collection {collection_name} not found during search.")
                return []
            logger.error(f"Qdrant search error: {e}")
            return []
        except Exception as e:
            logger.error(f"Qdrant search failed: {e}")
            return []

    async def search_supporting_fragments(
        self,
        project_id: UUID,
        query_vector: List[float],
        limit: int = 3,
        score_threshold: float = 0.6,
    ) -> List[dict]:
        """
        Returns normalized semantic evidence payload for theory generation.
        """
        hits = await self.search_similar(
            project_id=project_id,
            vector=query_vector,
            limit=limit,
            score_threshold=score_threshold,
        )
        evidence = []
        for hit in hits:
            payload = hit.payload or {}
            metadata = {
                "codes": payload.get("codes", []),
                "project_id": payload.get("project_id"),
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
