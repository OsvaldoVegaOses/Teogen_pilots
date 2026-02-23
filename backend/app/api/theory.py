from __future__ import annotations

import asyncio
import json as _json
import logging
import time
import uuid
from datetime import datetime
from json import JSONDecodeError
from typing import Any, Dict, List, Optional, Set
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import MultipleResultsFound
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import CurrentUser, get_current_user
from ..core.settings import settings
from ..database import get_db, get_session_local
from ..engines.coding_engine import coding_engine
from ..engines.theory_engine import theory_engine
from ..models.models import Category, Code, Project, Theory
from ..schemas.theory import TheoryGenerateRequest, TheoryResponse
from ..services.azure_openai import foundry_openai
from ..services.export_service import export_service
from ..services.neo4j_service import neo4j_service
from ..services.qdrant_service import qdrant_service
from ..services.storage_service import storage_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects", tags=["Theory"])

_TASK_TTL = 86400
_TASK_PREFIX = "theory_task:"
_LOCK_PREFIX = "theory_lock:"
_redis_client = None
_theory_tasks: Dict[str, Dict[str, Any]] = {}
_background_tasks: Set[asyncio.Task] = set()


def _use_celery_mode() -> bool:
    return bool(settings.THEORY_USE_CELERY and settings.AZURE_REDIS_HOST and settings.AZURE_REDIS_KEY)


