from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Dict, Any, Set
from uuid import UUID
from sqlalchemy import select, func
import asyncio
import logging
import time

from ..database import get_db, get_session_local

logger = logging.getLogger(__name__)
from ..schemas.theory import TheoryGenerateRequest, TheoryResponse
from ..engines.theory_engine import theory_engine
from ..models.models import Project, Theory, Code, Category
from ..core.auth import CurrentUser, get_current_user
from ..services.storage_service import storage_service
from ..services.export_service import export_service
from ..services.neo4j_service import neo4j_service
from ..services.qdrant_service import qdrant_service
from ..services.azure_openai import foundry_openai
from ..engines.coding_engine import coding_engine
import uuid
from datetime import datetime

router = APIRouter(prefix="/projects", tags=["Theory"])

# ── In-memory task store (single-replica safe) ──────────────────────────────
# task_id -> {"status": pending|running|completed|failed, "result": ..., "error": ...}
_theory_tasks: Dict[str, Dict[str, Any]] = {}

# Keeps strong references to background tasks so GC does not cancel them.
_background_tasks: Set[asyncio.Task] = set()

# ── Background worker ───────────────────────────────────────────────────────
async def _run_theory_pipeline(task_id: str, project_id: UUID, user_uuid: UUID, request: TheoryGenerateRequest):
    """Run the full theory pipeline in a background asyncio task."""
    wall_start = time.perf_counter()
    logger.info("[theory] task %s STARTED for project %s", task_id, project_id)
    _theory_tasks[task_id]["status"] = "running"
    try:
        session_local = get_session_local()
        async with session_local() as db:
            await _theory_pipeline(task_id, project_id, user_uuid, request, db)
    except Exception as e:
        logger.exception("[theory] task %s CRASHED: %s", task_id, e)
        _theory_tasks[task_id]["status"] = "failed"
        _theory_tasks[task_id]["error"] = str(e)
    finally:
        elapsed = time.perf_counter() - wall_start
        logger.info("[theory] task %s FINISHED status=%s total_elapsed=%.1fs", task_id, _theory_tasks.get(task_id, {}).get("status"), elapsed)


