import logging
import re
import uuid
from collections import deque
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..assistant_database import ensure_assistant_schema, get_assistant_db
from ..core.auth import CurrentUser, get_current_user, get_optional_user
from ..core.settings import settings

logger = logging.getLogger(__name__)
from ..models.assistant_models import AssistantContactLead, AssistantMessageLog
from ..schemas.assistant import (
    AssistantLeadCreateRequest,
    AssistantLeadCreateResponse,
    AssistantMetricsResponse,
    AssistantMessageLogItem,
    AssistantLeadItem,
    AssistantOpsResponse,
    PublicAssistantChatRequest,
    PublicAssistantChatResponse,
)
from ..services.assistant_knowledge import assistant_knowledge_version, assistant_reply
from ..services.assistant_llm_service import assistant_llm_service

router = APIRouter(prefix="/assistant", tags=["Assistant"])

_BLOCKED_PATTERNS = [
    "codigo fuente",
    "source code",
    "repositorio",
    "token",
    "password",
    "clave",
    "secret",
    "credenciales",
    ".env",
    "base de datos interna",
    "datos del proyecto",
    "connection string",
    "api key",
    "azure_pg",
    "host de base de datos",
    "dump",
    "schema interno",
]
_PUBLIC_CHAT_WINDOW_SECONDS = 300
_PUBLIC_CHAT_MAX_REQUESTS = 20
_PUBLIC_LEAD_WINDOW_SECONDS = 3600
_PUBLIC_LEAD_MAX_REQUESTS = 5
_PUBLIC_LLM_FALLBACK_MAX_PER_SESSION = 4
_PUBLIC_LLM_FALLBACK_TTL_SECONDS = 7200  # 2 h por sesión
_rate_limit_store: dict[str, deque[datetime]] = {}
_public_llm_fallback_store: dict[str, int] = {}
_redis_assistant = None


async def _get_redis_assistant():
    """Lazy Redis client reutilizable; devuelve None si no está configurado."""
    global _redis_assistant
    if _redis_assistant is not None:
        return _redis_assistant
    if not (settings.AZURE_REDIS_HOST and settings.AZURE_REDIS_KEY):
        return None
    try:
        import redis.asyncio as aioredis

        client = aioredis.Redis(
            host=settings.AZURE_REDIS_HOST,
            port=settings.REDIS_SSL_PORT,
            password=settings.AZURE_REDIS_KEY,
            ssl=True,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        await client.ping()
        _redis_assistant = client
    except Exception as exc:
        logger.warning("Redis no disponible para asistente (modo in-memory): %s", exc)
        _redis_assistant = None
    return _redis_assistant


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def _client_key(request: Request, session_id: str | None, namespace: str) -> str:
    ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "unknown")
    normalized_ip = str(ip).split(",")[0].strip()
    return f"{namespace}:{normalized_ip}:{session_id or 'anon'}"


async def _check_rate_limit(key: str, window_seconds: int, max_requests: int) -> None:
    redis = await _get_redis_assistant()
    if redis:
        try:
            now = datetime.utcnow().timestamp()
            window_start = now - window_seconds
            rkey = f"asst:rl:{key}"
            async with redis.pipeline(transaction=True) as pipe:
                pipe.zremrangebyscore(rkey, 0, window_start)
                pipe.zcard(rkey)
                pipe.zadd(rkey, {str(now): now})
                pipe.expire(rkey, window_seconds + 10)
                results = await pipe.execute()
            if results[1] >= max_requests:
                raise HTTPException(status_code=429, detail="Rate limit exceeded for assistant endpoint")
            return
        except HTTPException:
            raise
        except Exception as exc:
            logger.warning("Redis rate limit fallback a in-memory: %s", exc)

    # Fallback in-memory (instancia única o Redis no disponible)
    now_dt = datetime.utcnow()
    window_start_dt = now_dt - timedelta(seconds=window_seconds)
    bucket = _rate_limit_store.setdefault(key, deque())
    while bucket and bucket[0] < window_start_dt:
        bucket.popleft()
    if len(bucket) >= max_requests:
        raise HTTPException(status_code=429, detail="Rate limit exceeded for assistant endpoint")
    bucket.append(now_dt)


