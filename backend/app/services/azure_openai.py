from openai import AsyncAzureOpenAI
from ..core.settings import settings
import logging

logger = logging.getLogger(__name__)

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
        """Unified async chat completion call with retry on empty choices (rate-limit resilience)."""
        import asyncio
        max_retries = 3
        for attempt in range(max_retries):
            response = await self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                **kwargs,
            )
            if response.choices:
                return response.choices[0].message.content
            if attempt < max_retries - 1:
                wait = 2 ** attempt  # 1s, 2s
                logger.warning(
                    f"Model '{model}' returned empty choices "
                    f"(attempt {attempt + 1}/{max_retries}). Retrying in {wait}s..."
                )
                await asyncio.sleep(wait)
        raise RuntimeError(
            f"Model '{model}' returned empty choices after {max_retries} attempts "
            f"(possible rate-limit or content filter)."
        )

foundry_openai = FoundryOpenAIService()
