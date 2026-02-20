# backend/app/engines/coding_engine.py
from ..services.azure_openai import foundry_openai
from ..services.qdrant_service import qdrant_service
from ..services.neo4j_service import neo4j_service
from ..prompts.axial_coding import AXIAL_CODING_SYSTEM_PROMPT, get_coding_user_prompt
import json
import logging
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from ..models.models import Fragment, Code, Project, code_fragment_links
from sqlalchemy import select, insert, update
from qdrant_client.models import PointStruct

logger = logging.getLogger(__name__)

class CodingEngine:
    """Engine responsible for Open and Axial coding of fragments."""

    def __init__(self):
        self.ai = foundry_openai

    async def process_fragment(self, project_id: UUID, fragment_id: UUID, fragment_text: str, db: AsyncSession) -> dict:
        """
        Takes a fragment text and generates suggested codes and axial relationships.
        Now also links codes to the source fragment via code_fragment_links.
        
        Syncs data to Qdrant (vectors) and Neo4j (graph).
        """
        
        # 1. Get existing codes for context
        # Optimized: Only fetch labels and definitions to save bandwidth/tokens
        code_result = await db.execute(select(Code).filter(Code.project_id == project_id))
        existing_codes_list = code_result.scalars().all()
        existing_codes = [
            {"label": c.label, "definition": c.definition}
            for c in existing_codes_list
        ]
        
        # 2. Call AI (Coding Logic)
        logger.info(f"Coding fragment: {fragment_text[:50]}...")

        # Robust JSON parsing
        try:
            raw_response = await self.ai.claude_analysis(
                messages=[
                    {"role": "system", "content": AXIAL_CODING_SYSTEM_PROMPT},
                    {"role": "user", "content": get_coding_user_prompt(fragment_text, existing_codes)},
                ],
                response_format={"type": "json_object"},
            )
            coding_results = json.loads(raw_response)
        except Exception as e:
            logger.error(f"AI Coding failed for fragment {fragment_id}: {e}")
            return {}

        # 3. Save codes and create links in Relational DB (Postgres)
        codes_to_sync = [] # List of (code_id, label) for Neo4j

        for code_data in coding_results.get("extracted_codes", []):
            label = code_data.get("label")
            if not label: continue

            # Check if code already exists (Case-insensitive check recommended but using exact for now)
            existing_code = next((c for c in existing_codes_list if c.label == label), None)
            
            if existing_code:
                code_id = existing_code.id
            else:
                # Create new code
                # Check DB again in case it was created in parallel (race condition mitigation)
                existing_check = await db.execute(
                    select(Code).filter(Code.label == label, Code.project_id == project_id)
                )
                existing_code_db = existing_check.scalar_one_or_none()
                
                if existing_code_db:
                    code_id = existing_code_db.id
                else:
                    new_code = Code(
                        project_id=project_id,
                        label=label,
                        definition=code_data.get("definition", ""),
                        created_by="ai",
                    )
                    db.add(new_code)
                    await db.flush() 
                    code_id = new_code.id
                    # Add to local cache for subsequent loops
                    existing_codes_list.append(new_code)

            codes_to_sync.append((code_id, label))

            # Create Code <-> Fragment Link
            # Using execute directly to handle composite primary key insert safely
            # Ideally we check existence first or use ON CONFLICT DO NOTHING (Postgres specific)
            # Here we check manually:
            link_exists = await db.execute(
                select(code_fragment_links.c.code_id).where(
                    code_fragment_links.c.code_id == code_id,
                    code_fragment_links.c.fragment_id == fragment_id,
                )
            )
            if not link_exists.first():
                await db.execute(
                    insert(code_fragment_links).values(
                        code_id=code_id,
                        fragment_id=fragment_id,
                        confidence=code_data.get("confidence", 1.0),
                    )
                )

        # 4. Integrate with Qdrant (Vector Embedding)
        try:
            embeddings = await self.ai.generate_embeddings([fragment_text])
            if embeddings:
                vector = embeddings[0]
                await qdrant_service.upsert_vectors(
                    project_id=project_id,
                    points=[
                        PointStruct(
                            id=str(fragment_id),
                            vector=vector,
                            payload={
                                "text": fragment_text,
                                "project_id": str(project_id),
                                "codes": [c[1] for c in codes_to_sync]
                            }
                        )
                    ]
                )
                # Mark as synced in Postgres
                await db.execute(
                    update(Fragment)
                    .where(Fragment.id == fragment_id)
                    .values(embedding_synced=True)
                )
        except Exception as e:
            logger.error(f"Failed to sync embedding for fragment {fragment_id}: {e}")

        # 5. Integrate with Neo4j (Knowledge Graph)
        try:
            # Sync Fragment Node
            await neo4j_service.create_fragment_node(project_id, fragment_id, fragment_text)
            
            # Sync Code Nodes and Relationships
            for code_id, label in codes_to_sync:
                await neo4j_service.create_code_node(project_id, code_id, label)
                await neo4j_service.create_code_fragment_relation(code_id, fragment_id)
                
        except Exception as e:
            logger.error(f"Failed to sync graph for fragment {fragment_id}: {e}")

        return coding_results

    async def auto_code_interview(self, project_id: UUID, interview_id: UUID, db: AsyncSession):
        """
        Iterates through all fragments of an interview and codes them.
        """
        # Ensure project node exists in Neo4j before syncing dependent nodes.
        project_result = await db.execute(
            select(Project).where(Project.id == project_id)
        )
        project = project_result.scalar_one_or_none()
        if not project:
            raise ValueError(f"Project {project_id} not found")

        await neo4j_service.ensure_project_node(project_id, project.name)
        
        frag_result = await db.execute(
            select(Fragment).filter(Fragment.interview_id == interview_id)
        )
        fragments = frag_result.scalars().all()

        for fragment in fragments:
            await self.process_fragment(project_id, fragment.id, fragment.text, db)
            
        await db.commit()

coding_engine = CodingEngine()