def _resolve_public_reply(user_message: str) -> tuple[str, str, bool]:
    q = _normalize_text(user_message)

    if any(p in q for p in _BLOCKED_PATTERNS):
        return (
            assistant_reply("blocked", "sensitive_request"),
            "blocked_sensitive_request",
            True,
        )

    if any(k in q for k in ["contacto", "email", "correo", "comercial"]):
        return (
            assistant_reply("public", "contact"),
            "contact",
            False,
        )

    if any(k in q for k in ["que es", "theogen", "plataforma"]):
        return (
            assistant_reply("public", "platform_overview"),
            "platform_overview",
            False,
        )

    if any(k in q for k in ["industria", "segmento", "para quien"]):
        return (
            assistant_reply("public", "segments"),
            "segments",
            False,
        )

    if any(k in q for k in ["como funciona", "flujo", "pasos"]):
        return (
            assistant_reply("public", "workflow"),
            "workflow",
            False,
        )

    if any(k in q for k in ["precio", "plan", "demo", "probar"]):
        return (
            assistant_reply("public", "commercial"),
            "commercial",
            False,
        )

    return (
        assistant_reply("public", "general"),
        "general",
        False,
    )


async def _can_use_public_llm_fallback(session_id: str) -> bool:
    redis = await _get_redis_assistant()
    if redis:
        try:
            raw = await redis.get(f"asst:llm:{session_id}")
            return raw is None or int(raw) < _PUBLIC_LLM_FALLBACK_MAX_PER_SESSION
        except Exception as exc:
            logger.warning("Redis llm-fallback check error: %s", exc)
    return _public_llm_fallback_store.get(session_id, 0) < _PUBLIC_LLM_FALLBACK_MAX_PER_SESSION


async def _mark_public_llm_fallback(session_id: str) -> int:
    redis = await _get_redis_assistant()
    if redis:
        try:
            rkey = f"asst:llm:{session_id}"
            count = await redis.incr(rkey)
            if count == 1:
                await redis.expire(rkey, _PUBLIC_LLM_FALLBACK_TTL_SECONDS)
            return count
        except Exception as exc:
            logger.warning("Redis llm-fallback mark error: %s", exc)
    next_count = _public_llm_fallback_store.get(session_id, 0) + 1
    _public_llm_fallback_store[session_id] = next_count
    return next_count


def _resolve_authenticated_reply(user_message: str) -> tuple[str, str, bool]:
    q = _normalize_text(user_message)

    if any(p in q for p in _BLOCKED_PATTERNS):
        return (
            assistant_reply("blocked", "sensitive_request"),
            "blocked_sensitive_request",
            True,
        )

    if any(k in q for k in ["codificacion", "open coding", "axial", "selectiva", "selective"]):
        return (
            assistant_reply("authenticated", "technical_coding_flow"),
            "technical_coding_flow",
            False,
        )

    if any(k in q for k in ["teoria", "claim", "evidencia", "fragmento", "trazabilidad"]):
        return (
            assistant_reply("authenticated", "technical_theory_traceability"),
            "technical_theory_traceability",
            False,
        )

    if any(k in q for k in ["entrevista", "transcripcion", "audio"]):
        return (
            assistant_reply("authenticated", "technical_interview_pipeline"),
            "technical_interview_pipeline",
            False,
        )

    if any(k in q for k in ["exportar", "reporte", "pdf", "ppt", "xlsx"]):
        return (
            assistant_reply("authenticated", "technical_exports"),
            "technical_exports",
            False,
        )

    if any(k in q for k in ["error", "falla", "timeout", "no responde"]):
        return (
            assistant_reply("authenticated", "technical_troubleshooting"),
            "technical_troubleshooting",
            False,
        )

    if any(k in q for k in ["contacto", "email", "correo", "comercial"]):
        return (
            assistant_reply("authenticated", "contact"),
            "contact",
            False,
        )

    return (
        assistant_reply("authenticated", "authenticated_general"),
        "authenticated_general",
        False,
    )


