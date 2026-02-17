# backend/app/engines/coding_engine.py
from ..services.azure_openai import foundry_openai
from ..prompts.axial_coding import AXIAL_CODING_SYSTEM_PROMPT, get_coding_user_prompt
import json
import logging
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from ..models.models import Fragment, Code, Project, code_fragment_links
from sqlalchemy import select, insert

logger = logging.getLogger(__name__)

class CodingEngine:
    """Engine responsible for Open and Axial coding of fragments."""

    def __init__(self):
        self.ai = foundry_openai

    async def process_fragment(self, project_id: UUID, fragment_id: UUID, fragment_text: str, db: AsyncSession) -> dict:
        """
        Takes a fragment text and generates suggested codes and axial relationships.
        Now also links codes to the source fragment via code_fragment_links.
        """
        # 1. Get existing codes for context
        code_result = await db.execute(select(Code).filter(Code.project_id == project_id))
        existing_codes = [
            {"label": c.label, "definition": c.definition}
            for c in code_result.scalars().all()
        ]

        # 2. Call AI
        logger.info(f"Coding fragment: {fragment_text[:50]}...")

        response = await self.ai.claude_analysis(
            messages=[
                {"role": "system", "content": AXIAL_CODING_SYSTEM_PROMPT},
                {"role": "user", "content": get_coding_user_prompt(fragment_text, existing_codes)},
            ],
            response_format={"type": "json_object"},
        )

        coding_results = json.loads(response)

        # 3. Save codes and create links to the fragment
        for code_data in coding_results.get("extracted_codes", []):
            # Check if code already exists
            existing_check = await db.execute(
                select(Code).filter(
                    Code.label == code_data["label"],
                    Code.project_id == project_id,
                )
            )
            existing_code = existing_check.scalar_one_or_none()

            if existing_code:
                code_id = existing_code.id
            else:
                new_code = Code(
                    project_id=project_id,
                    label=code_data["label"],
                    definition=code_data.get("definition", ""),
                    created_by="ai",
                )
                db.add(new_code)
                await db.flush()  # Get the ID without committing
                code_id = new_code.id

            # ← FIXED: Create the Code↔Fragment link
            # Check if link already exists
            existing_link = await db.execute(
                select(code_fragment_links).filter(
                    code_fragment_links.c.code_id == code_id,
                    code_fragment_links.c.fragment_id == fragment_id,
                )
            )
            if not existing_link.first():
                await db.execute(
                    insert(code_fragment_links).values(
                        code_id=code_id,
                        fragment_id=fragment_id,
                        confidence=1.0,
                    )
                )

        return coding_results

    async def auto_code_interview(self, project_id: UUID, interview_id: UUID, db: AsyncSession):
        """
        Iterates through all fragments of an interview and codes them.
        """
        frag_result = await db.execute(
            select(Fragment).filter(Fragment.interview_id == interview_id)
        )
        fragments = frag_result.scalars().all()

        for fragment in fragments:
            # ← FIXED: Pass fragment.id so we can create the link
            await self.process_fragment(project_id, fragment.id, fragment.text, db)

        await db.commit()

coding_engine = CodingEngine()
