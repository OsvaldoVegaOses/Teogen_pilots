from openai import OpenAI, AzureOpenAI
from ..core.settings import settings
import logging

logger = logging.getLogger(__name__)

class FoundryOpenAIService:
    """Updated service for Microsoft Foundry & Azure OpenAI API v1 (2025)."""
    
    def __init__(self):
        self.client = None
        self.azure_client = None
        
        if settings.AZURE_OPENAI_API_KEY and settings.AZURE_OPENAI_ENDPOINT:
            # ✅ Option 1: Standard OpenAI client using the /v1/ endpoint
            # This is the new 2025 standard for simplified orchestration
            self.client = OpenAI(
                api_key=settings.AZURE_OPENAI_API_KEY,
                base_url=f"{settings.AZURE_OPENAI_ENDPOINT.rstrip('/')}/openai/v1/"
            )
            
            # ✅ Option 2: AzureOpenAI specific client for features like OIDC/Managed Identity
            self.azure_client = AzureOpenAI(
                api_key=settings.AZURE_OPENAI_API_KEY,
                api_version=settings.AZURE_OPENAI_API_VERSION,
                azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
            )
        else:
            logger.warning("Microsoft Foundry / Azure OpenAI credentials not found.")

    async def generate_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Generates 3072-dim embeddings using text-embedding-3-large."""
        if not self.client:
            raise Exception("AI client not initialized")
        
        response = self.client.embeddings.create(
            model=settings.MODEL_EMBEDDING,
            input=texts
        )
        return [item.embedding for item in response.data]

    async def reasoning_advanced(self, messages: list, **kwargs):
        """Deep reasoning using GPT-5.2 (gpt-5.2-chat in your portal)."""
        return await self._chat_call(settings.MODEL_REASONING_ADVANCED, messages, **kwargs)

    async def kimi_reasoning(self, messages: list, **kwargs):
        """Reasoning using Kimi-K2.5 (from your Foundry)."""
        return await self._chat_call(settings.MODEL_KIMI, messages, **kwargs)

    async def deepseek_reasoning(self, messages: list, **kwargs):
        """Reasoning using DeepSeek-V3.2-Speciale (from your Foundry)."""
        return await self._chat_call(settings.MODEL_DEEPSEEK, messages, **kwargs)

    async def reasoning_fast(self, messages: list, **kwargs):
        """Fast reasoning using o3-mini."""
        return await self._chat_call(settings.MODEL_REASONING_FAST, messages, **kwargs)

    async def claude_analysis(self, messages: list, **kwargs):
        """Qualitative analysis using Claude 3.5 Sonnet (available in Foundry)."""
        return await self._chat_call(settings.MODEL_CLAUDE_ADVANCED, messages, **kwargs)

    async def _chat_call(self, model: str, messages: list, temperature: float = 0.3, **kwargs):
        if not self.client:
            logger.info(f"MOCK AI CALL ({model}): Returning sample data.")
            # Detect if it's a coding task by looking at the messages/system prompt
            system_msg = next((m["content"] for m in messages if m["role"] == "system"), "")
            
            if "AXIAL_CODING" in system_msg or "extracted_codes" in system_msg:
                return """
                {
                  "extracted_codes": [
                    {
                      "label": "Capital Social Comunitario",
                      "definition": "Recursos y redes de apoyo que los actores comunitarios movilizan para mejorar su entorno.",
                      "properties": [{"name": "Fortaleza del vínculo", "dimension_range": "Débil a Fuerte"}],
                      "evidence_quote": "llevamos años trabajando en la junta de vecinos"
                    },
                    {
                      "label": "Resiliencia Territorial",
                      "definition": "Capacidad de la comunidad para enfrentar crisis externas como el cambio climático o falta de recursos.",
                      "properties": [{"name": "Autogestión", "dimension_range": "Baja a Alta"}],
                      "evidence_quote": "mejorar los espacios públicos"
                    }
                  ],
                  "axial_links_suggestions": [
                    {
                      "code_a": "Capital Social Comunitario",
                      "code_b": "Resiliencia Territorial",
                      "relationship_type": "causal",
                      "reasoning": "Un fuerte capital social permite una mayor resiliencia ante crisis."
                    }
                  ]
                }
                """
            
            if "CENTRAL_CATEGORY" in system_msg:
                return """
                {
                  "selected_central_category": "Empoderamiento Comunitario bajo Presión",
                  "detailed_reasoning": "Se seleccionó debido a su alta centralidad en todos los fragmentos analizados..."
                }
                """
                
            return "Sample AI response for local testing."
        
        response = self.client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            **kwargs
        )
        return response.choices[0].message.content

foundry_openai = FoundryOpenAIService()
