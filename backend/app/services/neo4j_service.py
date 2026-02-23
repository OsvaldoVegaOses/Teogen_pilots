
import logging
from typing import Optional, List, Dict, Any
from uuid import UUID

from neo4j import AsyncGraphDatabase, AsyncDriver, AsyncSession
from ..core.settings import settings

logger = logging.getLogger(__name__)

class FoundryNeo4jService:
    """
    Async Service for interacting with Neo4j Graph Database.
    Designed for fault tolerance: operations return gracefully if unconfigured.
    """

    def __init__(self):
        self.driver: Optional[AsyncDriver] = None
        self.enabled = False

        if settings.NEO4J_URI and settings.NEO4J_USER and settings.NEO4J_PASSWORD:
            try:
                self.driver = AsyncGraphDatabase.driver(
                    settings.NEO4J_URI,
                    auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
                )
                self.enabled = True
                logger.info(f"Neo4j service initialized at {settings.NEO4J_URI} as {settings.NEO4J_USER}")
            except Exception as e:
                logger.error(f"Failed to initialize Neo4j driver: {e}")
        else:
            logger.info("Neo4j URI/User/Password not set. Graph search capabilities disabled.")

    async def verify_connectivity(self):
        """Simple check to verify if the graph database is reachable."""
        if not self.enabled or not self.driver:
            return False
        try:
            await self.driver.verify_connectivity()
            return True
        except Exception as e:
            logger.error(f"Neo4j connectivity check failed: {e}")
            return False

    async def create_project_node(self, project_id: UUID, name: str):
        """MERGE (p:Project {id: project_id, name: name})."""
        if not self.enabled: return

        query = """
        MERGE (p:Project {id: $project_id})
        SET p.name = $name
        RETURN p
        """
        await self._execute_write(query, {"project_id": str(project_id), "name": name})

    async def create_code_node(self, project_id: UUID, code_id: UUID, label: str):
        """MERGE (c:Code {id: code_id}) LINKED TO (p:Project)."""
        if not self.enabled: return

        query = """
        MERGE (p:Project {id: $project_id})
        MERGE (c:Code {id: $code_id})
        SET c.label = $label, c.project_id = $project_id
        MERGE (p)-[:HAS_CODE]->(c)
        RETURN c
        """
        await self._execute_write(query, {
            "project_id": str(project_id),
            "code_id": str(code_id),
            "label": label
        })

    async def create_fragment_node(self, project_id: UUID, fragment_id: UUID, text_snippet: str):
        """MERGE (f:Fragment {id: fragment_id}) LINKED TO (p:Project)."""
        if not self.enabled: return

        query = """
        MERGE (p:Project {id: $project_id})
        MERGE (f:Fragment {id: $fragment_id})
        SET f.text_snippet = $text_snippet, f.project_id = $project_id
        MERGE (p)-[:HAS_FRAGMENT]->(f)
        RETURN f
        """
        await self._execute_write(query, {
            "project_id": str(project_id),
            "fragment_id": str(fragment_id),
            "text_snippet": text_snippet[:50]  # Only store snippet
        })

    async def create_code_fragment_relation(self, code_id: UUID, fragment_id: UUID):
        """(c:Code)-[:APPLIES_TO]->(f:Fragment)."""
        if not self.enabled: return

        query = """
        MATCH (c:Code {id: $code_id})
        MATCH (f:Fragment {id: $fragment_id})
        MERGE (c)-[:APPLIES_TO]->(f)
        """
        await self._execute_write(query, {
            "code_id": str(code_id),
            "fragment_id": str(fragment_id)
        })

    async def create_category_node(self, project_id: UUID, category_id: UUID, name: str):
        """MERGE (cat:Category {id: category_id})."""
        if not self.enabled: return

        query = """
        MERGE (p:Project {id: $project_id})
        MERGE (cat:Category {id: $category_id})
        SET cat.name = $name
        MERGE (p)-[:HAS_CATEGORY]->(cat)
        RETURN cat
        """
        await self._execute_write(query, {
            "project_id": str(project_id),
            "category_id": str(category_id),
            "name": name
        })

    async def link_code_to_category(self, code_id: UUID, category_id: UUID):
        """(cat:Category)-[:CONTAINS]->(c:Code)."""
        if not self.enabled: return

        query = """
        MATCH (cat:Category {id: $category_id})
        MATCH (c:Code {id: $code_id})
        MERGE (cat)-[:CONTAINS]->(c)
        """
        await self._execute_write(query, {
            "code_id": str(code_id),
            "category_id": str(category_id)
        })

    async def batch_sync_interview(
        self,
        project_id: UUID,
        fragments: list[tuple[UUID, str]],          # [(fragment_id, text), ...]
        codes_cache: dict,                           # {label: Code object}
        fragment_code_pairs: list[tuple[UUID, UUID]], # [(fragment_id, code_id), ...]
    ):
        """
        Syncs an entire interview to Neo4j in 3 UNWIND queries instead of
        O(fragments × codes) individual round-trips.
        """
        if not self.enabled or not self.driver:
            return

        pid = str(project_id)
        async with self.driver.session() as session:
            # 1. Batch fragment nodes
            if fragments:
                await session.run(
                    """
                    UNWIND $frags AS f
                    MERGE (proj:Project {id: $pid})
                    MERGE (fr:Fragment {id: f.id})
                    SET fr.text_snippet = f.snippet, fr.project_id = $pid
                    MERGE (proj)-[:HAS_FRAGMENT]->(fr)
                    """,
                    {
                        "pid": pid,
                        "frags": [
                            {"id": str(fid), "snippet": text[:50]}
                            for fid, text in fragments
                        ],
                    },
                )

            # 2. Batch code nodes (whole project cache — idempotent MERGE)
            if codes_cache:
                await session.run(
                    """
                    UNWIND $codes AS c
                    MERGE (proj:Project {id: $pid})
                    MERGE (co:Code {id: c.id})
                    SET co.label = c.label, co.project_id = $pid
                    MERGE (proj)-[:HAS_CODE]->(co)
                    """,
                    {
                        "pid": pid,
                        "codes": [
                            {"id": str(obj.id), "label": label}
                            for label, obj in codes_cache.items()
                        ],
                    },
                )

            # 3. Batch code→fragment relations
            if fragment_code_pairs:
                await session.run(
                    """
                    UNWIND $pairs AS p
                    MATCH (c:Code {id: p.code_id})
                    MATCH (f:Fragment {id: p.frag_id})
                    MERGE (c)-[:APPLIES_TO]->(f)
                    """,
                    {
                        "pairs": [
                            {"code_id": str(cid), "frag_id": str(fid)}
                            for fid, cid in fragment_code_pairs
                        ]
                    },
                )

    async def ensure_project_node(self, project_id: UUID, name: str = "Unnamed Project"):
        """Ensures a project node exists before syncing related entities."""
        if not self.enabled:
            raise RuntimeError("Neo4j service is not enabled")
        await self.create_project_node(project_id, name or "Unnamed Project")

    async def get_project_network_metrics(self, project_id: UUID) -> Dict[str, Any]:
        """
        Returns graph metrics used by theory generation.
        Raises when project has no usable graph data.
        """
        if not self.enabled or not self.driver:
            raise RuntimeError("Neo4j service is not enabled")

        project_id_str = str(project_id)

        counts_query = """
        MATCH (p:Project {id: $project_id})
        OPTIONAL MATCH (p)-[:HAS_CATEGORY]->(cat:Category)
        WITH p, count(DISTINCT cat) AS category_count
        OPTIONAL MATCH (p)-[:HAS_CODE]->(c:Code)
        WITH p, category_count, count(DISTINCT c) AS code_count
        OPTIONAL MATCH (p)-[:HAS_FRAGMENT]->(f:Fragment)
        RETURN category_count, code_count, count(DISTINCT f) AS fragment_count
        """

        centrality_query = """
        MATCH (:Project {id: $project_id})-[:HAS_CATEGORY]->(cat:Category)
        OPTIONAL MATCH (cat)-[:CONTAINS]->(c:Code)-[:APPLIES_TO]->(:Fragment)<-[:APPLIES_TO]-(other:Code)
        WITH cat, count(DISTINCT c) AS code_degree, count(DISTINCT other) AS fragment_degree
        RETURN cat.id AS category_id, cat.name AS category_name, code_degree, fragment_degree
        ORDER BY code_degree DESC, fragment_degree DESC
        """

        cooccurrence_query = """
        MATCH (:Project {id: $project_id})-[:HAS_CATEGORY]->(c1:Category)-[:CONTAINS]->(:Code)-[:APPLIES_TO]->(f:Fragment)<-[:APPLIES_TO]-(:Code)<-[:CONTAINS]-(c2:Category)
        WHERE c1.id < c2.id
        RETURN c1.id AS category_a_id, c1.name AS category_a_name,
               c2.id AS category_b_id, c2.name AS category_b_name,
               count(DISTINCT f) AS shared_fragments
        ORDER BY shared_fragments DESC
        """

        counts_data = await self._execute_read(counts_query, {"project_id": project_id_str})
        centrality_data = await self._execute_read(centrality_query, {"project_id": project_id_str})
        cooccurrence_data = await self._execute_read(cooccurrence_query, {"project_id": project_id_str})

        counts = counts_data[0] if counts_data else {
            "category_count": 0,
            "code_count": 0,
            "fragment_count": 0
        }

        if counts.get("category_count", 0) == 0:
            raise ValueError(f"No category nodes found in Neo4j for project {project_id_str}")

        return {
            "project_id": project_id_str,
            "counts": counts,
            "category_centrality": centrality_data,
            "category_cooccurrence": cooccurrence_data,
        }

    async def close(self):
        """Closes the Neo4j driver connection."""
        if self.driver:
            await self.driver.close()

    async def _execute_write(self, query: str, parameters: Dict[str, Any]):
        """Internal helper to execute write transactions safely."""
        try:
            async with self.driver.session() as session:
                await session.run(query, parameters)
        except Exception as e:
            logger.error(f"Neo4j write failed: {e}")
            raise

    async def _execute_read(self, query: str, parameters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Internal helper to execute read queries and return plain dict rows."""
        try:
            async with self.driver.session() as session:
                result = await session.run(query, parameters)
                return await result.data()
        except Exception as e:
            logger.error(f"Neo4j read failed: {e}")
            raise

neo4j_service = FoundryNeo4jService()
