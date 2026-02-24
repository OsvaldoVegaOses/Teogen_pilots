from __future__ import annotations

import logging

from openai import AsyncAzureOpenAI

from ..core.settings import settings

logger = logging.getLogger(__name__)

# Models that reject custom temperature values.
_NO_TEMPERATURE_MODELS: set[str] = {
    "gpt-5.2-chat",
    "o1",
    "o1-mini",
    "o1-preview",
    "o3",
    "o3-mini",
    "o4-mini",
}

# Families that currently reject JSON mode in our Azure Foundry setup.
_NO_JSON_MODELS: set[str] = {"deepseek", "kimi"}

# Models that require max_completion_tokens instead of max_tokens.
_USE_MAX_COMPLETION_TOKENS_MODELS: set[str] = {
    "gpt-5.2-chat",
    "o1",
    "o1-mini",
    "o1-preview",
    "o3",
    "o3-mini",
    "o4-mini",
}


class FoundryOpenAIService:
    """Service for Microsoft Foundry and Azure OpenAI chat/embeddings."""

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
        return self._azure_client

    @property
    def azure_client(self):
        self._ensure_clients()
        return self._azure_client

    @staticmethod
    def _normalize_model_name(model: str) -> str:
        return (model or "").strip().lower()

    def _supports_temperature(self, model: str) -> bool:
        normalized = self._normalize_model_name(model)
        if normalized in _NO_TEMPERATURE_MODELS:
            return False
        if normalized.startswith(("o1", "o3", "o4")):
            return False
        return True

    def _supports_json_mode(self, model: str) -> bool:
        normalized = self._normalize_model_name(model)
        return not any(blocked in normalized for blocked in _NO_JSON_MODELS)

    def _uses_max_completion_tokens(self, model: str) -> bool:
        normalized = self._normalize_model_name(model)
        if normalized in _USE_MAX_COMPLETION_TOKENS_MODELS:
            return True
        return normalized.startswith(("o1", "o3", "o4"))

    async def generate_embeddings(self, texts: list[str]) -> list[list[float]]:
        response = await self.azure_client.embeddings.create(
            model=settings.MODEL_EMBEDDING,
            input=texts,
        )
        return [item.embedding for item in response.data]

    async def reasoning_advanced(self, messages: list, **kwargs):
        return await self._chat_call(settings.MODEL_REASONING_ADVANCED, messages, **kwargs)

    async def kimi_reasoning(self, messages: list, **kwargs):
        return await self._chat_call(settings.MODEL_KIMI, messages, **kwargs)

    async def deepseek_reasoning(self, messages: list, **kwargs):
        return await self._chat_call(settings.MODEL_DEEPSEEK, messages, **kwargs)

    async def reasoning_fast(self, messages: list, **kwargs):
        return await self._chat_call(settings.MODEL_REASONING_FAST, messages, **kwargs)

    async def claude_analysis(self, messages: list, **kwargs):
        return await self._chat_call(settings.MODEL_CLAUDE_ADVANCED, messages, **kwargs)

    async def _chat_call(self, model: str, messages: list, temperature: float = 0.3, **kwargs):
        """Unified async chat completion with capability-aware parameter handling."""
        import asyncio

        response_format = kwargs.pop("response_format", None)
        token_limit = kwargs.pop("max_tokens", None) or settings.THEORY_LLM_MAX_OUTPUT_TOKENS

        if self._uses_max_completion_tokens(model):
            kwargs.setdefault("max_completion_tokens", token_limit)
            kwargs.pop("max_tokens", None)
        else:
            kwargs.setdefault("max_tokens", token_limit)
            kwargs.pop("max_completion_tokens", None)

        if self._supports_temperature(model):
            kwargs["temperature"] = temperature
        else:
            kwargs.pop("temperature", None)

        if response_format and self._supports_json_mode(model):
            kwargs["response_format"] = response_format

        logger.debug(
            "LLM call model=%s temp=%s max_tokens=%s max_completion_tokens=%s response_format=%s keys=%s",
            model,
            kwargs.get("temperature"),
            kwargs.get("max_tokens"),
            kwargs.get("max_completion_tokens"),
            kwargs.get("response_format"),
            sorted(kwargs.keys()),
        )

        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = await self.client.chat.completions.create(
                    model=model,
                    messages=messages,
                    **kwargs,
                )
            except Exception as e:
                err_str = str(e).lower()

                if "temperature" in err_str and "unsupported" in err_str and "temperature" in kwargs:
                    logger.warning(
                        "Model '%s' rejected temperature param - stripping and retrying.",
                        model,
                    )
                    kwargs.pop("temperature", None)
                    _NO_TEMPERATURE_MODELS.add(self._normalize_model_name(model))
                    continue

                if "response_format" in err_str and "unsupported" in err_str and "response_format" in kwargs:
                    logger.warning(
                        "Model '%s' rejected response_format - stripping and retrying.",
                        model,
                    )
                    kwargs.pop("response_format", None)
                    lowered = self._normalize_model_name(model)
                    if "deepseek" in lowered:
                        _NO_JSON_MODELS.add("deepseek")
                    if "kimi" in lowered:
                        _NO_JSON_MODELS.add("kimi")
                    continue

                if "max_tokens" in err_str and "unsupported" in err_str and "max_tokens" in kwargs:
                    logger.warning(
                        "Model '%s' rejected max_tokens - switching to max_completion_tokens and retrying.",
                        model,
                    )
                    limit = kwargs.pop("max_tokens")
                    kwargs["max_completion_tokens"] = limit
                    _USE_MAX_COMPLETION_TOKENS_MODELS.add(self._normalize_model_name(model))
                    continue

                if (
                    "max_completion_tokens" in err_str
                    and "unsupported" in err_str
                    and "max_completion_tokens" in kwargs
                ):
                    logger.warning(
                        "Model '%s' rejected max_completion_tokens - switching to max_tokens and retrying.",
                        model,
                    )
                    limit = kwargs.pop("max_completion_tokens")
                    kwargs["max_tokens"] = limit
                    _USE_MAX_COMPLETION_TOKENS_MODELS.discard(self._normalize_model_name(model))
                    continue

                raise
            else:
                if response.choices:
                    return response.choices[0].message.content

                if attempt < max_retries - 1:
                    wait = 2**attempt
                    logger.warning(
                        "Model '%s' returned empty choices (attempt %d/%d). Retrying in %ds...",
                        model,
                        attempt + 1,
                        max_retries,
                        wait,
                    )
                    await asyncio.sleep(wait)

        raise RuntimeError(
            f"Model '{model}' returned empty choices after {max_retries} attempts "
            f"(possible rate-limit or content filter)."
        )


foundry_openai = FoundryOpenAIService()
