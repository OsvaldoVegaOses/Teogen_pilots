from ..services.azure_openai import foundry_openai
from ..core.settings import settings
import json
import logging

logger = logging.getLogger(__name__)

class ModelRouterEngine:
    """Uses Model Router 2025 to select the best model for each task."""

    def __init__(self):
        self.router_deployment = settings.MODEL_ROUTER

    @property
    def client(self):
        return foundry_openai.client

    async def route_and_generate(self, task_type: str, prompt: str, **kwargs):
        """
        Automatically routes to the best available model.
        Uses async client to avoid blocking the event loop.
        """
        if not self.client:
            raise RuntimeError("AI client not initialized")

        try:
            response = await self.client.chat.completions.create(
                model=self.router_deployment,
                messages=[
                    {
                        "role": "system",
                        "content": f"Task type: {task_type}. Select the best model and execute.",
                    },
                    {"role": "user", "content": prompt},
                ],
                **kwargs,
            )

            result_content = response.choices[0].message.content if response.choices else None
            if not result_content:
                raise RuntimeError(f"Model router returned empty choices for task_type='{task_type}'.")

            return {
                "result": result_content,
                "model_used": response.model,
                "usage": response.usage,
            }
        except Exception as e:
            logger.error(f"Model Router error: {e}. Falling back to reasoning_advanced.")
            # Fallback logic
            res = await foundry_openai.reasoning_advanced(
                [{"role": "user", "content": prompt}]
            )
            return {
                "result": res,
                "model_used": settings.MODEL_REASONING_ADVANCED,
                "usage": None,
            }

model_router = ModelRouterEngine()
