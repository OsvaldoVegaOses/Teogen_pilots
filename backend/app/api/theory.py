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

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import MultipleResultsFound
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import CurrentUser, get_current_user
from ..core.settings import settings
from ..database import get_db, get_session_local
from ..engines.theory_pipeline import TheoryPipeline, TheoryPipelineError
from ..models.models import Project, Theory
from ..schemas.theory import (
    TheoryGenerateRequest,
    TheoryResponse,
    TheoryClaimsExplainResponse,
    TheoryJudgeRolloutResponse,
    TheoryPipelineSloResponse,
)
from ..services.export_service import export_service
from ..services.neo4j_service import neo4j_service
from ..services.storage_service import storage_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects", tags=["Theory"])

_TASK_TTL = 86400
_TASK_PREFIX = "theory_task:"
_LOCK_PREFIX = "theory_lock:"
_redis_client = None
_theory_tasks: Dict[str, Dict[str, Any]] = {}
_background_tasks: Set[asyncio.Task] = set()
_background_tasks_by_id: Dict[str, asyncio.Task] = {}
_local_pipeline_semaphore = asyncio.Semaphore(max(1, settings.THEORY_LOCAL_MAX_CONCURRENT_TASKS))
theory_pipeline = TheoryPipeline()


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


async def _mark_step(task_id: str, step: str, progress: int) -> None:
    await _set_task_state(task_id, step=step, progress=progress)


async def _run_theory_pipeline(task_id: str, project_id: UUID, user_uuid: UUID, request: TheoryGenerateRequest):
    wall_start = time.perf_counter()
    logger.info("[theory] task %s STARTED for project %s", task_id, project_id)
    await _set_task_state(task_id, status_value="running", step="pipeline_start", progress=2)
    try:
        async with _local_pipeline_semaphore:
            session_local = get_session_local()
            async with session_local() as db:
                await _theory_pipeline(task_id, project_id, user_uuid, request, db)
    except asyncio.CancelledError:
        # Best-effort: mark canceled. If cancellation happens during an uninterruptible I/O,
        # this might be delayed until the next await completes.
        logger.warning("[theory] task %s CANCELLED by user", task_id)
        await _set_task_state(
            task_id,
            status_value="failed",
            step="canceled",
            progress=100,
            error="Canceled by user",
            error_code="CANCELED",
        )
        raise
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
            _background_tasks_by_id[task_id] = bg_task
            bg_task.add_done_callback(_background_tasks.discard)
            bg_task.add_done_callback(lambda _t: _background_tasks_by_id.pop(task_id, None))
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