async def _persist_chat_log(
    *,
    assistant_db: AsyncSession | None,
    session_id: str,
    mode: str,
    user: CurrentUser | None,
    user_message: str,
    assistant_reply: str,
    intent: str,
    blocked: bool,
    request: Request,
) -> bool:
    logging_enabled = await ensure_assistant_schema()
    if logging_enabled and assistant_db is not None:
        log_entry = AssistantMessageLog(
            session_id=session_id,
            mode=mode,
            user_id=(user.user_uuid if user else None),
            user_message=user_message.strip(),
            assistant_reply=assistant_reply,
            intent=intent,
            blocked=blocked,
            client_ip=request.headers.get("x-forwarded-for", request.client.host if request.client else None),
            user_agent=request.headers.get("user-agent"),
        )
        assistant_db.add(log_entry)
        await assistant_db.commit()
    return logging_enabled


@router.post("/public/chat", response_model=PublicAssistantChatResponse)
async def public_chat(
    payload: PublicAssistantChatRequest,
    request: Request,
    user: CurrentUser | None = Depends(get_optional_user),
    assistant_db: AsyncSession | None = Depends(get_assistant_db),
):
    session_id = payload.session_id or str(uuid.uuid4())
    await _check_rate_limit(
        _client_key(request, session_id, "public-chat"),
        window_seconds=_PUBLIC_CHAT_WINDOW_SECONDS,
        max_requests=_PUBLIC_CHAT_MAX_REQUESTS,
    )
    reply, intent, blocked = _resolve_public_reply(payload.message)
    if not blocked and intent == "general" and await _can_use_public_llm_fallback(session_id):
        try:
            llm_reply = await assistant_llm_service.generate_public_reply(payload.message)
            if llm_reply and llm_reply.strip():
                reply = llm_reply.strip()
                count = await _mark_public_llm_fallback(session_id)
                intent = f"llm_fallback_general_{count}"
        except Exception:
            # Keep deterministic generic fallback if LLM is unavailable.
            pass

    logging_enabled = await _persist_chat_log(
        assistant_db=assistant_db,
        session_id=session_id,
        mode="authenticated_public" if user else "public",
        user=user,
        user_message=payload.message,
        assistant_reply=reply,
        intent=intent,
        blocked=blocked,
        request=request,
    )

    return PublicAssistantChatResponse(
        session_id=session_id,
        reply=reply,
        blocked=blocked,
        intent=f"{intent}@{assistant_knowledge_version()}",
        logging_enabled=logging_enabled,
    )


@router.post("/authenticated/chat", response_model=PublicAssistantChatResponse)
async def authenticated_chat(
    payload: PublicAssistantChatRequest,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    assistant_db: AsyncSession | None = Depends(get_assistant_db),
):
    reply, intent, blocked = _resolve_authenticated_reply(payload.message)
    if not blocked:
        try:
            llm_reply = await assistant_llm_service.generate_authenticated_reply(payload.message)
            if llm_reply and llm_reply.strip():
                reply = llm_reply.strip()
                intent = f"llm_{intent}"
        except Exception:
            # Preserve deterministic fallback for reliability.
            pass
    session_id = payload.session_id or str(uuid.uuid4())

    logging_enabled = await _persist_chat_log(
        assistant_db=assistant_db,
        session_id=session_id,
        mode="authenticated",
        user=user,
        user_message=payload.message,
        assistant_reply=reply,
        intent=intent,
        blocked=blocked,
        request=request,
    )

    return PublicAssistantChatResponse(
        session_id=session_id,
        reply=reply,
        blocked=blocked,
        intent=f"{intent}@{assistant_knowledge_version()}",
        logging_enabled=logging_enabled,
    )


