
import logging
from typing import Optional, List, Dict
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
        MATCH (p:Project {id: $project_id})
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
        MATCH (p:Project {id: $project_id})
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
        MATCH (p:Project {id: $project_id})
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

neo4j_service = FoundryNeo4jService()
