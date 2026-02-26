# backend/app/engines/coding_engine.py
from __future__ import annotations

import asyncio
import logging
from uuid import UUID
from typing import Optional, Tuple

from qdrant_client.models import PointStruct
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.json_utils import safe_json_loads
from ..core.settings import settings
from ..models.models import Code, Fragment, Project, code_fragment_links
from ..prompts.axial_coding import AXIAL_CODING_SYSTEM_PROMPT, get_coding_user_prompt
from ..services.azure_openai import foundry_openai
from ..services.neo4j_service import neo4j_service
from ..services.qdrant_service import qdrant_service

logger = logging.getLogger(__name__)


def _normalize_extracted_code(code_data):
    """
    Normalize model output to support dict and string code formats.
    Supported formats:
    - {"label": "...", "definition": "...", "confidence": 0.9}
    - "code label"
    """
    if isinstance(code_data, dict):
        label = (code_data.get("label") or "").strip()
        definition = (code_data.get("definition") or "").strip()
        confidence = code_data.get("confidence", 1.0)
        evidence_text = (
            code_data.get("evidence_text")
            or code_data.get("quote")
            or code_data.get("evidence")
            or code_data.get("text_span")
            or ""
        )
    elif isinstance(code_data, str):
        label = code_data.strip()
        definition = ""
        confidence = 1.0
        evidence_text = ""
    else:
        return None

    if not label:
        return None

    return {
        "label": label,
        "definition": definition,
        "confidence": confidence,
        "evidence_text": evidence_text,
    }