@router.post("/public/lead", response_model=AssistantLeadCreateResponse)
async def create_public_lead(
    payload: AssistantLeadCreateRequest,
    request: Request,
    user: CurrentUser | None = Depends(get_optional_user),
    assistant_db: AsyncSession | None = Depends(get_assistant_db),
):
    await _check_rate_limit(
        _client_key(request, payload.session_id, "public-lead"),
        window_seconds=_PUBLIC_LEAD_WINDOW_SECONDS,
        max_requests=_PUBLIC_LEAD_MAX_REQUESTS,
    )
    if not payload.consent:
        return AssistantLeadCreateResponse(
            created=False,
            logging_enabled=False,
            message="Se requiere consentimiento para registrar datos de contacto.",
        )

    logging_enabled = await ensure_assistant_schema()
    if not logging_enabled or assistant_db is None:
        return AssistantLeadCreateResponse(
            created=False,
            logging_enabled=False,
            message="Registro de contacto no disponible temporalmente.",
        )

    lead = AssistantContactLead(
        session_id=payload.session_id,
        source_mode="authenticated_public" if user else "public",
        user_id=(user.user_uuid if user else None),
        name=payload.name.strip(),
        email=payload.email.strip(),
        company=(payload.company.strip() if payload.company else None),
        phone=(payload.phone.strip() if payload.phone else None),
        notes=(payload.notes.strip() if payload.notes else None),
        consent=payload.consent,
        client_ip=request.headers.get("x-forwarded-for", request.client.host if request.client else None),
        user_agent=request.headers.get("user-agent"),
    )
    assistant_db.add(lead)
    await assistant_db.commit()

    return AssistantLeadCreateResponse(
        created=True,
        logging_enabled=True,
        message="Gracias. Tu solicitud de contacto fue registrada.",
    )


@router.get("/authenticated/metrics", response_model=AssistantMetricsResponse)
async def get_authenticated_metrics(
    _user: CurrentUser = Depends(get_current_user),
    assistant_db: AsyncSession | None = Depends(get_assistant_db),
):
    logging_enabled = await ensure_assistant_schema()
    if not logging_enabled or assistant_db is None:
        return AssistantMetricsResponse(
            logging_enabled=False,
            total_messages_7d=0,
            blocked_messages_7d=0,
            leads_7d=0,
        )

    since = datetime.utcnow() - timedelta(days=7)

    total_messages_result = await assistant_db.execute(
        select(func.count(AssistantMessageLog.id)).where(AssistantMessageLog.created_at >= since)
    )
    blocked_messages_result = await assistant_db.execute(
        select(func.count(AssistantMessageLog.id)).where(
            AssistantMessageLog.created_at >= since,
            AssistantMessageLog.blocked.is_(True),
        )
    )
    leads_result = await assistant_db.execute(
        select(func.count(AssistantContactLead.id)).where(AssistantContactLead.created_at >= since)
    )

    return AssistantMetricsResponse(
        logging_enabled=True,
        total_messages_7d=int(total_messages_result.scalar() or 0),
        blocked_messages_7d=int(blocked_messages_result.scalar() or 0),
        leads_7d=int(leads_result.scalar() or 0),
    )


@router.get("/authenticated/ops", response_model=AssistantOpsResponse)
async def get_authenticated_ops(
    _user: CurrentUser = Depends(get_current_user),
    assistant_db: AsyncSession | None = Depends(get_assistant_db),
):
    logging_enabled = await ensure_assistant_schema()
    if not logging_enabled or assistant_db is None:
        return AssistantOpsResponse(logging_enabled=False, recent_messages=[], recent_leads=[])

    messages_result = await assistant_db.execute(
        select(AssistantMessageLog).order_by(AssistantMessageLog.created_at.desc()).limit(20)
    )
    leads_result = await assistant_db.execute(
        select(AssistantContactLead).order_by(AssistantContactLead.created_at.desc()).limit(20)
    )

    recent_messages = [
        AssistantMessageLogItem(
            session_id=row.session_id,
            mode=row.mode,
            user_message=row.user_message,
            assistant_reply=row.assistant_reply,
            intent=row.intent,
            blocked=bool(row.blocked),
            created_at=row.created_at.isoformat() if row.created_at else "",
        )
        for row in messages_result.scalars().all()
    ]
    recent_leads = [
        AssistantLeadItem(
            session_id=row.session_id,
            source_mode=row.source_mode,
            name=row.name,
            email=row.email,
            company=row.company,
            phone=row.phone,
            created_at=row.created_at.isoformat() if row.created_at else "",
        )
        for row in leads_result.scalars().all()
    ]

    return AssistantOpsResponse(
        logging_enabled=True,
        recent_messages=recent_messages,
        recent_leads=recent_leads,
    )