@router.post("/{project_id}/generate-theory/cancel/{task_id}")
async def cancel_theory_task(
    project_id: UUID,
    task_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    task = _theory_tasks.get(task_id) or await _restore_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.get("project_id") != str(project_id) or task.get("owner_id") != str(user.user_uuid):
        raise HTTPException(status_code=404, detail="Task not found")

    if task.get("status") in ("completed", "failed"):
        return task

    # Local-mode: cancel coroutine if still tracked.
    bg = _background_tasks_by_id.get(task_id)
    if bg and not bg.done():
        bg.cancel()

    # Celery-mode: best-effort revoke (does not guarantee termination of a running task).
    worker_task_id = task.get("worker_task_id")
    if worker_task_id:
        try:
            from ..tasks.celery_app import celery_app

            celery_app.control.revoke(worker_task_id, terminate=False)
        except Exception:
            pass

    await _set_task_state(
        task_id,
        status_value="failed",
        step="canceled",
        progress=100,
        error="Canceled by user",
        error_code="CANCELED",
    )
    await _release_project_lock(project_id, task_id)
    return _theory_tasks.get(task_id) or task


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
    started = time.perf_counter()
    try:
        result_payload = await theory_pipeline.run(
            task_id=task_id,
            project_id=project_id,
            user_uuid=user_uuid,
            request=request,
            db=db,
            mark_step=lambda step, progress: _mark_step(task_id, step, progress),
            refresh_lock=lambda: _refresh_project_lock(project_id, task_id),
        )
        await _set_task_state(
            task_id,
            status_value="completed",
            step="completed",
            progress=100,
            result=result_payload,
        )
        await _refresh_project_lock(project_id, task_id)
        logger.info("[theory][%s] completed in %.1fs", task_id, time.perf_counter() - started)
    except TheoryPipelineError as e:
        await db.rollback()
        await _set_task_state(
            task_id,
            status_value="failed",
            step="failed",
            progress=100,
            error=e.message,
            error_code=e.code,
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

    result = await db.execute(
        select(Theory)
        .filter(Theory.project_id == project_id)
        .order_by(Theory.created_at.desc())
    )
    return result.scalars().all()


@router.get(
    "/{project_id}/theories/judge-rollout",
    response_model=TheoryJudgeRolloutResponse,
)
async def get_theory_judge_rollout(
    project_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project_result = await db.execute(
        select(Project).where(Project.id == project_id, Project.owner_id == user.user_uuid)
    )
    if not project_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Project not found")

    policy = await theory_pipeline.get_judge_rollout_policy(project_id=project_id, db=db)

    latest_theory = (
        await db.execute(
            select(Theory)
            .where(Theory.project_id == project_id)
            .order_by(Theory.created_at.desc())
            .limit(1)
        )
    ).scalars().first()

    latest_validation: Dict[str, Any] = {}
    latest_theory_id: Optional[UUID] = None
    latest_created_at: Optional[datetime] = None
    if latest_theory:
        latest_theory_id = latest_theory.id
        latest_created_at = latest_theory.created_at
        validation = latest_theory.validation or {}
        if isinstance(validation, dict):
            latest_validation = {
                "judge": validation.get("judge", {}),
                "judge_rollout": validation.get("judge_rollout", {}),
                "claim_metrics": validation.get("claim_metrics", {}),
                "quality_metrics": validation.get("quality_metrics", {}),
                "neo4j_claim_sync": validation.get("neo4j_claim_sync", {}),
                "qdrant_claim_sync": validation.get("qdrant_claim_sync", {}),
            }

    return {
        "project_id": project_id,
        "policy": policy,
        "latest_theory_id": latest_theory_id,
        "latest_created_at": latest_created_at,
        "latest_validation": latest_validation,
    }


def _percentile(values: List[float], q: float) -> float:
    clean = sorted(float(v) for v in values if v is not None)
    if not clean:
        return 0.0
    if len(clean) == 1:
        return round(clean[0], 2)
    q = max(0.0, min(100.0, float(q)))
    rank = int(round((q / 100.0) * (len(clean) - 1)))
    return round(clean[rank], 2)


@router.get(
    "/{project_id}/theories/pipeline-slo",
    response_model=TheoryPipelineSloResponse,
)
async def get_theory_pipeline_slo(
    project_id: UUID,
    window: int = Query(20, ge=5, le=200),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project_result = await db.execute(
        select(Project).where(Project.id == project_id, Project.owner_id == user.user_uuid)
    )
    if not project_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Project not found")

    rows = (
        await db.execute(
            select(Theory.id, Theory.created_at, Theory.validation)
            .where(Theory.project_id == project_id)
            .order_by(Theory.created_at.desc())
            .limit(window)
        )
    ).all()

    if not rows:
        return {
            "project_id": project_id,
            "window_size": int(window),
            "sample_size": 0,
            "latest_theory_id": None,
            "latest_created_at": None,
            "latency_p95_ms": {},
            "latency_p50_ms": {},
            "quality": {},
            "reliability": {},
        }

    latency_keys = [
        "category_summary_sync_ms",
        "neo4j_metrics_ms",
        "qdrant_retrieval_ms",
        "identify_llm_ms",
        "paradigm_llm_ms",
        "gaps_llm_ms",
    ]
    latency_values: Dict[str, List[float]] = {k: [] for k in latency_keys}

    warn_only_runs = 0
    fallback_network = 0
    fallback_evidence = 0
    neo4j_claim_sync_failed = 0
    qdrant_claim_sync_failed = 0
    claims_without_evidence_total = 0

    for _theory_id, _created_at, validation in rows:
        if not isinstance(validation, dict):
            continue
        runtime = validation.get("pipeline_runtime") or {}
        latency = runtime.get("latency_ms") or {}
        for key in latency_keys:
            value = latency.get(key)
            if isinstance(value, (int, float)):
                latency_values[key].append(float(value))

        judge = validation.get("judge") or {}
        if bool(judge.get("warn_only")):
            warn_only_runs += 1

        routing = validation.get("deterministic_routing") or {}
        execution = routing.get("execution") or {}
        if str(execution.get("network_metrics_source") or "").strip().lower() == "sql_fallback":
            fallback_network += 1
        if str(execution.get("semantic_evidence_source") or "").strip().lower() == "sql_fallback":
            fallback_evidence += 1

        neo4j_claim_sync = validation.get("neo4j_claim_sync") or {}
        if bool(neo4j_claim_sync.get("neo4j_sync_failed")):
            neo4j_claim_sync_failed += 1
        qdrant_claim_sync = validation.get("qdrant_claim_sync") or {}
        if bool(qdrant_claim_sync.get("qdrant_sync_failed")):
            qdrant_claim_sync_failed += 1

        claim_metrics = validation.get("claim_metrics") or {}
        claims_without_evidence_total += int(claim_metrics.get("claims_without_evidence") or 0)

    sample_size = len(rows)
    latency_p95 = {k: _percentile(v, 95) for k, v in latency_values.items() if v}
    latency_p50 = {k: _percentile(v, 50) for k, v in latency_values.items() if v}

    latest_theory_id, latest_created_at, _ = rows[0]

    return {
        "project_id": project_id,
        "window_size": int(window),
        "sample_size": sample_size,
        "latest_theory_id": latest_theory_id,
        "latest_created_at": latest_created_at,
        "latency_p95_ms": latency_p95,
        "latency_p50_ms": latency_p50,
        "quality": {
            "claims_without_evidence_total": int(claims_without_evidence_total),
            "claims_without_evidence_rate": round(claims_without_evidence_total / max(1, sample_size), 3),
            "judge_warn_only_runs": int(warn_only_runs),
            "judge_warn_only_rate": round(warn_only_runs / max(1, sample_size), 3),
        },
        "reliability": {
            "network_sql_fallback_runs": int(fallback_network),
            "evidence_sql_fallback_runs": int(fallback_evidence),
            "network_sql_fallback_rate": round(fallback_network / max(1, sample_size), 3),
            "evidence_sql_fallback_rate": round(fallback_evidence / max(1, sample_size), 3),
            "neo4j_claim_sync_failed_runs": int(neo4j_claim_sync_failed),
            "qdrant_claim_sync_failed_runs": int(qdrant_claim_sync_failed),
        },
    }


def _build_claims_from_validation_fallback(theory: Theory) -> List[Dict[str, Any]]:
    model_json = theory.model_json or {}
    validation = theory.validation or {}
    evidence_index = (
        validation.get("network_metrics_summary", {}).get("evidence_index", [])
        if isinstance(validation, dict)
        else []
    )
    evidence_map = {}
    for ev in evidence_index or []:
        if not isinstance(ev, dict):
            continue
        fid = str(ev.get("fragment_id") or ev.get("id") or "").strip()
        if not fid:
            continue
        evidence_map[fid] = {
            "fragment_id": fid,
            "score": ev.get("score"),
            "rank": None,
            "text": ev.get("text"),
            "interview_id": ev.get("interview_id"),
        }

    section_to_type = {
        "conditions": "condition",
        "context": "condition",
        "intervening_conditions": "condition",
        "actions": "action",
        "consequences": "consequence",
        "propositions": "proposition",
    }
    items: List[Dict[str, Any]] = []
    for section, claim_type in section_to_type.items():
        raw = model_json.get(section) or []
        if not isinstance(raw, list):
            continue
        for idx, entry in enumerate(raw):
            if not isinstance(entry, dict):
                continue
            text = str(entry.get("text") or entry.get("name") or "").strip()
            if not text:
                continue
            evidence = []
            for rank, fid in enumerate(entry.get("evidence_ids") or []):
                fragment_id = str(fid).strip()
                if not fragment_id:
                    continue
                base = evidence_map.get(
                    fragment_id,
                    {
                        "fragment_id": fragment_id,
                        "score": None,
                        "rank": None,
                        "text": None,
                        "interview_id": None,
                    },
                )
                evidence.append({**base, "rank": rank})

            category_name = str(entry.get("name") or "").strip()
            categories = [{"id": None, "name": category_name}] if category_name and section != "propositions" else []
            path_examples = []
            for ev in evidence[:3]:
                fragment_id = ev.get("fragment_id")
                if categories:
                    path_examples.append(f"{categories[0].get('name')} -> {text} -> {fragment_id}")
                else:
                    path_examples.append(f"{text} -> {fragment_id}")

            items.append(
                {
                    "claim_id": f"fallback:{theory.id}:{section}:{idx}",
                    "claim_type": claim_type,
                    "section": section,
                    "order": idx,
                    "text": text,
                    "categories": categories,
                    "evidence": evidence,
                    "path_examples": path_examples,
                }
            )
    return items


@router.get(
    "/{project_id}/theories/{theory_id}/claims/explain",
    response_model=TheoryClaimsExplainResponse,
)
async def explain_theory_claims(
    project_id: UUID,
    theory_id: UUID,
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0, le=5000),
    section: Optional[str] = Query(None, pattern="^(conditions|context|intervening_conditions|actions|consequences|propositions)$"),
    claim_type: Optional[str] = Query(None, pattern="^(condition|action|consequence|proposition|gap)$"),
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
    theory, _project = row

    source = "validation_fallback"
    all_claims = _build_claims_from_validation_fallback(theory)
    if section:
        all_claims = [claim for claim in all_claims if str(claim.get("section") or "") == section]
    if claim_type:
        all_claims = [claim for claim in all_claims if str(claim.get("claim_type") or "") == claim_type]
    total = len(all_claims)
    claims = all_claims[offset : offset + limit]

    try:
        neo_claims = await neo4j_service.get_theory_claims_explain(
            project_id=project_id,
            theory_id=theory_id,
            owner_id=user.user_uuid,
            limit=limit,
            offset=offset,
            section=section,
            claim_type=claim_type,
        )
    except Exception as e:
        logger.warning(
            "Neo4j explain failed project_id=%s theory_id=%s: %s",
            project_id,
            theory_id,
            str(e)[:300],
        )
        neo_claims = {"total": 0, "claims": []}

    if isinstance(neo_claims, dict):
        neo_claims_rows = neo_claims.get("claims") or []
        neo_total = int(neo_claims.get("total") or 0)
    else:
        neo_claims_rows = neo_claims or []
        neo_total = len(neo_claims_rows)

    if neo_claims_rows:
        source = "neo4j"
        total = neo_total
        claims = []
        for claim in neo_claims_rows:
            categories = [
                {"id": str(cat.get("id") or ""), "name": str(cat.get("name") or "")}
                for cat in (claim.get("categories") or [])
                if isinstance(cat, dict)
            ]
            evidence = [
                {
                    "fragment_id": str(ev.get("fragment_id") or ""),
                    "score": ev.get("score"),
                    "rank": ev.get("rank"),
                    "text": ev.get("text"),
                    "interview_id": None,
                }
                for ev in (claim.get("evidence") or [])
                if isinstance(ev, dict) and str(ev.get("fragment_id") or "").strip()
            ]
            path_examples = []
            for ev in evidence[:3]:
                if categories:
                    path_examples.append(
                        f"{categories[0].get('name') or 'Category'} -> {claim.get('text') or ''} -> {ev.get('fragment_id')}"
                    )
                else:
                    path_examples.append(f"{claim.get('text') or ''} -> {ev.get('fragment_id')}")

            claims.append(
                {
                    "claim_id": str(claim.get("claim_id") or ""),
                    "claim_type": str(claim.get("claim_type") or ""),
                    "section": str(claim.get("section") or ""),
                    "order": int(claim.get("order") or 0),
                    "text": str(claim.get("text") or ""),
                    "categories": categories,
                    "evidence": evidence,
                    "path_examples": path_examples,
                }
            )

    return {
        "project_id": project_id,
        "theory_id": theory_id,
        "source": source,
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": (offset + len(claims)) < total,
        "section_filter": section,
        "claim_type_filter": claim_type,
        "claim_count": len(claims),
        "claims": claims,
    }


@router.post("/{project_id}/theories/{theory_id}/export")
async def export_theory_report(
    project_id: UUID,
    theory_id: UUID,
    format: str = Query("pdf", pattern="^(pdf|pptx|xlsx|png)$"),
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
            "validation": theory.validation,
        }

        report_buffer, extension, content_type = await export_service.generate_theory_report(
            project_name=project.name,
            language=project.language or "es",
            theory_data=theory_dict,
            format=format,
            template_key=getattr(project, "domain_template", "generic") or "generic",
        )

        blob_name = f"{project_id}/reports/Theory_{theory_id}_{uuid.uuid4().hex[:8]}.{extension}"

        await storage_service.upload_blob(
            container_key="exports",
            blob_name=blob_name,
            data=report_buffer.getvalue(),
            content_type=content_type,
        )

        download_url = await storage_service.generate_sas_url(
            container_key="exports",
            blob_name=blob_name,
            expires_hours=1,
        )

        return {
            "download_url": download_url,
            "filename": f"TheoGen_{project.name.replace(' ', '_')}.{extension}",
            "expires_at_utc": "1h",
            "format": extension,
        }

    except Exception:
        logger.exception(
            "Failed to export report project_id=%s theory_id=%s format=%s",
            project_id,
            theory_id,
            format,
        )
        raise HTTPException(status_code=500, detail="Failed to generate or upload report")