def _infer_char_span(fragment_text: str, evidence_text: str) -> Tuple[Optional[int], Optional[int]]:
    if not fragment_text or not evidence_text:
        return None, None

    needle = str(evidence_text).strip()
    if not needle:
        return None, None

    pos = fragment_text.find(needle)
    if pos < 0:
        pos = fragment_text.lower().find(needle.lower())
    if pos < 0:
        return None, None
    return pos, pos + len(needle)


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
        {label_lower: Code} dict that avoids re-querying the DB on every call.
        """
        if codes_cache is None:
            existing_list = (
                await db.execute(select(Code).filter(Code.project_id == project_id))
            ).scalars().all()
            codes_cache = {
                (c.label or "").strip().lower(): c
                for c in existing_list
                if c.label
            }

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
            coding_results = safe_json_loads(raw)
        except Exception as e:
            logger.error("AI coding failed for fragment %s: %s", fragment_id, e)
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
            char_start, char_end = _infer_char_span(fragment_text, code_data.get("evidence_text", ""))
            links_to_insert.append(
                {
                    "code_id": code_id,
                    "fragment_id": fragment_id,
                    "confidence": code_data.get("confidence", 1.0),
                    "source": "ai",
                    "char_start": char_start,
                    "char_end": char_end,
                }
            )

        if links_to_insert:
            await db.execute(
                pg_insert(code_fragment_links).values(links_to_insert).on_conflict_do_nothing()
            )

        try:
            embeddings = await self.ai.generate_embeddings([fragment_text])
            if embeddings:
                await asyncio.wait_for(
                    qdrant_service.upsert_vectors(
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
                    ),
                    timeout=max(5, int(settings.CODING_QDRANT_UPSERT_TIMEOUT_SECONDS)),
                )
                await db.execute(
                    update(Fragment).where(Fragment.id == fragment_id).values(embedding_synced=True)
                )
        except Exception as e:
            logger.error("Embedding sync failed for fragment %s: %s", fragment_id, e)

        try:
            await asyncio.wait_for(
                neo4j_service.create_fragment_node(project_id, fragment_id, fragment_text),
                timeout=max(5, int(settings.CODING_NEO4J_SYNC_TIMEOUT_SECONDS)),
            )
            for code_id, label in codes_to_sync:
                await asyncio.wait_for(
                    neo4j_service.create_code_node(project_id, code_id, label),
                    timeout=max(5, int(settings.CODING_NEO4J_SYNC_TIMEOUT_SECONDS)),
                )
                await asyncio.wait_for(
                    neo4j_service.create_code_fragment_relation(code_id, fragment_id),
                    timeout=max(5, int(settings.CODING_NEO4J_SYNC_TIMEOUT_SECONDS)),
                )
        except Exception as e:
            logger.error("Neo4j sync failed for fragment %s: %s", fragment_id, e)

        return coding_results

    async def _get_or_create_code(
        self,
        db: AsyncSession,
        project_id: UUID,
        label: str,
        code_data: dict,
        codes_cache: dict,
    ) -> UUID:
        """Return the id of an existing or newly-created Code, updating cache."""
        label = label.strip()
        label_lower = label.lower()
        if label_lower in codes_cache:
            return codes_cache[label_lower].id

        existing = (
            await db.execute(
                select(Code)
                .filter(
                    func.lower(func.trim(Code.label)) == label_lower,
                    Code.project_id == project_id,
                )
                .limit(1)
            )
        ).scalars().first()
        if existing:
            codes_cache[label_lower] = existing
            return existing.id

        new_code = Code(
            project_id=project_id,
            label=label,
            definition=code_data.get("definition", ""),
            created_by="ai",
        )
        db.add(new_code)
        await db.flush()
        codes_cache[label_lower] = new_code
        return new_code.id

    async def auto_code_interview(self, project_id: UUID, interview_id: UUID, db: AsyncSession):
        """
        Two-phase batch processor for a full interview:
        1) Parallel LLM coding calls (no DB writes).
        2) Sequential DB writes + batch Qdrant + batch Neo4j sync.
        """
        project = (
            await db.execute(select(Project).where(Project.id == project_id).limit(1))
        ).scalars().first()
        if not project:
            raise ValueError(f"Project {project_id} not found")

        await neo4j_service.ensure_project_node(project_id, project.name)

        fragments = (
            await db.execute(select(Fragment).filter(Fragment.interview_id == interview_id))
        ).scalars().all()
        if not fragments:
            logger.info("[coding][%s] no fragments, skipping", interview_id)
            return

        codes_cache: dict[str, Code] = {
            (c.label or "").strip().lower(): c
            for c in (
                await db.execute(select(Code).filter(Code.project_id == project_id))
            ).scalars().all()
            if c.label
        }
        codes_snapshot = [
            {"label": c.label, "definition": c.definition}
            for c in codes_cache.values()
        ]

        logger.info(
            "[coding][%s] cache=%d codes fragments=%d",
            interview_id,
            len(codes_cache),
            len(fragments),
        )

        sem = asyncio.Semaphore(max(1, settings.CODING_FRAGMENT_CONCURRENCY))

        async def _call_llm(fragment: Fragment):
            async with sem:
                try:
                    raw = await self.ai.claude_analysis(
                        messages=[
                            {"role": "system", "content": AXIAL_CODING_SYSTEM_PROMPT},
                            {"role": "user", "content": get_coding_user_prompt(fragment.text, codes_snapshot)},
                        ],
                        response_format={"type": "json_object"},
                    )
                    return fragment, safe_json_loads(raw)
                except Exception as e:
                    logger.error("LLM coding failed for fragment %s: %s", fragment.id, e)
                    return fragment, {}

        llm_results: list[tuple[Fragment, dict]] = await asyncio.gather(
            *[_call_llm(f) for f in fragments]
        )

        neo4j_pairs: list[tuple[UUID, UUID]] = []
        embed_texts: list[str] = []
        embed_frag_ids: list[UUID] = []
        embed_code_labels: list[list[str]] = []
        embed_created_at: list[str | None] = []

        for fragment, coding_result in llm_results:
            labels_this_frag: list[str] = []
            links_to_insert: list[dict] = []

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
                char_start, char_end = _infer_char_span(fragment.text, code_data.get("evidence_text", ""))
                links_to_insert.append(
                    {
                        "code_id": code_id,
                        "fragment_id": fragment.id,
                        "confidence": code_data.get("confidence", 1.0),
                        "source": "ai",
                        "char_start": char_start,
                        "char_end": char_end,
                    }
                )

            if links_to_insert:
                await db.execute(
                    pg_insert(code_fragment_links)
                    .values(links_to_insert)
                    .on_conflict_do_nothing()
                )

            embed_texts.append(fragment.text)
            embed_frag_ids.append(fragment.id)
            embed_code_labels.append(labels_this_frag)
            embed_created_at.append(fragment.created_at.isoformat() if getattr(fragment, "created_at", None) else None)

        try:
            # Embeddings can be a long pole; guard with timeouts/retries inside the service.
            all_embeddings = await self.ai.generate_embeddings(embed_texts)
            qdrant_points = [
                PointStruct(
                    id=str(fid),
                    vector=vec,
                    payload={
                        "text": txt,
                        "project_id": str(project_id),
                        "owner_id": str(project.owner_id) if getattr(project, "owner_id", None) else None,
                        "interview_id": str(interview_id),
                        "fragment_id": str(fid),
                        "source_type": "fragment",
                        "created_at": created_at,
                        "codes": labels,
                    },
                )
                for fid, txt, labels, created_at, vec in zip(
                    embed_frag_ids, embed_texts, embed_code_labels, embed_created_at, all_embeddings
                )
            ]
            if qdrant_points:
                await asyncio.wait_for(
                    qdrant_service.upsert_vectors(project_id=project_id, points=qdrant_points),
                    timeout=max(5, int(settings.CODING_QDRANT_UPSERT_TIMEOUT_SECONDS)),
                )

            # Mark only the fragments we successfully embedded (zip() may truncate on mismatch).
            embedded_ids = embed_frag_ids[: len(all_embeddings)]
            if embedded_ids:
                await db.execute(
                    update(Fragment).where(Fragment.id.in_(embedded_ids)).values(embedding_synced=True)
                )
        except Exception as e:
            logger.error("Batch Qdrant upsert failed for interview %s: %s", interview_id, e)

        try:
            await asyncio.wait_for(
                neo4j_service.batch_sync_interview(
                    project_id=project_id,
                    fragments=[(f.id, f.text) for f in fragments],
                    codes_cache=codes_cache,
                    fragment_code_pairs=neo4j_pairs,
                ),
                timeout=max(5, int(settings.CODING_NEO4J_SYNC_TIMEOUT_SECONDS)),
            )
        except Exception as e:
            logger.error("Batch Neo4j sync failed for interview %s: %s", interview_id, e)

        await db.commit()
        logger.info(
            "[coding][%s] complete fragments=%d total_codes=%d",
            interview_id,
            len(fragments),
            len(codes_cache),
        )


coding_engine = CodingEngine()
