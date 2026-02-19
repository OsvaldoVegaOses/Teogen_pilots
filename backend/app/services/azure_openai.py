from openai import AsyncOpenAI, AsyncAzureOpenAI
from ..core.settings import settings
import logging

logger = logging.getLogger(__name__)

class FoundryOpenAIService:
    """Updated service for Microsoft Foundry & Azure OpenAI API v1 (2025).
    
    Uses async SDK clients to avoid blocking the event loop.
    No local/mock fallback — requires valid Azure credentials.
    """

    def __init__(self):
        self._client = None
        self._azure_client = None

    def _ensure_clients(self):
        if self._client and self._azure_client:
            return

        if not settings.AZURE_OPENAI_API_KEY or not settings.AZURE_OPENAI_ENDPOINT:
            raise RuntimeError(
                "AZURE_OPENAI_API_KEY and AZURE_OPENAI_ENDPOINT are required. "
                "TheoGen does not support local/mock AI mode."
            )

        # ✅ Async OpenAI client using the /v1/ endpoint
        self._client = AsyncOpenAI(
            api_key=settings.AZURE_OPENAI_API_KEY,
            base_url=f"{settings.AZURE_OPENAI_ENDPOINT.rstrip('/')}/openai/v1/",
        )

        # ✅ Async AzureOpenAI client for features like OIDC/Managed Identity
        self._azure_client = AsyncAzureOpenAI(
            api_key=settings.AZURE_OPENAI_API_KEY,
            api_version=settings.AZURE_OPENAI_API_VERSION,
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
        )

    @property
    def client(self):
        self._ensure_clients()
        return self._client

    @property
    def azure_client(self):
        self._ensure_clients()
        return self._azure_client

    async def generate_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Generates 3072-dim embeddings using text-embedding-3-large."""
        response = await self.client.embeddings.create(
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
        """Unified async chat completion call. No mock/fallback."""
        response = await self.client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            **kwargs,
        )
        return response.choices[0].message.content

foundry_openai = FoundryOpenAIService()