async def _get_redis():
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    try:
        if not (settings.AZURE_REDIS_HOST and settings.AZURE_REDIS_KEY):
            return None
        import redis.asyncio as aioredis

        _redis_client = aioredis.Redis(
            host=settings.AZURE_REDIS_HOST,
            port=settings.REDIS_SSL_PORT,
            password=settings.AZURE_REDIS_KEY,
            ssl=True,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        await _redis_client.ping()
        logger.info("Redis task store connected: %s", settings.AZURE_REDIS_HOST)
    except Exception as e:
        logger.warning("Redis task store unavailable, using memory only: %s", e)
        _redis_client = None
    return _redis_client


async def _persist_task(task_id: str) -> None:
    task = _theory_tasks.get(task_id)
    if not task:
        return
    redis = await _get_redis()
    if redis:
        try:
            await redis.setex(
                f"{_TASK_PREFIX}{task_id}",
                _TASK_TTL,
                _json.dumps(task, default=str),
            )
        except Exception as e:
            logger.warning("Redis persist failed for task %s: %s", task_id, e)


async def _restore_task(task_id: str) -> Optional[Dict[str, Any]]:
    if task_id in _theory_tasks:
        return _theory_tasks[task_id]
    redis = await _get_redis()
    if not redis:
        return None
    try:
        raw = await redis.get(f"{_TASK_PREFIX}{task_id}")
        if raw:
            task = _json.loads(raw)
            _theory_tasks[task_id] = task
            return task
    except Exception as e:
        logger.warning("Redis restore failed for task %s: %s", task_id, e)
    return None


def _new_task_payload(task_id: str, project_id: UUID, user_uuid: UUID) -> Dict[str, Any]:
    return {
        "task_id": task_id,
        "status": "pending",
        "result": None,
        "error": None,
        "error_code": None,
        "project_id": str(project_id),
        "owner_id": str(user_uuid),
        "step": "queued",
        "progress": 0,
        "next_poll_seconds": max(2, settings.THEORY_STATUS_POLL_HINT_SECONDS),
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
    }


async def _set_task_state(
    task_id: str,
    *,
    status_value: Optional[str] = None,
    step: Optional[str] = None,
    progress: Optional[int] = None,
    error: Optional[str] = None,
    error_code: Optional[str] = None,
    result: Any = None,
) -> None:
    task = _theory_tasks.get(task_id)
    if not task:
        return
    if status_value is not None:
        task["status"] = status_value
    if step is not None:
        task["step"] = step
    if progress is not None:
        task["progress"] = max(0, min(100, int(progress)))
    if error is not None:
        task["error"] = error
    if error_code is not None:
        task["error_code"] = error_code
    if result is not None:
        task["result"] = result
    task["next_poll_seconds"] = max(2, settings.THEORY_STATUS_POLL_HINT_SECONDS)
    task["updated_at"] = datetime.utcnow().isoformat()
    await _persist_task(task_id)


async def _acquire_project_lock(project_id: UUID, task_id: str) -> Optional[str]:
    """Return None when acquired; otherwise return existing task_id."""
    redis = await _get_redis()
    if not redis:
        return None
    lock_key = f"{_LOCK_PREFIX}{project_id}"
    ttl = max(60, settings.THEORY_TASK_LOCK_TTL_SECONDS)
    try:
        acquired = await redis.set(lock_key, task_id, ex=ttl, nx=True)
        if acquired:
            return None
        return await redis.get(lock_key)
    except Exception as e:
        logger.warning("Redis lock acquire failed for project %s: %s", project_id, e)
        return None


async def _refresh_project_lock(project_id: UUID, task_id: str) -> None:
    redis = await _get_redis()
    if not redis:
        return
    lock_key = f"{_LOCK_PREFIX}{project_id}"
    ttl = max(60, settings.THEORY_TASK_LOCK_TTL_SECONDS)
    try:
        current = await redis.get(lock_key)
        if current == task_id:
            await redis.expire(lock_key, ttl)
    except Exception as e:
        logger.warning("Redis lock refresh failed for project %s: %s", project_id, e)


async def _release_project_lock(project_id: UUID, task_id: str) -> None:
    redis = await _get_redis()
    if not redis:
        return
    lock_key = f"{_LOCK_PREFIX}{project_id}"
    try:
        current = await redis.get(lock_key)
        if current == task_id:
            await redis.delete(lock_key)
    except Exception as e:
        logger.warning("Redis lock release failed for project %s: %s", project_id, e)


def _t(label: str, task_id: str, t0: float) -> float:
    elapsed = time.perf_counter() - t0
    logger.info("[theory][%s] step=%s elapsed=%.2fs", task_id, label, elapsed)
    return time.perf_counter()


async def _mark_step(task_id: str, step: str, progress: int) -> None:
    await _set_task_state(task_id, step=step, progress=progress)


def _slim_cats_for_llm(cats_data: list, network_metrics: dict) -> list:
    """Return a token-safe slice of cats_data, sorted by network centrality.

    - Caps to THEORY_MAX_CATS_FOR_LLM categories (most central first).
    - Caps evidence fragments per category and truncates fragment text.
    - Does NOT mutate the original list.
    """
    centrality_rank: dict[str, int] = {
        item.get("category_id", ""): idx
        for idx, item in enumerate(network_metrics.get("category_centrality", []))
    }
    sorted_cats = sorted(cats_data, key=lambda c: centrality_rank.get(c["id"], 9999))
    result = []
    for cat in sorted_cats[:settings.THEORY_MAX_CATS_FOR_LLM]:
        frags_slimmed = []
        for frag in cat.get("semantic_evidence", [])[:settings.THEORY_MAX_EVIDENCE_FRAGS]:
            if isinstance(frag, dict) and "text" in frag:
                frag = {**frag, "text": frag["text"][:settings.THEORY_MAX_FRAG_CHARS]}
            frags_slimmed.append(frag)
        result.append({**cat, "semantic_evidence": frags_slimmed})
    return result


def _slim_network_for_llm(network_metrics: dict) -> dict:
    """Return network_metrics with list sizes capped to THEORY_MAX_NETWORK_TOP."""
    top_n = settings.THEORY_MAX_NETWORK_TOP
    return {
        "counts": network_metrics.get("counts", {}),
        "category_centrality": network_metrics.get("category_centrality", [])[:top_n],
        "category_cooccurrence": network_metrics.get("category_cooccurrence", [])[:top_n],
    }


def _cats_no_evidence(cats_data: list) -> list:
    """Strip semantic_evidence for the Straussian build call (evidence already consumed in step 1)."""
    return [
        {"id": c["id"], "name": c["name"], "description": c.get("description", "")}
        for c in cats_data
    ]


async def _run_theory_pipeline(task_id: str, project_id: UUID, user_uuid: UUID, request: TheoryGenerateRequest):
    wall_start = time.perf_counter()
    logger.info("[theory] task %s STARTED for project %s", task_id, project_id)
    await _set_task_state(task_id, status_value="running", step="pipeline_start", progress=2)
    try:
        session_local = get_session_local()
        async with session_local() as db:
            await _theory_pipeline(task_id, project_id, user_uuid, request, db)
    except (MultipleResultsFound, JSONDecodeError) as e:
        logger.exception("[theory] task %s failed with known data error", task_id)
        await _set_task_state(
            task_id,
            status_value="failed",
            step="failed",
            progress=100,
            error=str(e),
            error_code="DATA_CONSISTENCY_ERROR",
        )
    except Exception as e:
        logger.exception("[theory] task %s CRASHED: %s", task_id, e)
        await _set_task_state(
            task_id,
            status_value="failed",
            step="failed",
            progress=100,
            error=str(e),
            error_code="PIPELINE_ERROR",
        )
    finally:
        await _release_project_lock(project_id, task_id)
        elapsed = time.perf_counter() - wall_start
        logger.info(
            "[theory] task %s FINISHED status=%s total_elapsed=%.1fs",
            task_id,
            _theory_tasks.get(task_id, {}).get("status"),
            elapsed,
        )


@router.post("/{project_id}/generate-theory", status_code=202)
async def generate_theory(
    project_id: UUID,
    request: TheoryGenerateRequest,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project_result = await db.execute(
        select(Project).where(Project.id == project_id, Project.owner_id == user.user_uuid)
    )
    project = project_result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    task_id = str(uuid.uuid4())
    existing_task_id = await _acquire_project_lock(project_id, task_id)
    if existing_task_id and existing_task_id != task_id:
        existing_task = _theory_tasks.get(existing_task_id) or await _restore_task(existing_task_id)
        if existing_task and existing_task.get("owner_id") == str(user.user_uuid):
            return {
                "task_id": existing_task_id,
                "status": existing_task.get("status", "running"),
                "reused": True,
                "next_poll_seconds": settings.THEORY_STATUS_POLL_HINT_SECONDS,
                "execution_mode": existing_task.get("execution_mode", "local"),
            }
        if not existing_task:
            # Stale lock without task payload: clear and retry once.
            await _release_project_lock(project_id, existing_task_id)
            retry_existing = await _acquire_project_lock(project_id, task_id)
            if retry_existing in (None, task_id):
                existing_task_id = None
            else:
                existing_task = _theory_tasks.get(retry_existing) or await _restore_task(retry_existing)
                if existing_task and existing_task.get("owner_id") == str(user.user_uuid):
                    return {
                        "task_id": retry_existing,
                        "status": existing_task.get("status", "running"),
                        "reused": True,
                        "next_poll_seconds": settings.THEORY_STATUS_POLL_HINT_SECONDS,
                        "execution_mode": existing_task.get("execution_mode", "local"),
                    }
        raise HTTPException(
            status_code=409,
            detail="A theory generation task is already running for this project.",
        )

    _theory_tasks[task_id] = _new_task_payload(task_id, project_id, user.user_uuid)
    _theory_tasks[task_id]["execution_mode"] = "celery" if _use_celery_mode() else "local"
    await _persist_task(task_id)
    try:
        if _use_celery_mode():
            from ..tasks.theory_tasks import run_theory_pipeline_task

            celery_task = run_theory_pipeline_task.delay(
                task_id=task_id,
                project_id=str(project_id),
                user_uuid=str(user.user_uuid),
                request_payload=request.model_dump(),
            )
            _theory_tasks[task_id]["worker_task_id"] = celery_task.id
            await _persist_task(task_id)
            logger.info(
                "[theory] enqueued task %s for project %s via celery worker_task_id=%s",
                task_id,
                project_id,
                celery_task.id,
            )
        else:
            bg_task = asyncio.create_task(_run_theory_pipeline(task_id, project_id, user.user_uuid, request))
            _background_tasks.add(bg_task)
            bg_task.add_done_callback(_background_tasks.discard)
            logger.info("[theory] enqueued task %s for project %s in local mode", task_id, project_id)
    except Exception as e:
        await _release_project_lock(project_id, task_id)
        await _set_task_state(
            task_id,
            status_value="failed",
            step="enqueue",
            progress=100,
            error=f"Failed to enqueue theory task: {e}",
            error_code="ENQUEUE_ERROR",
        )
        raise HTTPException(status_code=500, detail="Failed to enqueue theory task")
    return {
        "task_id": task_id,
        "status": "pending",
        "next_poll_seconds": settings.THEORY_STATUS_POLL_HINT_SECONDS,
        "execution_mode": _theory_tasks[task_id]["execution_mode"],
    }


@router.get("/{project_id}/generate-theory/status/{task_id}")
async def get_theory_task_status(
    project_id: UUID,
    task_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    task = _theory_tasks.get(task_id) or await _restore_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.get("project_id") != str(project_id) or task.get("owner_id") != str(user.user_uuid):
        raise HTTPException(status_code=404, detail="Task not found")
    task["next_poll_seconds"] = max(2, settings.THEORY_STATUS_POLL_HINT_SECONDS)
    return task


async def _theory_pipeline(
    task_id: str,
    project_id: UUID,
    user_uuid: UUID,
    request: TheoryGenerateRequest,
    db: AsyncSession,
):
    pipeline_start = time.perf_counter()
    t0 = pipeline_start

    await _mark_step(task_id, "load_project", 5)
    project_result = await db.execute(
        select(Project).where(Project.id == project_id, Project.owner_id == user_uuid)
    )
    project = project_result.scalar_one_or_none()
    if not project:
        await _set_task_state(
            task_id,
            status_value="failed",
            step="load_project",
            progress=100,
            error="Project not found",
            error_code="NOT_FOUND",
        )
        return
    t0 = _t("load_project", task_id, t0)

    await _mark_step(task_id, "load_categories", 10)
    cat_result = await db.execute(select(Category).filter(Category.project_id == project_id))
    categories = cat_result.scalars().all()
    t0 = _t("load_categories", task_id, t0)

    if len(categories) < 2:
        code_exists_result = await db.execute(
            select(Code.id).where(Code.project_id == project_id).limit(1)
        )

        if code_exists_result.first() is None:
            from ..models.models import Interview

            completed_interviews_result = await db.execute(
                select(Interview).where(
                    Interview.project_id == project_id,
                    Interview.transcription_status == "completed",
                    Interview.full_text.isnot(None),
                )
            )
            completed_interviews = completed_interviews_result.scalars().all()
            await _mark_step(task_id, "auto_code", 25)

            t_ac = time.perf_counter()
            session_local = get_session_local()
            sem = asyncio.Semaphore(max(1, settings.THEORY_INTERVIEW_CONCURRENCY))

            async def _code_interview(iv_id):
                async with sem:
                    async with session_local() as iv_db:
                        await coding_engine.auto_code_interview(project_id, iv_id, iv_db)

            await asyncio.gather(*[_code_interview(iv.id) for iv in completed_interviews])
            logger.info(
                "[theory][%s] auto_code interviews=%d elapsed=%.2fs",
                task_id,
                len(completed_interviews),
                time.perf_counter() - t_ac,
            )
            await _refresh_project_lock(project_id, task_id)

        code_result = await db.execute(select(Code).filter(Code.project_id == project_id))
        codes_for_bootstrap = code_result.scalars().all()

        if len(codes_for_bootstrap) >= 2:
            category_by_label = {c.name.strip().lower(): c for c in categories if c.name}

            for code in codes_for_bootstrap:
                if code.category_id:
                    continue
                label = (code.label or "").strip()
                if not label:
                    continue

                key = label.lower()
                category = category_by_label.get(key)
                if not category:
                    category = Category(
                        project_id=project_id,
                        name=label[:500],
                        definition="Auto-generada desde codigos durante teorizacion",
                        created_at=datetime.utcnow(),
                    )
                    db.add(category)
                    await db.flush()
                    category_by_label[key] = category

                code.category_id = category.id

            await db.commit()
            cat_result = await db.execute(select(Category).filter(Category.project_id == project_id))
            categories = cat_result.scalars().all()

    if len(categories) < 2:
        from ..models.models import Interview

        interviews_total = (
            await db.execute(select(func.count()).select_from(Interview).where(Interview.project_id == project_id))
        ).scalar() or 0

        interviews_completed = (
            await db.execute(
                select(func.count())
                .select_from(Interview)
                .where(Interview.project_id == project_id, Interview.transcription_status == "completed")
            )
        ).scalar() or 0

        codes_total = (
            await db.execute(select(func.count()).select_from(Code).where(Code.project_id == project_id))
        ).scalar() or 0

        await _set_task_state(
            task_id,
            status_value="failed",
            step="validate_categories",
            progress=100,
            error=(
                "No hay suficientes categorias para teorizacion (minimo 2). "
                f"Estado actual: entrevistas={interviews_total}, entrevistas_completadas={interviews_completed}, "
                f"codigos={codes_total}, categorias={len(categories)}."
            ),
            error_code="INSUFFICIENT_CATEGORIES",
        )
        return

    await _mark_step(task_id, "neo4j_taxonomy_sync", 45)
    await neo4j_service.ensure_project_node(project_id, project.name)

    code_result = await db.execute(select(Code).filter(Code.project_id == project_id))
    codes = code_result.scalars().all()
    await neo4j_service.batch_sync_taxonomy(
        project_id=project_id,
        categories=[(cat.id, cat.name) for cat in categories],
        code_category_pairs=[(code.id, code.category_id) for code in codes if code.category_id],
    )
    t0 = _t("neo4j_taxonomy_sync", task_id, t0)

    try:
        cats_data = [
            {"id": str(c.id), "name": c.name, "description": c.definition or ""}
            for c in categories
        ]

        await _mark_step(task_id, "network_metrics", 60)
        t0 = time.perf_counter()
        network_metrics = await neo4j_service.get_project_network_metrics(project_id)
        t0 = _t("network_metrics", task_id, t0)

        await _mark_step(task_id, "semantic_evidence", 70)
        category_by_id = {str(c.id): c for c in categories}
        top_categories = [
            (item.get("category_id"), category_by_id.get(item.get("category_id")))
            for item in network_metrics.get("category_centrality", [])[:3]
            if category_by_id.get(item.get("category_id"))
        ]

        async def _fetch_evidence(category_id: str, category_obj):
            query_text = f"{category_obj.name}. {category_obj.definition or ''}".strip()
            embeddings = await foundry_openai.generate_embeddings([query_text])
            if not embeddings:
                return None
            fragments = await qdrant_service.search_supporting_fragments(
                project_id=project_id,
                query_vector=embeddings[0],
                limit=3,
            )
            return {
                "category_id": category_id,
                "category_name": category_obj.name,
                "fragments": fragments,
            }

        evidence_results = await asyncio.gather(
            *[_fetch_evidence(cid, cobj) for cid, cobj in top_categories],
            return_exceptions=False,
        )
        semantic_evidence = [r for r in evidence_results if r is not None]

        evidence_by_category = {
            item["category_id"]: item["fragments"] for item in semantic_evidence
        }
        for cat in cats_data:
            cat["semantic_evidence"] = evidence_by_category.get(cat["id"], [])

        await _mark_step(task_id, "identify_central_category", 80)
        cats_slim = _slim_cats_for_llm(cats_data, network_metrics)
        network_slim = _slim_network_for_llm(network_metrics)
        logger.info(
            "[theory][%s] context-slim: cats %d→%d evidence_frags<=%d frag_chars<=%d network_top=%d",
            task_id, len(cats_data), len(cats_slim),
            settings.THEORY_MAX_EVIDENCE_FRAGS, settings.THEORY_MAX_FRAG_CHARS,
            settings.THEORY_MAX_NETWORK_TOP,
        )
        central_cat_data = await theory_engine.identify_central_category(cats_slim, network_slim)

        await _mark_step(task_id, "build_straussian_paradigm", 87)
        # Pass cats without evidence — evidence was already used in step 1 (identify_central_category).
        # This avoids re-sending thousands of tokens of raw interview text.
        paradigm = await theory_engine.build_straussian_paradigm(
            central_cat_data["selected_central_category"],
            _cats_no_evidence(cats_slim),
        )

        await _mark_step(task_id, "analyze_saturation_and_gaps", 93)
        gaps = await theory_engine.analyze_saturation_and_gaps(paradigm)

        await _mark_step(task_id, "save_theory", 97)
        new_theory = Theory(
            project_id=project_id,
            model_json=paradigm,
            propositions=paradigm.get("propositions", []),
            validation={
                "gap_analysis": gaps,
                "network_metrics_summary": {
                    "counts": network_metrics.get("counts", {}),
                    "category_centrality_top": network_metrics.get("category_centrality", [])[:5],
                    "category_cooccurrence_top": network_metrics.get("category_cooccurrence", [])[:5],
                    "semantic_evidence_top": semantic_evidence,
                },
            },
            gaps=gaps.get("identified_gaps", []),
            confidence_score=paradigm.get("confidence_score", 0.7),
            generated_by="DeepSeek-V3.2-Speciale/Kimi-K2.5",
            status="completed",
        )

        db.add(new_theory)
        await db.commit()
        await db.refresh(new_theory)

        result_payload = {
            "id": str(new_theory.id),
            "project_id": str(new_theory.project_id),
            "version": new_theory.version,
            "status": new_theory.status,
            "confidence_score": new_theory.confidence_score,
            "generated_by": new_theory.generated_by,
            "model_json": new_theory.model_json,
            "propositions": new_theory.propositions,
            "gaps": new_theory.gaps,
            "validation": new_theory.validation,
            "created_at": new_theory.created_at.isoformat() if new_theory.created_at else None,
        }
        await _set_task_state(
            task_id,
            status_value="completed",
            step="completed",
            progress=100,
            result=result_payload,
        )
        await _refresh_project_lock(project_id, task_id)

        total_pipeline = time.perf_counter() - pipeline_start
        logger.info(
            "[theory][%s] completed theory_id=%s total_pipeline=%.1fs",
            task_id,
            new_theory.id,
            total_pipeline,
        )

    except Exception as e:
        await db.rollback()
        await _set_task_state(
            task_id,
            status_value="failed",
            step="failed",
            progress=100,
            error=f"Theory generation failed: {str(e)}",
            error_code="PIPELINE_ERROR",
        )


@router.get("/{project_id}/theories", response_model=List[TheoryResponse])
async def list_theories(
    project_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project_result = await db.execute(
        select(Project).where(Project.id == project_id, Project.owner_id == user.user_uuid)
    )
    if not project_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Project not found")

    result = await db.execute(select(Theory).filter(Theory.project_id == project_id))
    return result.scalars().all()


@router.post("/{project_id}/theories/{theory_id}/export")
async def export_theory_report(
    project_id: UUID,
    theory_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Theory, Project)
        .join(Project, Theory.project_id == Project.id)
        .where(
            Theory.id == theory_id,
            Theory.project_id == project_id,
            Project.owner_id == user.user_uuid,
        )
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Theory or Project not found")

    theory, project = row

    try:
        theory_dict = {
            "version": theory.version,
            "confidence_score": theory.confidence_score,
            "generated_by": theory.generated_by,
            "model_json": theory.model_json,
            "propositions": theory.propositions,
            "gaps": theory.gaps,
        }

        pdf_buffer = await export_service.generate_theory_pdf(
            project_name=project.name,
            language=project.language or "es",
            theory_data=theory_dict,
        )

        blob_name = f"{project_id}/reports/Theory_{theory_id}_{uuid.uuid4().hex[:8]}.pdf"

        await storage_service.upload_blob(
            container_key="exports",
            blob_name=blob_name,
            data=pdf_buffer.getvalue(),
        )

        download_url = await storage_service.generate_sas_url(
            container_key="exports",
            blob_name=blob_name,
            expires_hours=1,
        )

        return {
            "download_url": download_url,
            "filename": f"TheoGen_{project.name.replace(' ', '_')}.pdf",
            "expires_at_utc": "1h",
        }

    except Exception as e:
        logger.error("Failed to export report: %s", e)
        raise HTTPException(status_code=500, detail="Failed to generate or upload report")
