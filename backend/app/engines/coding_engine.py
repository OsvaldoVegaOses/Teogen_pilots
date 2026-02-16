# backend/app/engines/coding_engine.py
from ..services.azure_openai import foundry_openai
from ..prompts.axial_coding import AXIAL_CODING_SYSTEM_PROMPT, get_coding_user_prompt
import json
import logging
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from ..models.models import Fragment, Code, Project
from sqlalchemy import select

logger = logging.getLogger(__name__)

class CodingEngine:
    """Engine responsible for Open and Axial coding of fragments."""
    
    def __init__(self):
        self.ai = foundry_openai

    async def process_fragment(self, project_id: UUID, fragment_text: str, db: AsyncSession) -> dict:
        """
        Takes a fragment text and generates suggested codes and axial relationships.
        """
        # 1. Get existing codes for context
        code_result = await db.execute(select(Code).filter(Code.project_id == project_id))
        existing_codes = [{"label": c.label, "definition": c.definition} for c in code_result.scalars().all()]

        # 2. Call AI (Using Claude 3.5 Sonnet as default for high qualitative sensitivity)
        logger.info(f"Coding fragment: {fragment_text[:50]}...")
        
        response = await self.ai.claude_analysis(
            messages=[
                {"role": "system", "content": AXIAL_CODING_SYSTEM_PROMPT},
                {"role": "user", "content": get_coding_user_prompt(fragment_text, existing_codes)}
            ],
            response_format={"type": "json_object"}
        )

        return json.loads(response)

    async def auto_code_interview(self, project_id: UUID, interview_id: UUID, db: AsyncSession):
        """
        Iterates through all fragments of an interview and codes them.
        """
        frag_result = await db.execute(select(Fragment).filter(Fragment.interview_id == interview_id))
        fragments = frag_result.scalars().all()

        for fragment in fragments:
            coding_results = await self.process_fragment(project_id, fragment.text, db)
            
            # Save new codes to DB
            for code_data in coding_results.get("extracted_codes", []):
                # Simple logic for now: check if code exists, if not, create
                # In production, we would use vector similarity to merge codes
                existing_check = await db.execute(select(Code).filter(Code.label == code_data["label"], Code.project_id == project_id))
                if not existing_check.scalar_one_or_none():
                    new_code = Code(
                        project_id=project_id,
                        label=code_data["label"],
                        definition=code_data["definition"],
                        created_by="ai"
                    )
                    db.add(new_code)
            
            await db.commit()

coding_engine = CodingEngine()
