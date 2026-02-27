import logging

from ..core.settings import settings
from .assistant_knowledge import assistant_knowledge_version, get_assistant_knowledge
from .azure_openai import foundry_openai

logger = logging.getLogger(__name__)


class AssistantLLMService:
    def _public_system_prompt(self) -> str:
        knowledge = get_assistant_knowledge()
        public_knowledge = knowledge.get("public", {})
        blocked = knowledge.get("blocked", {})

        return (
            "Eres el asistente publico de TheoGen para visitantes de la landing. "
            "Tu tarea es responder solo con informacion comercial y publica de la plataforma.\n\n"
            "Restricciones obligatorias:\n"
            "1. Nunca entregues codigo fuente, secretos, tokens, passwords, .env, connection strings ni datos internos.\n"
            "2. No inventes funcionalidades, precios, clientes, implementaciones ni acceso a datos.\n"
            "3. Si la pregunta es sensible o esta fuera del alcance publico, responde exactamente con la politica de bloqueo.\n"
            "4. Si no estas seguro, orienta al contacto comercial oficial.\n"
            "5. Responde breve, clara y en espanol.\n\n"
            f"Politica de bloqueo: {blocked.get('sensitive_request', '')}\n\n"
            f"Base de conocimiento publica: {public_knowledge}\n"
            f"Version de conocimiento: {assistant_knowledge_version()}"
        )

    def _authenticated_system_prompt(self) -> str:
        knowledge = get_assistant_knowledge()
        auth_knowledge = knowledge.get("authenticated", {})
        public_knowledge = knowledge.get("public", {})
        blocked = knowledge.get("blocked", {})

        return (
            "Eres el asistente tecnico de TheoGen para usuarios autenticados. "
            "Tu tarea es ayudar con uso funcional de la plataforma, no con codigo fuente ni infraestructura sensible.\n\n"
            "Restricciones obligatorias:\n"
            "1. Nunca entregues codigo fuente, consultas SQL, secretos, tokens, passwords, .env, connection strings, ni datos internos del proyecto.\n"
            "2. No inventes acceso a entrevistas, proyectos o datos privados.\n"
            "3. Si el usuario pide algo sensible, responde exactamente con la politica de bloqueo.\n"
            "4. Responde de forma breve, operativa y en espanol.\n"
            "5. Si la pregunta no esta cubierta, orienta al uso funcional y contacto.\n\n"
            f"Politica de bloqueo: {blocked.get('sensitive_request', '')}\n\n"
            f"Base de conocimiento publica: {public_knowledge}\n"
            f"Base de conocimiento autenticada: {auth_knowledge}\n"
            f"Version de conocimiento: {assistant_knowledge_version()}"
        )

    async def generate_authenticated_reply(self, user_message: str) -> str:
        messages = [
            {"role": "system", "content": self._authenticated_system_prompt()},
            {"role": "user", "content": user_message.strip()},
        ]
        return await foundry_openai.assistant_chat(
            settings.MODEL_ASSISTANT_AUTHENTICATED,
            messages,
            temperature=0.1,
            max_tokens=500,
        )

    async def generate_public_reply(self, user_message: str) -> str:
        messages = [
            {"role": "system", "content": self._public_system_prompt()},
            {"role": "user", "content": user_message.strip()},
        ]
        return await foundry_openai.assistant_chat(
            settings.MODEL_ASSISTANT_PUBLIC,
            messages,
            temperature=0.1,
            max_tokens=220,
        )


assistant_llm_service = AssistantLLMService()
