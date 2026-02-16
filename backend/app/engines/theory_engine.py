# backend/app/engines/theory_engine.py
from ..services.azure_openai import foundry_openai
from ..engines.model_router import model_router
from ..prompts import (
    CENTRAL_CATEGORY_SYSTEM_PROMPT, 
    get_central_category_user_prompt,
    STRAUSSIAN_MODEL_SYSTEM_PROMPT,
    get_straussian_build_prompt,
    GAP_ANALYSIS_SYSTEM_PROMPT
)
import json
import logging

logger = logging.getLogger(__name__)

class TheoryGenerationEngine:
    """The 'Brain' of TheoGen - Orchestrates the qualitative theory pipeline."""
    
    def __init__(self):
        self.ai = foundry_openai
        self.router = model_router

    async def identify_central_category(self, categories: list, network: dict) -> dict:
        """Uses GPT-5.2 to find the axle of the theory."""
        logger.info("Identifying central category using GPT-5.2...")
        
        # Use gpt-5.2-chat (MODEL_REASONING_ADVANCED)
        response = await self.ai.reasoning_advanced(
            messages=[
                {"role": "system", "content": CENTRAL_CATEGORY_SYSTEM_PROMPT},
                {"role": "user", "content": get_central_category_user_prompt(categories, network)}
            ],
            response_format={"type": "json_object"}
        )
        return json.loads(response)

    async def build_straussian_paradigm(self, central_cat: str, other_cats: list) -> dict:
        """Uses Claude 3.5 Sonnet via Model Router to build the structural model."""
        logger.info("Building Straussian Paradigm...")
        
        # We can route this to Claude or GPT-5.2 depending on router logic
        route_result = await self.router.route_and_generate(
            task_type="qualitative_modeling",
            prompt=get_straussian_build_prompt(central_cat, other_cats),
            system_prompt=STRAUSSIAN_MODEL_SYSTEM_PROMPT,
            response_format={"type": "json_object"}
        )
        return json.loads(route_result["result"])

    async def analyze_saturation_and_gaps(self, theory_data: dict) -> dict:
        """Uses o3-mini (MODEL_REASONING_FAST) for logical gap analysis."""
        logger.info("Analyzing saturation GAPs with o3-mini...")
        
        response = await self.ai.reasoning_fast(
            messages=[
                {"role": "system", "content": GAP_ANALYSIS_SYSTEM_PROMPT},
                {"role": "user", "content": f"Theory Current Data: {theory_data}"}
            ],
            response_format={"type": "json_object"}
        )
        return json.loads(response)

theory_engine = TheoryGenerationEngine()
