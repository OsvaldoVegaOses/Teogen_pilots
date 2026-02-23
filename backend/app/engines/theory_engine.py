# backend/app/engines/theory_engine.py
from ..services.azure_openai import foundry_openai
from ..engines.model_router import model_router
from ..core.json_utils import safe_json_loads
from ..prompts import (
    CENTRAL_CATEGORY_SYSTEM_PROMPT, 
    get_central_category_user_prompt,
    STRAUSSIAN_MODEL_SYSTEM_PROMPT,
    get_straussian_build_prompt,
    GAP_ANALYSIS_SYSTEM_PROMPT
)
import logging

logger = logging.getLogger(__name__)

class TheoryGenerationEngine:
    """The 'Brain' of TheoGen - Orchestrates the qualitative theory pipeline."""
    
    def __init__(self):
        self.ai = foundry_openai
        self.router = model_router

    async def identify_central_category(self, categories: list, network: dict) -> dict:
        """Uses DeepSeek-V3 to find the axle of the theory."""
        logger.info("Identifying central category...")
        required_network_keys = {"counts", "category_centrality", "category_cooccurrence"}
        missing = required_network_keys - set(network.keys())
        if missing:
            raise ValueError(f"Network payload missing required keys: {', '.join(sorted(missing))}")

        # NOTE: response_format=json_object NOT sent — DeepSeek-V3 in Azure Foundry
        # returns empty choices when JSON mode is requested but not supported.
        # safe_json_loads extracts JSON from free-text response.
        response = await self.ai.reasoning_advanced(
            messages=[
                {"role": "system", "content": CENTRAL_CATEGORY_SYSTEM_PROMPT},
                {"role": "user", "content": get_central_category_user_prompt(categories, network)}
            ]
        )
        return safe_json_loads(response)

    async def build_straussian_paradigm(self, central_cat: str, other_cats: list) -> dict:
        """Uses Model Router to build the structural model."""
        logger.info("Building Straussian Paradigm...")

        # system_prompt passed as named param (NOT as kwarg to completions.create)
        # response_format omitted — model-router may route to models that don't support JSON mode
        route_result = await self.router.route_and_generate(
            task_type="qualitative_modeling",
            prompt=get_straussian_build_prompt(central_cat, other_cats),
            system_prompt=STRAUSSIAN_MODEL_SYSTEM_PROMPT,
        )
        return safe_json_loads(route_result["result"])

    async def analyze_saturation_and_gaps(self, theory_data: dict) -> dict:
        """Uses DeepSeek-V3 (MODEL_REASONING_FAST) for logical gap analysis."""
        logger.info("Analyzing saturation GAPs...")

        # response_format omitted — DeepSeek doesn't support JSON mode in Azure Foundry
        response = await self.ai.reasoning_fast(
            messages=[
                {"role": "system", "content": GAP_ANALYSIS_SYSTEM_PROMPT},
                {"role": "user", "content": f"Theory Current Data: {theory_data}"}
            ]
        )
        return safe_json_loads(response)

theory_engine = TheoryGenerationEngine()
