from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from uuid import UUID
from sqlalchemy import select, func

from ..database import get_db
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

@router.post("/{project_id}/generate-theory", response_model=TheoryResponse)
async def generate_theory(
    project_id: UUID, 
    request: TheoryGenerateRequest,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Triggers the Grounded Theory generation pipeline.
    Uses multiple Microsoft Foundry models via direct deployment.
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

    # 2. Collect Data
    cat_result = await db.execute(select(Category).filter(Category.project_id == project_id))
    categories = cat_result.scalars().all()

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
            for interview in completed_interviews:
                await coding_engine.auto_code_interview(project_id, interview.id, db)

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

        raise HTTPException(
            status_code=400,
            detail=(
                "No hay suficientes categorías para teorización (mínimo 2). "
                f"Estado actual: entrevistas={interviews_total}, entrevistas_completadas={interviews_completed}, "
                f"códigos={codes_total}, categorías={len(categories)}. "
                "Completa transcripción/codificación primero."
            ),
        )

    # 3. Ensure graph taxonomy is synced for this project
    await neo4j_service.ensure_project_node(project_id, project.name)
    for category in categories:
        await neo4j_service.create_category_node(project_id, category.id, category.name)

    code_result = await db.execute(select(Code).filter(Code.project_id == project_id))
    codes = code_result.scalars().all()
    for code in codes:
        if code.category_id:
            await neo4j_service.link_code_to_category(code.id, code.category_id)

    # 4. Logic: Central Category -> Paradigm -> Gaps
    try:
        cats_data = [
            {"id": str(c.id), "name": c.name, "description": c.definition or ""}
            for c in categories
        ]

        try:
            network_metrics = await neo4j_service.get_project_network_metrics(project_id)
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))

        # Build semantic evidence from Qdrant for top central categories.
        category_by_id = {str(c.id): c for c in categories}
        semantic_evidence = []
        for item in network_metrics.get("category_centrality", [])[:3]:
            category_id = item.get("category_id")
            category_obj = category_by_id.get(category_id)
            if not category_obj:
                continue

            query_text = f"{category_obj.name}. {category_obj.definition or ''}".strip()
            embeddings = await foundry_openai.generate_embeddings([query_text])
            if not embeddings:
                continue

            fragments = await qdrant_service.search_supporting_fragments(
                project_id=project_id,
                query_vector=embeddings[0],
                limit=3,
            )
            semantic_evidence.append({
                "category_id": category_id,
                "category_name": category_obj.name,
                "fragments": fragments,
            })

        evidence_by_category = {
            item["category_id"]: item["fragments"] for item in semantic_evidence
        }
        for cat in cats_data:
            cat["semantic_evidence"] = evidence_by_category.get(cat["id"], [])

        # Identify Central Category
        central_cat_data = await theory_engine.identify_central_category(
            cats_data, network_metrics
        )

        # Build Paradigm
        paradigm = await theory_engine.build_straussian_paradigm(
            central_cat_data["selected_central_category"],
            cats_data,
        )

        # Analyze Gaps
        gaps = await theory_engine.analyze_saturation_and_gaps(paradigm)

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

        db.add(new_theory)
        await db.commit()
        await db.refresh(new_theory)

        return new_theory

    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Theory generation failed: {str(e)}")

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
