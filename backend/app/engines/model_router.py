from ..services.azure_openai import foundry_openai
from ..core.settings import settings
import json
import logging

logger = logging.getLogger(__name__)

class ModelRouterEngine:
    """Uses Model Router 2025 to select the best model for each task."""
    
    def __init__(self):
        self.client = foundry_openai.client
        self.router_deployment = settings.MODEL_ROUTER

    async def route_and_generate(self, task_type: str, prompt: str, **kwargs):
        """
        Automatically routes to:
        - GPT-5.2 (deep reasoning)
        - Claude 3.5 Sonnet (qualitative analysis)
        - o3-mini (speed/validation)
        """
        if not self.client:
            raise Exception("AI client not initialized")
            
        try:
            # Note: In practice, the router is often a specialized deployment 
            # or a logic layer in the backend.
            response = self.client.chat.completions.create(
                model=self.router_deployment,
                messages=[
                    {
                        "role": "system", 
                        "content": f"Task type: {task_type}. Select the best model (GPT-5.2, Claude 3.5, or o3-mini) and execute."
                    },
                    {"role": "user", "content": prompt}
                ],
                **kwargs
            )
            
            return {
                "result": response.choices[0].message.content,
                "model_used": response.model,
                "usage": response.usage
            }
        except Exception as e:
            logger.error(f"Model Router error: {e}. Falling back to reasoning_advanced.")
            # Fallback logic
            res = await foundry_openai.reasoning_advanced([{"role": "user", "content": prompt}])
            return {
                "result": res,
                "model_used": settings.MODEL_REASONING_ADVANCED,
                "usage": None
            }

model_router = ModelRouterEngine()
