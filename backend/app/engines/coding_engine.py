# backend/app/engines/coding_engine.py
from ..services.azure_openai import foundry_openai
from ..services.qdrant_service import qdrant_service
from ..services.neo4j_service import neo4j_service
from ..prompts.axial_coding import AXIAL_CODING_SYSTEM_PROMPT, get_coding_user_prompt
import json
import logging
import asyncio
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert
from ..models.models import Fragment, Code, Project, code_fragment_links
from sqlalchemy import select, update
from qdrant_client.models import PointStruct

logger = logging.getLogger(__name__)


def _normalize_extracted_code(code_data):
    """
    Normaliza la salida del modelo para aceptar códigos como dict o string.
    Formatos soportados:
    - {"label": "...", "definition": "...", "confidence": 0.9}
    - "label del código"
    """
    if isinstance(code_data, dict):
        label = (code_data.get("label") or "").strip()
        definition = (code_data.get("definition") or "").strip()
        confidence = code_data.get("confidence", 1.0)
    elif isinstance(code_data, str):
        label = code_data.strip()
        definition = ""
        confidence = 1.0
    else:
        return None

    if not label:
        return None

    return {
        "label": label,
        "definition": definition,
        "confidence": confidence,
    }

class CodingEngine:
    """Engine responsible for Open and Axial coding of fragments."""

    def __init__(self):
        self.ai = foundry_openai

    async def process_fragment(
        self,
        project_id: UUID,
        fragment_id: UUID,
        fragment_text: str,
        db: AsyncSession,
        codes_cache: dict | None = None,
    ) -> dict:
        """
        Codes a single fragment. `codes_cache` (optional) is a shared
        {label: Code} dict that avoids re-querying the DB on every call.
        When not provided a fresh query is issued (backward-compatible).
        """
        if codes_cache is None:
            existing_list = (await db.execute(
                select(Code).filter(Code.project_id == project_id)
            )).scalars().all()
            codes_cache = {c.label: c for c in existing_list}

        codes_snapshot = [
            {"label": c.label, "definition": c.definition}
            for c in codes_cache.values()
        ]

        try:
            raw = await self.ai.claude_analysis(
                messages=[
                    {"role": "system", "content": AXIAL_CODING_SYSTEM_PROMPT},
                    {"role": "user", "content": get_coding_user_prompt(fragment_text, codes_snapshot)},
                ],
                response_format={"type": "json_object"},
            )
            coding_results = json.loads(raw)
        except Exception as e:
            logger.error("AI Coding failed for fragment %s: %s", fragment_id, e)
            return {}

        codes_to_sync: list[tuple[UUID, str]] = []
        links_to_insert: list[dict] = []
        for raw_code in coding_results.get("extracted_codes", []):
            code_data = _normalize_extracted_code(raw_code)
            if not code_data:
                continue
            label = code_data.get("label", "").strip()
            if not label:
                continue
            code_id = await self._get_or_create_code(db, project_id, label, code_data, codes_cache)
            codes_to_sync.append((code_id, label))
            links_to_insert.append({
                "code_id": code_id,
                "fragment_id": fragment_id,
                "confidence": code_data.get("confidence", 1.0),
            })

        if links_to_insert:
            await db.execute(
                pg_insert(code_fragment_links).values(links_to_insert).on_conflict_do_nothing()
            )

        try:
            embeddings = await self.ai.generate_embeddings([fragment_text])
            if embeddings:
                await qdrant_service.upsert_vectors(
                    project_id=project_id,
                    points=[
                        PointStruct(
                            id=str(fragment_id),
                            vector=embeddings[0],
                            payload={
                                "text": fragment_text,
                                "project_id": str(project_id),
                                "codes": [lbl for _, lbl in codes_to_sync],
                            },
                        )
                    ],
                )
                await db.execute(
                    update(Fragment).where(Fragment.id == fragment_id).values(embedding_synced=True)
                )
        except Exception as e:
            logger.error("Embedding sync failed for fragment %s: %s", fragment_id, e)

        try:
            await neo4j_service.create_fragment_node(project_id, fragment_id, fragment_text)
            for code_id, label in codes_to_sync:
                await neo4j_service.create_code_node(project_id, code_id, label)
                await neo4j_service.create_code_fragment_relation(code_id, fragment_id)
        except Exception as e:
            logger.error("Neo4j sync failed for fragment %s: %s", fragment_id, e)

        return coding_results

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _get_or_create_code(
        self,
        db: AsyncSession,
        project_id: UUID,
        label: str,
        code_data: dict,
        codes_cache: dict,
    ) -> UUID:
        """Return the id of an existing or newly-created Code, updating the cache."""
        if label in codes_cache:
            return codes_cache[label].id
        existing = (
            await db.execute(
                select(Code).filter(Code.label == label, Code.project_id == project_id)
            )
        ).scalar_one_or_none()
        if existing:
            codes_cache[label] = existing
            return existing.id
        new_code = Code(
            project_id=project_id,
            label=label,
            definition=code_data.get("definition", ""),
            created_by="ai",
        )
        db.add(new_code)
        await db.flush()
        codes_cache[label] = new_code
        return new_code.id

    # ── Batch interview coding ────────────────────────────────────────────────

    async def auto_code_interview(self, project_id: UUID, interview_id: UUID, db: AsyncSession):
        """
        Two-phase batch processor for a full interview:

        Phase 1 – Parallel LLM calls (Semaphore 8, zero DB writes).
          All fragments are coded concurrently using the project codes snapshot
          captured before the phase starts.

        Phase 2 – Sequential DB writes using a shared codes_cache (eliminates
          N+1 SELECT), then single-call batch Qdrant upsert and Neo4j UNWIND
          sync (3 queries total for the whole interview).
        """
        project = (
            await db.execute(select(Project).where(Project.id == project_id))
        ).scalar_one_or_none()
        if not project:
            raise ValueError(f"Project {project_id} not found")
        await neo4j_service.ensure_project_node(project_id, project.name)

        fragments = (
            await db.execute(select(Fragment).filter(Fragment.interview_id == interview_id))
        ).scalars().all()
        if not fragments:
            logger.info("[coding][%s] No fragments, skipping.", interview_id)
            return

        # ── Load codes cache ONCE (eliminates per-fragment SELECT) ────────────
        codes_cache: dict[str, Code] = {
            c.label: c
            for c in (
                await db.execute(select(Code).filter(Code.project_id == project_id))
            ).scalars().all()
        }
        codes_snapshot = [
            {"label": c.label, "definition": c.definition} for c in codes_cache.values()
        ]
        logger.info(
            "[coding][%s] cache=%d codes  fragments=%d",
            interview_id, len(codes_cache), len(fragments),
        )

        # ── PHASE 1: Parallel LLM calls ───────────────────────────────────────
        _sem = asyncio.Semaphore(8)

        async def _call_llm(fragment: Fragment):
            async with _sem:
                try:
                    raw = await self.ai.claude_analysis(
                        messages=[
                            {"role": "system", "content": AXIAL_CODING_SYSTEM_PROMPT},
                            {"role": "user", "content": get_coding_user_prompt(fragment.text, codes_snapshot)},
                        ],
                        response_format={"type": "json_object"},
                    )
                    return fragment, json.loads(raw)
                except Exception as e:
                    logger.error("LLM coding failed for fragment %s: %s", fragment.id, e)
                    return fragment, {}

        llm_results: list[tuple[Fragment, dict]] = await asyncio.gather(
            *[_call_llm(f) for f in fragments]
        )
        logger.info("[coding][%s] Phase 1 DONE – %d LLM calls", interview_id, len(fragments))

        # ── PHASE 2: Sequential DB writes + collect for batch ops ─────────────
        neo4j_pairs: list[tuple[UUID, UUID]] = []   # (fragment_id, code_id)
        embed_texts:  list[str]  = []
        embed_frag_ids: list[UUID] = []
        embed_code_labels: list[list[str]] = []

        for fragment, coding_result in llm_results:
            labels_this_frag: list[str] = []
            links_to_insert:  list[dict] = []

            for raw_code in coding_result.get("extracted_codes", []):
                code_data = _normalize_extracted_code(raw_code)
                if not code_data:
                    continue
                label = code_data.get("label", "").strip()
                if not label:
                    continue
                code_id = await self._get_or_create_code(
                    db, project_id, label, code_data, codes_cache
                )
                labels_this_frag.append(label)
                neo4j_pairs.append((fragment.id, code_id))
                links_to_insert.append({
                    "code_id": code_id,
                    "fragment_id": fragment.id,
                    "confidence": code_data.get("confidence", 1.0),
                })

            if links_to_insert:
                await db.execute(
                    pg_insert(code_fragment_links)
                    .values(links_to_insert)
                    .on_conflict_do_nothing()
                )

            embed_texts.append(fragment.text)
            embed_frag_ids.append(fragment.id)
            embed_code_labels.append(labels_this_frag)

        logger.info(
            "[coding][%s] Phase 2 DONE – codes_cache=%d", interview_id, len(codes_cache)
        )

        # ── Batch Qdrant upsert (N fragments → 1 embedding API call) ─────────
        try:
            all_embeddings = await self.ai.generate_embeddings(embed_texts)
            qdrant_points = [
                PointStruct(
                    id=str(fid),
                    vector=vec,
                    payload={"text": txt, "project_id": str(project_id), "codes": labels},
                )
                for fid, txt, labels, vec in zip(
                    embed_frag_ids, embed_texts, embed_code_labels, all_embeddings
                )
            ]
            if qdrant_points:
                await qdrant_service.upsert_vectors(project_id=project_id, points=qdrant_points)
            if embed_frag_ids:
                await db.execute(
                    update(Fragment)
                    .where(Fragment.id.in_(embed_frag_ids))
                    .values(embedding_synced=True)
                )
            logger.info(
                "[coding][%s] Batch Qdrant: %d points upserted", interview_id, len(qdrant_points)
            )
        except Exception as e:
            logger.error("Batch Qdrant upsert failed for interview %s: %s", interview_id, e)

        # ── Batch Neo4j UNWIND (3 queries total for the interview) ────────────
        try:
            await neo4j_service.batch_sync_interview(
                project_id=project_id,
                fragments=[(f.id, f.text) for f in fragments],
                codes_cache=codes_cache,
                fragment_code_pairs=neo4j_pairs,
            )
            logger.info("[coding][%s] Batch Neo4j sync complete", interview_id)
        except Exception as e:
            logger.error("Batch Neo4j sync failed for interview %s: %s", interview_id, e)

        await db.commit()
        logger.info(
            "[coding][%s] COMPLETE – %d fragments  %d codes total",
            interview_id, len(fragments), len(codes_cache),
        )

coding_engine = CodingEngine()
