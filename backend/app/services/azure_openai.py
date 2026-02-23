from openai import AsyncAzureOpenAI
from ..core.settings import settings
import logging

logger = logging.getLogger(__name__)

# Models that only support temperature=1 (o-series / reasoning).
# Temperature param is skipped for these; the API uses its default (1).
# Unknown reasoning models are auto-detected from 400 'unsupported_value' errors at runtime.
_NO_TEMPERATURE_MODELS: set[str] = {
    "gpt-5.2-chat",
    "o1", "o1-mini", "o1-preview",
    "o3", "o3-mini",
    "o4-mini",
}


class FoundryOpenAIService:
    """Updated service for Microsoft Foundry & Azure OpenAI API v1 (2025).
    
    Uses async SDK clients to avoid blocking the event loop.
    No local/mock fallback — requires valid Azure credentials.
    """

    def __init__(self):
        self._azure_client = None

    def _ensure_clients(self):
        if self._azure_client:
            return

        if not settings.AZURE_OPENAI_API_KEY or not settings.AZURE_OPENAI_ENDPOINT:
            raise RuntimeError(
                "AZURE_OPENAI_API_KEY and AZURE_OPENAI_ENDPOINT are required. "
                "TheoGen does not support local/mock AI mode."
            )

        self._azure_client = AsyncAzureOpenAI(
            api_key=settings.AZURE_OPENAI_API_KEY,
            api_version=settings.AZURE_OPENAI_API_VERSION,
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
        )

    @property
    def client(self):
        self._ensure_clients()
        # Use AsyncAzureOpenAI — routes to /openai/deployments/{model}/
        # which matches the portal URI for all AIServices deployments.
        # AsyncOpenAI with /openai/v1/ caused empty choices on DeepSeek.
        return self._azure_client

    @property
    def azure_client(self):
        self._ensure_clients()
        return self._azure_client

    async def generate_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Generates embeddings using text-embedding-3-large."""
        response = await self.azure_client.embeddings.create(
            model=settings.MODEL_EMBEDDING,
            input=texts,
        )
        return [item.embedding for item in response.data]

    async def reasoning_advanced(self, messages: list, **kwargs):
        """Deep reasoning using DeepSeek-V3.2-Speciale."""
        return await self._chat_call(settings.MODEL_REASONING_ADVANCED, messages, **kwargs)

    async def kimi_reasoning(self, messages: list, **kwargs):
        """Reasoning using Kimi-K2.5 (from your Foundry)."""
        return await self._chat_call(settings.MODEL_KIMI, messages, **kwargs)

    async def deepseek_reasoning(self, messages: list, **kwargs):
        """Reasoning using DeepSeek-V3.2-Speciale (from your Foundry)."""
        return await self._chat_call(settings.MODEL_DEEPSEEK, messages, **kwargs)

    async def reasoning_fast(self, messages: list, **kwargs):
        """Fast reasoning using DeepSeek-V3.2-Speciale."""
        return await self._chat_call(settings.MODEL_REASONING_FAST, messages, **kwargs)

    async def claude_analysis(self, messages: list, **kwargs):
        """Qualitative analysis using MODEL_CLAUDE_ADVANCED (Kimi-K2.5)."""
        return await self._chat_call(settings.MODEL_CLAUDE_ADVANCED, messages, **kwargs)

    async def _chat_call(self, model: str, messages: list, temperature: float = 0.3, **kwargs):
        """Unified async chat completion call with retry on empty choices and auto param-stripping.

        Handles two classes of API errors automatically:
        - temperature unsupported (reasoning/o-series models): stripped on first 400 and
          model is added to _NO_TEMPERATURE_MODELS so future calls skip it immediately.
        - response_format: always stripped as a safety net.
        """
        import asyncio
        # Strip params that certain models never accept
        kwargs.pop("response_format", None)
        if model not in _NO_TEMPERATURE_MODELS:
            kwargs["temperature"] = temperature

        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = await self.client.chat.completions.create(
                    model=model,
                    messages=messages,
                    **kwargs,
                )
            except Exception as e:
                err_str = str(e)
                # Auto-detect reasoning models that reject custom temperature (400 unsupported_value)
                if "temperature" in err_str and "unsupported_value" in err_str and "temperature" in kwargs:
                    logger.warning(
                        "Model '%s' rejected temperature param — stripping and retrying. "
                        "Add to _NO_TEMPERATURE_MODELS to avoid future round-trip.",
                        model,
                    )
                    kwargs.pop("temperature")
                    _NO_TEMPERATURE_MODELS.add(model)
                    continue  # retry (temperature issue now fixed for this and future calls)
                raise
            else:
                if response.choices:
                    return response.choices[0].message.content
                if attempt < max_retries - 1:
                    wait = 2 ** attempt  # 1s, 2s
                    logger.warning(
                        "Model '%s' returned empty choices (attempt %d/%d). Retrying in %ds...",
                        model, attempt + 1, max_retries, wait,
                    )
                    await asyncio.sleep(wait)
        raise RuntimeError(
            f"Model '{model}' returned empty choices after {max_retries} attempts "
            f"(possible rate-limit or content filter)."
        )

foundry_openai = FoundryOpenAIService()
