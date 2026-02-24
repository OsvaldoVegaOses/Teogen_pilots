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
from ..schemas.theory import TheoryGenerateRequest, TheoryResponse
from ..services.export_service import export_service
from ..services.storage_service import storage_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects", tags=["Theory"])

_TASK_TTL = 86400
_TASK_PREFIX = "theory_task:"
_LOCK_PREFIX = "theory_lock:"
_redis_client = None
_theory_tasks: Dict[str, Dict[str, Any]] = {}
_background_tasks: Set[asyncio.Task] = set()
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

    result = await db.execute(select(Theory).filter(Theory.project_id == project_id))
    return result.scalars().all()


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

    except Exception as e:
        logger.error("Failed to export report: %s", e)
        raise HTTPException(status_code=500, detail="Failed to generate or upload report")