@router.post("/{project_id}/generate-theory", status_code=202)
async def generate_theory(
    project_id: UUID,
    request: TheoryGenerateRequest,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Enqueues the Grounded Theory pipeline and returns a task_id for polling.
    Returns 202 immediately to avoid gateway timeout.
    """
    # 1. Verify project exists and belongs to authenticated user
    project_result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.owner_id == user.user_uuid
        )
    )
    project = project_result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    task_id = str(uuid.uuid4())
    _theory_tasks[task_id] = {"status": "pending", "result": None, "error": None}
    # Store reference to prevent garbage collection before task completes.
    bg_task = asyncio.create_task(_run_theory_pipeline(task_id, project_id, user.user_uuid, request))
    _background_tasks.add(bg_task)
    bg_task.add_done_callback(_background_tasks.discard)
    logger.info("[theory] enqueued task %s for project %s", task_id, project_id)
    return {"task_id": task_id, "status": "pending"}


@router.get("/{project_id}/generate-theory/status/{task_id}")
async def get_theory_task_status(
    project_id: UUID,
    task_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    """Poll the status of a running theory generation task."""
    task = _theory_tasks.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


# ── The actual pipeline logic (reused by background task) ───────────────────
def _t(label: str, task_id: str, t0: float) -> float:
    """Log elapsed time for a step and return new t0."""
    elapsed = time.perf_counter() - t0
    logger.info("[theory][%s] step=%s elapsed=%.2fs", task_id, label, elapsed)
    return time.perf_counter()


async def _theory_pipeline(
    task_id: str,
    project_id: UUID,
    user_uuid: UUID,
    request: TheoryGenerateRequest,
    db: AsyncSession,
):
    pipeline_start = time.perf_counter()
    t0 = pipeline_start
    logger.info("[theory][%s] step=load_project", task_id)
    project_result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.owner_id == user_uuid,
        )
    )
    project = project_result.scalar_one_or_none()
    if not project:
        _theory_tasks[task_id]["status"] = "failed"
        _theory_tasks[task_id]["error"] = "Project not found"
        return
    t0 = _t("load_project", task_id, t0)

    # 2. Collect Data
    logger.info("[theory][%s] step=load_categories", task_id)
    cat_result = await db.execute(select(Category).filter(Category.project_id == project_id))
    categories = cat_result.scalars().all()
    t0 = _t("load_categories", task_id, t0)
    logger.info("[theory][%s] categories_found=%d", task_id, len(categories))

    if len(categories) < 2:
        code_exists_result = await db.execute(
            select(Code.id)
            .where(Code.project_id == project_id)
            .limit(1)
        )

        # Auto-code completed interviews only if there are no codes yet.
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
            logger.info("[theory][%s] step=auto_code interviews_to_code=%d", task_id, len(completed_interviews))
            t_ac = time.perf_counter()
            # Usar sesiones independientes por entrevista con concurrencia limitada a 3
            # (AsyncSession compartida NO es segura para asyncio.gather concurrente)
            _session_local = get_session_local()
            _sem = asyncio.Semaphore(3)

            async def _code_interview(iv_id):
                async with _sem:
                    async with _session_local() as iv_db:
                        await coding_engine.auto_code_interview(project_id, iv_id, iv_db)

            await asyncio.gather(*[_code_interview(iv.id) for iv in completed_interviews])
            logger.info("[theory][%s] step=auto_code DONE interviews=%d elapsed=%.2fs",
                        task_id, len(completed_interviews), time.perf_counter() - t_ac)

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
                        definition="Auto-generada desde códigos durante teorización",
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
            await db.execute(
                select(func.count()).select_from(Interview).where(Interview.project_id == project_id)
            )
        ).scalar() or 0

        interviews_completed = (
            await db.execute(
                select(func.count())
                .select_from(Interview)
                .where(
                    Interview.project_id == project_id,
                    Interview.transcription_status == "completed",
                )
            )
        ).scalar() or 0

        codes_total = (
            await db.execute(
                select(func.count()).select_from(Code).where(Code.project_id == project_id)
            )
        ).scalar() or 0

        _theory_tasks[task_id]["status"] = "failed"
        _theory_tasks[task_id]["error"] = (
            "No hay suficientes categorías para teorización (mínimo 2). "
            f"Estado actual: entrevistas={interviews_total}, entrevistas_completadas={interviews_completed}, "
            f"códigos={codes_total}, categorías={len(categories)}. "
            "Completa transcripción/codificación primero."
        )
        return

    # 3. Ensure graph taxonomy is synced for this project
    t0 = time.perf_counter()
    logger.info("[theory][%s] step=neo4j_sync categories=%d", task_id, len(categories))
    await neo4j_service.ensure_project_node(project_id, project.name)
    # Crear nodos de categoría en paralelo
    await asyncio.gather(
        *[neo4j_service.create_category_node(project_id, cat.id, cat.name) for cat in categories]
    )
    t0 = _t("neo4j_sync_categories", task_id, t0)

    code_result = await db.execute(select(Code).filter(Code.project_id == project_id))
    codes = code_result.scalars().all()
    logger.info("[theory][%s] step=neo4j_link_codes codes=%d", task_id, len(codes))
    # Vincular códigos a categorías en paralelo
    await asyncio.gather(
        *[neo4j_service.link_code_to_category(code.id, code.category_id)
          for code in codes if code.category_id]
    )
    t0 = _t("neo4j_link_codes", task_id, t0)

    # 4. Logic: Central Category -> Paradigm -> Gaps
    try:
        cats_data = [
            {"id": str(c.id), "name": c.name, "description": c.definition or ""}
            for c in categories
        ]

        t0 = time.perf_counter()
        logger.info("[theory][%s] step=network_metrics", task_id)
        try:
            network_metrics = await neo4j_service.get_project_network_metrics(project_id)
        except ValueError as e:
            _theory_tasks[task_id]["status"] = "failed"
            _theory_tasks[task_id]["error"] = str(e)
            return
        t0 = _t("network_metrics", task_id, t0)

        # Build semantic evidence from Qdrant for top central categories.
        category_by_id = {str(c.id): c for c in categories}
        semantic_evidence = []
        t0 = time.perf_counter()
        logger.info("[theory][%s] step=semantic_evidence_build", task_id)
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
            return {"category_id": category_id, "category_name": category_obj.name, "fragments": fragments}

        # Obtener evidencia semántica de las top categorías en paralelo
        evidence_results = await asyncio.gather(
            *[_fetch_evidence(cid, cobj) for cid, cobj in top_categories],
            return_exceptions=False,
        )
        semantic_evidence = [r for r in evidence_results if r is not None]
        t0 = _t("semantic_evidence_build", task_id, t0)

        evidence_by_category = {
            item["category_id"]: item["fragments"] for item in semantic_evidence
        }
        for cat in cats_data:
            cat["semantic_evidence"] = evidence_by_category.get(cat["id"], [])

        # Identify Central Category
        t0 = time.perf_counter()
        logger.info("[theory][%s] step=identify_central_category", task_id)
        central_cat_data = await theory_engine.identify_central_category(
            cats_data, network_metrics
        )
        t0 = _t("identify_central_category", task_id, t0)

        # Build Paradigm
        t0 = time.perf_counter()
        logger.info("[theory][%s] step=build_straussian_paradigm", task_id)
        paradigm = await theory_engine.build_straussian_paradigm(
            central_cat_data["selected_central_category"],
            cats_data,
        )
        t0 = _t("build_straussian_paradigm", task_id, t0)

        # Analyze Gaps
        t0 = time.perf_counter()
        logger.info("[theory][%s] step=analyze_saturation_and_gaps", task_id)
        gaps = await theory_engine.analyze_saturation_and_gaps(paradigm)
        t0 = _t("analyze_saturation_and_gaps", task_id, t0)

        # 5. Save to Database
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

        t0 = time.perf_counter()
        logger.info("[theory][%s] step=save_theory", task_id)
        db.add(new_theory)
        await db.commit()
        await db.refresh(new_theory)
        t0 = _t("save_theory", task_id, t0)

        # Serialize result for the polling endpoint
        _theory_tasks[task_id]["status"] = "completed"
        total_pipeline = time.perf_counter() - pipeline_start
        logger.info("[theory][%s] step=COMPLETED theory_id=%s total_pipeline=%.1fs", task_id, new_theory.id, total_pipeline)
        _theory_tasks[task_id]["result"] = {
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

    except Exception as e:
        await db.rollback()
        _theory_tasks[task_id]["status"] = "failed"
        _theory_tasks[task_id]["error"] = f"Theory generation failed: {str(e)}"

@router.get("/{project_id}/theories", response_model=List[TheoryResponse])
async def list_theories(
    project_id: UUID, 
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # Verify project ownership
    project_result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.owner_id == user.user_uuid
        )
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
    db: AsyncSession = Depends(get_db)
):
    """
    Generates a PDF report for the given theory, uploads it to Azure, 
    and returns a temporary SAS URL for download.
    """
    # 1. Verify project ownership and theory existence
    result = await db.execute(
        select(Theory, Project)
        .join(Project, Theory.project_id == Project.id)
        .where(
            Theory.id == theory_id,
            Theory.project_id == project_id,
            Project.owner_id == user.user_uuid
        )
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Theory or Project not found")
    
    theory, project = row

    # 2. Generate PDF
    try:
        # Prepare data for service
        theory_dict = {
            "version": theory.version,
            "confidence_score": theory.confidence_score,
            "generated_by": theory.generated_by,
            "model_json": theory.model_json,
            "propositions": theory.propositions,
            "gaps": theory.gaps
        }
        
        pdf_buffer = await export_service.generate_theory_pdf(
            project_name=project.name,
            language=project.language or "es",
            theory_data=theory_dict
        )
        
        # 3. Upload to Azure Blob Storage ("exports" container)
        blob_name = f"{project_id}/reports/Theory_{theory_id}_{uuid.uuid4().hex[:8]}.pdf"
        
        await storage_service.upload_blob(
            container_key="exports",
            blob_name=blob_name,
            data=pdf_buffer.getvalue()
        )
        
        # 4. Generate SAS URL (expires in 1 hour)
        download_url = await storage_service.generate_sas_url(
            container_key="exports",
            blob_name=blob_name,
            expires_hours=1
        )
        
        return {
            "download_url": download_url,
            "filename": f"TheoGen_{project.name.replace(' ', '_')}.pdf",
            "expires_at_utc": "1h"
        }

    except Exception as e:
        import logging
        logging.error(f"Failed to export report: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate or upload report")
