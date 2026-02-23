from ..services.azure_openai import foundry_openai
from ..core.settings import settings
import logging

logger = logging.getLogger(__name__)

class ModelRouterEngine:
    """Uses Model Router 2025 to select the best model for each task."""

    def __init__(self):
        self.router_deployment = settings.MODEL_ROUTER

    @property
    def client(self):
        return foundry_openai.client

    async def route_and_generate(self, task_type: str, prompt: str, system_prompt: str = None, **kwargs):
        """
        Automatically routes to the best available model.
        system_prompt is injected into the messages array (NOT passed as kwarg to completions.create).
        response_format is stripped from kwargs — model-router may route to models that don't support it.
        """
        if not self.client:
            raise RuntimeError("AI client not initialized")

        # Strip unsupported params before forwarding to completions.create
        kwargs.pop("response_format", None)

        system_content = f"Task type: {task_type}. Select the best model and execute."
        if system_prompt:
            system_content = f"{system_content}\n\n{system_prompt}"

        try:
            response = await self.client.chat.completions.create(
                model=self.router_deployment,
                messages=[
                    {"role": "system", "content": system_content},
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
            # Fallback to Kimi-K2.5 (NOT DeepSeek — avoids cascading same failure)
            logger.warning(f"Model Router error: {e}. Falling back to Kimi-K2.5.")
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            res = await foundry_openai.kimi_reasoning(messages)
            return {
                "result": res,
                "model_used": settings.MODEL_KIMI,
                "usage": None,
            }

model_router = ModelRouterEngine()
