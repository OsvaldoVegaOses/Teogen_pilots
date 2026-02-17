from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from uuid import UUID

from ..database import get_db
from ..schemas.theory import TheoryGenerateRequest, TheoryResponse
from ..engines.theory_engine import theory_engine
from ..models.models import Project, Theory, Code, Category
from sqlalchemy import select

router = APIRouter(prefix="/projects", tags=["Theory"])

@router.post("/{project_id}/generate-theory", response_model=TheoryResponse)
async def generate_theory(
    project_id: UUID,
    request: TheoryGenerateRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Triggers the Grounded Theory generation pipeline.
    Uses multiple Microsoft Foundry models via direct deployment.
    """
    # 1. Verify project exists
    project_result = await db.execute(select(Project).filter(Project.id == project_id))
    project = project_result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # 2. Collect Data
    cat_result = await db.execute(select(Category).filter(Category.project_id == project_id))
    categories = cat_result.scalars().all()

    code_result = await db.execute(select(Code).filter(Code.project_id == project_id))
    codes = code_result.scalars().all()

    if len(categories) < 2:
        raise HTTPException(
            status_code=400,
            detail="Not enough categories to generate a theory (min 2)",
        )

    # 3. Logic: Central Category -> Paradigm -> Gaps
    try:
        # ← FIXED: c.description → c.definition (ORM Category uses 'definition')
        cats_data = [
            {"id": str(c.id), "name": c.name, "description": c.definition or ""}
            for c in categories
        ]

        # Identify Central Category
        central_cat_data = await theory_engine.identify_central_category(
            cats_data, {"network": "placeholder"}
        )

        # Build Paradigm
        paradigm = await theory_engine.build_straussian_paradigm(
            central_cat_data["selected_central_category"],
            cats_data,
        )

        # Analyze Gaps
        gaps = await theory_engine.analyze_saturation_and_gaps(paradigm)

        # 4. Save to Database
        # ← FIXED: model=paradigm → model_json=paradigm (ORM column name)
        # ← FIXED: generated_by now exists in ORM
        new_theory = Theory(
            project_id=project_id,
            model_json=paradigm,
            propositions=paradigm.get("propositions", []),
            validation={"gap_analysis": gaps},
            gaps=gaps.get("identified_gaps", []),
            confidence_score=paradigm.get("confidence_score", 0.7),
            generated_by="DeepSeek-V3.2-Speciale/Kimi-K2.5",
            status="completed",
        )

        db.add(new_theory)
        await db.commit()
        await db.refresh(new_theory)

        return new_theory

    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Theory generation failed: {str(e)}")

@router.get("/{project_id}/theories", response_model=List[TheoryResponse])
async def list_theories(project_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Theory).filter(Theory.project_id == project_id))
    return result.scalars().all()
