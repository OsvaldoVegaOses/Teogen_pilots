from __future__ import annotations

import asyncio
import json as _json
import logging
import time
import uuid
from datetime import datetime
from json import JSONDecodeError
from typing import Any, Dict, List, Optional, Set
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import MultipleResultsFound
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import CurrentUser, get_current_user
from ..core.settings import settings
from ..database import get_db, get_session_local
from ..engines.theory_pipeline import TheoryPipeline, TheoryPipelineError
from ..models.models import Project, Theory
from ..prompts.domain_templates import DOMAIN_TEMPLATES
from ..schemas.theory import (
    TheoryGenerateRequest,
    TheoryResponse,
    TheoryClaimsExplainResponse,
    TheoryJudgeRolloutResponse,
    TheoryPipelineSloResponse,
    TheoryExportReadinessResponse,
)
from ..services.export.privacy import detect_pii_types, redact_pii_text
from ..services.export_service import export_service
from ..services.neo4j_service import neo4j_service
from ..services.storage_service import storage_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects", tags=["Theory"])

_TASK_TTL = 86400
_TASK_PREFIX = "theory_task:"
_LOCK_PREFIX = "theory_lock:"
_redis_client = None
_theory_tasks: Dict[str, Dict[str, Any]] = {}
_background_tasks: Set[asyncio.Task] = set()
_background_tasks_by_id: Dict[str, asyncio.Task] = {}
_local_pipeline_semaphore = asyncio.Semaphore(max(1, settings.THEORY_LOCAL_MAX_CONCURRENT_TASKS))
theory_pipeline = TheoryPipeline()
_CLAIM_SECTIONS = (
    "conditions",
    "context",
    "intervening_conditions",
    "actions",
    "consequences",
    "propositions",
)
_TEMPLATE_EXPORT_POLICY: Dict[str, Dict[str, Any]] = {
    "generic": {
        "min_claims": 1,
        "min_interviews": 1,
        "allow_warn_only": False,
        "min_propositions": 0,
        "min_consequences": 0,
        "require_context_or_intervening": False,
        "require_consequence_balance": False,
    },
    "education": {
        "min_claims": 2,
        "min_interviews": 3,
        "allow_warn_only": False,
        "min_propositions": 5,
        "min_consequences": 3,
        "require_context_or_intervening": True,
        "require_consequence_balance": True,
    },
    "ngo": {
        "min_claims": 2,
        "min_interviews": 2,
        "allow_warn_only": False,
        "min_propositions": 5,
        "min_consequences": 3,
        "require_context_or_intervening": True,
        "require_consequence_balance": True,
    },
    "government": {
        "min_claims": 2,
        "min_interviews": 3,
        "allow_warn_only": False,
        "min_propositions": 5,
        "min_consequences": 3,
        "require_context_or_intervening": True,
        "require_consequence_balance": True,
    },
    "market_research": {
        "min_claims": 2,
        "min_interviews": 3,
        "allow_warn_only": False,
        "min_propositions": 5,
        "min_consequences": 3,
        "require_context_or_intervening": True,
        "require_consequence_balance": True,
    },
    "b2c": {
        "min_claims": 2,
        "min_interviews": 2,
        "allow_warn_only": False,
        "min_propositions": 5,
        "min_consequences": 3,
        "require_context_or_intervening": True,
        "require_consequence_balance": True,
    },
    "consulting": {
        "min_claims": 2,
        "min_interviews": 2,
        "allow_warn_only": False,
        "min_propositions": 5,
        "min_consequences": 3,
        "require_context_or_intervening": True,
        "require_consequence_balance": True,
    },
}


def _normalize_template_key(value: Any) -> str:
    key = str(value or "generic").strip().lower()
    if key in DOMAIN_TEMPLATES:
        return key
    return "generic"


def _resolve_template_export_policy(template_key: str) -> Dict[str, Any]:
    key = _normalize_template_key(template_key)
    policy = _TEMPLATE_EXPORT_POLICY.get(key) or _TEMPLATE_EXPORT_POLICY["generic"]
    return {
        "template_key": key,
        "min_claims": int(policy.get("min_claims") or 1),
        "min_interviews": int(policy.get("min_interviews") or 1),
        "allow_warn_only": bool(policy.get("allow_warn_only")),
        "min_propositions": int(policy.get("min_propositions") or 0),
        "min_consequences": int(policy.get("min_consequences") or 0),
        "require_context_or_intervening": bool(policy.get("require_context_or_intervening")),
        "require_consequence_balance": bool(policy.get("require_consequence_balance")),
    }


def _use_celery_mode() -> bool:
    return bool(settings.THEORY_USE_CELERY and settings.AZURE_REDIS_HOST and settings.AZURE_REDIS_KEY)


async def _get_redis():
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    try:
        if not (settings.AZURE_REDIS_HOST and settings.AZURE_REDIS_KEY):
            return None
        import redis.asyncio as aioredis

        _redis_client = aioredis.Redis(
            host=settings.AZURE_REDIS_HOST,
            port=settings.REDIS_SSL_PORT,
            password=settings.AZURE_REDIS_KEY,
            ssl=True,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        await _redis_client.ping()
        logger.info("Redis task store connected: %s", settings.AZURE_REDIS_HOST)
    except Exception as e:
        logger.warning("Redis task store unavailable, using memory only: %s", e)
        _redis_client = None
    return _redis_client


async def _persist_task(task_id: str) -> None:
    task = _theory_tasks.get(task_id)
    if not task:
        return
    redis = await _get_redis()
    if redis:
        try:
            await redis.setex(
                f"{_TASK_PREFIX}{task_id}",
                _TASK_TTL,
                _json.dumps(task, default=str),
            )
        except Exception as e:
            logger.warning("Redis persist failed for task %s: %s", task_id, e)


async def _restore_task(task_id: str) -> Optional[Dict[str, Any]]:
    if task_id in _theory_tasks:
        return _theory_tasks[task_id]
    redis = await _get_redis()
    if not redis:
        return None
    try:
        raw = await redis.get(f"{_TASK_PREFIX}{task_id}")
        if raw:
            task = _json.loads(raw)
            _theory_tasks[task_id] = task
            return task
    except Exception as e:
        logger.warning("Redis restore failed for task %s: %s", task_id, e)
    return None


def _new_task_payload(task_id: str, project_id: UUID, user_uuid: UUID) -> Dict[str, Any]:
    return {
        "task_id": task_id,
        "status": "pending",
        "result": None,
        "error": None,
        "error_code": None,
        "project_id": str(project_id),
        "owner_id": str(user_uuid),
        "step": "queued",
        "progress": 0,
        "next_poll_seconds": max(2, settings.THEORY_STATUS_POLL_HINT_SECONDS),
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
    }


def _normalize_evidence_ids(raw: Any) -> List[str]:
    if not isinstance(raw, list):
        return []
    return [str(item).strip() for item in raw if str(item).strip()]


def _extract_claim_evidence_ids(item: Any) -> List[str]:
    if not isinstance(item, dict):
        return []
    evidence_ids = _normalize_evidence_ids(item.get("evidence_ids"))
    single = item.get("evidence_id")
    if single is not None and str(single).strip():
        evidence_ids.append(str(single).strip())
    return [value for value in dict.fromkeys(evidence_ids) if value]


def _extract_claim_text(item: Any) -> str:
    if isinstance(item, dict):
        return str(
            item.get("text")
            or item.get("name")
            or item.get("description")
            or item.get("definition")
            or ""
        ).strip()
    if isinstance(item, (str, int, float)):
        return str(item).strip()
    return ""


def _iter_claim_entries(model_json: Dict[str, Any]) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    for section in _CLAIM_SECTIONS:
        raw_items = model_json.get(section) or []
        if not isinstance(raw_items, list):
            raw_items = [raw_items]
        for order, item in enumerate(raw_items):
            text = _extract_claim_text(item)
            if not text:
                continue
            entries.append(
                {
                    "section": section,
                    "order": order,
                    "text": text,
                    "evidence_ids": _extract_claim_evidence_ids(item),
                }
            )
    return entries


def _compute_claim_metrics_from_model(model_json: Dict[str, Any]) -> Dict[str, int]:
    claims_count = 0
    claims_without_evidence = 0

    for entry in _iter_claim_entries(model_json):
        claims_count += 1
        if not entry["evidence_ids"]:
            claims_without_evidence += 1

    return {
        "claims_count": int(claims_count),
        "claims_without_evidence": int(claims_without_evidence),
    }


def _build_export_quality_gate(theory: Theory, template_key: str = "generic") -> Dict[str, Any]:
    validation = theory.validation if isinstance(theory.validation, dict) else {}
    claim_metrics = validation.get("claim_metrics") if isinstance(validation.get("claim_metrics"), dict) else {}
    judge = validation.get("judge") if isinstance(validation.get("judge"), dict) else {}
    policy = _resolve_template_export_policy(template_key)

    claims_count = claim_metrics.get("claims_count")
    claims_without_evidence = claim_metrics.get("claims_without_evidence")
    interviews_covered = claim_metrics.get("interviews_covered")
    judge_warn_only = judge.get("warn_only")

    fallback_metrics = _compute_claim_metrics_from_model(theory.model_json if isinstance(theory.model_json, dict) else {})
    if not isinstance(claims_count, int):
        claims_count = fallback_metrics["claims_count"]
    if not isinstance(claims_without_evidence, int):
        claims_without_evidence = fallback_metrics["claims_without_evidence"]
    if not isinstance(interviews_covered, int):
        interviews_covered = None
    if not isinstance(judge_warn_only, bool):
        judge_warn_only = None

    model_json = theory.model_json if isinstance(theory.model_json, dict) else {}
    network_metrics_summary = (
        validation.get("network_metrics_summary")
        if isinstance(validation.get("network_metrics_summary"), dict)
        else {}
    )
    evidence_index = network_metrics_summary.get("evidence_index", [])
    if not isinstance(evidence_index, list):
        evidence_index = []
    evidence_ids_catalog_raw = network_metrics_summary.get("evidence_ids", [])
    if not isinstance(evidence_ids_catalog_raw, list):
        evidence_ids_catalog_raw = []

    evidence_catalog_ids: Set[str] = set()
    for ev in evidence_index:
        if not isinstance(ev, dict):
            continue
        fid = str(ev.get("fragment_id") or ev.get("id") or "").strip()
        if fid:
            evidence_catalog_ids.add(fid)
    for value in evidence_ids_catalog_raw:
        sid = str(value).strip()
        if sid:
            evidence_catalog_ids.add(sid)
    evidence_catalog_available = len(evidence_catalog_ids) > 0

    claims_with_resolved_evidence = 0
    claims_with_unresolved_evidence = 0
    unresolved_evidence_examples: List[Dict[str, Any]] = []
    if evidence_catalog_available:
        for entry in _iter_claim_entries(model_json):
            evidence_ids = entry["evidence_ids"]
            if not evidence_ids:
                continue
            if any(fid in evidence_catalog_ids for fid in evidence_ids):
                claims_with_resolved_evidence += 1
            else:
                claims_with_unresolved_evidence += 1
                if len(unresolved_evidence_examples) < 5:
                    unresolved_evidence_examples.append(
                        {
                            "section": entry["section"],
                            "order": entry["order"],
                            "text": entry["text"],
                            "evidence_ids": evidence_ids[:8],
                        }
                    )
    claims_with_any_evidence = max(0, int(claims_count) - int(claims_without_evidence))
    claim_explain_success_count = (
        claims_with_resolved_evidence if evidence_catalog_available else claims_with_any_evidence
    )
    claim_explain_success_rate = round(claim_explain_success_count / max(1, int(claims_count)), 3)

    def _section_as_list(key: str) -> List[Any]:
        raw = model_json.get(key)
        if isinstance(raw, list):
            return raw
        if raw is None:
            return []
        return [raw]

    def _meaningful_count(items: List[Any], *, text_keys: tuple[str, ...] = ("text", "name")) -> int:
        count = 0
        for item in items:
            if isinstance(item, dict):
                text = ""
                for tk in text_keys:
                    candidate = str(item.get(tk) or "").strip()
                    if candidate:
                        text = candidate
                        break
                if text:
                    count += 1
                continue
            if isinstance(item, str) and item.strip():
                count += 1
        return count

    propositions_items = (
        theory.propositions
        if isinstance(theory.propositions, list)
        else _section_as_list("propositions")
    )
    consequences_items = _section_as_list("consequences")
    context_items = _section_as_list("context")
    intervening_items = _section_as_list("intervening_conditions")

    propositions_count = _meaningful_count(propositions_items, text_keys=("text", "name", "proposition"))
    consequences_count = _meaningful_count(consequences_items, text_keys=("name", "text", "description"))
    context_count = _meaningful_count(context_items, text_keys=("name", "text", "description"))
    intervening_count = _meaningful_count(intervening_items, text_keys=("name", "text", "description"))

    consequences_types_present: Set[str] = set()
    consequences_horizons_present: Set[str] = set()
    for item in consequences_items:
        if not isinstance(item, dict):
            continue
        ctype = str(item.get("type") or "").strip().lower()
        if ctype:
            consequences_types_present.add(ctype)
        horizon = str(item.get("horizon") or "").strip().lower()
        if horizon:
            consequences_horizons_present.add(horizon)

    blocked_reasons: List[Dict[str, str]] = []
    if claims_count <= 0:
        blocked_reasons.append(
            {
                "code": "NO_CLAIMS",
                "message": "No hay claims trazables para decision/export.",
            }
        )
    if claims_without_evidence > 0:
        blocked_reasons.append(
            {
                "code": "CLAIMS_WITHOUT_EVIDENCE",
                "message": "Existen claims sin evidencia trazable.",
            }
        )
    if claims_with_unresolved_evidence > 0:
        blocked_reasons.append(
            {
                "code": "UNRESOLVED_EVIDENCE_REFERENCES",
                "message": (
                    f"Existen {claims_with_unresolved_evidence} claims cuyas referencias de evidencia "
                    "no se pueden resolver en el catalogo auditable."
                ),
            }
        )
    if claims_count > 0 and claims_without_evidence == 0 and not evidence_catalog_available:
        blocked_reasons.append(
            {
                "code": "EVIDENCE_INDEX_MISSING",
                "message": (
                    "No existe catalogo de evidencia auditable (evidence_index/evidence_ids) para verificar "
                    "las referencias de los claims."
                ),
            }
        )
    if claims_count > 0 and claims_count < int(policy["min_claims"]):
        blocked_reasons.append(
            {
                "code": "TEMPLATE_MIN_CLAIMS",
                "message": (
                    f"La plantilla `{policy['template_key']}` requiere al menos {policy['min_claims']} claims "
                    f"(actual: {claims_count})."
                ),
            }
        )
    if isinstance(interviews_covered, int) and interviews_covered < int(policy["min_interviews"]):
        blocked_reasons.append(
            {
                "code": "TEMPLATE_MIN_INTERVIEWS",
                "message": (
                    f"La plantilla `{policy['template_key']}` requiere al menos {policy['min_interviews']} entrevistas "
                    f"con evidencia (actual: {interviews_covered})."
                ),
            }
        )
    if judge_warn_only is True and not bool(policy["allow_warn_only"]):
        blocked_reasons.append(
            {
                "code": "TEMPLATE_WARN_ONLY_NOT_ALLOWED",
                "message": (
                    f"La plantilla `{policy['template_key']}` no permite exportar corridas en modo warn-only."
                ),
            }
        )
    if propositions_count < int(policy["min_propositions"]):
        blocked_reasons.append(
            {
                "code": "TEMPLATE_MIN_PROPOSITIONS",
                "message": (
                    f"La plantilla `{policy['template_key']}` requiere al menos {policy['min_propositions']} proposiciones "
                    f"(actual: {propositions_count})."
                ),
            }
        )
    if consequences_count < int(policy["min_consequences"]):
        blocked_reasons.append(
            {
                "code": "TEMPLATE_MIN_CONSEQUENCES",
                "message": (
                    f"La plantilla `{policy['template_key']}` requiere al menos {policy['min_consequences']} consecuencias "
                    f"(actual: {consequences_count})."
                ),
            }
        )
    if bool(policy["require_context_or_intervening"]) and (context_count + intervening_count) <= 0:
        blocked_reasons.append(
            {
                "code": "TEMPLATE_CONTEXT_REQUIRED",
                "message": (
                    f"La plantilla `{policy['template_key']}` requiere contexto o condiciones intervinientes no vacias."
                ),
            }
        )
    if bool(policy["require_consequence_balance"]) and consequences_count > 0:
        required_types = {"material", "social", "institutional"}
        required_horizons = {"corto_plazo", "largo_plazo"}
        if (not required_types.issubset(consequences_types_present)) or (
            not required_horizons.issubset(consequences_horizons_present)
        ):
            blocked_reasons.append(
                {
                    "code": "TEMPLATE_CONSEQUENCE_BALANCE",
                    "message": (
                        f"La plantilla `{policy['template_key']}` requiere consecuencias balanceadas "
                        f"(tipos material/social/institutional y horizontes corto/largo plazo)."
                    ),
                }
            )
    blocked = len(blocked_reasons) > 0
    return {
        "claims_count": int(claims_count),
        "claims_without_evidence": int(claims_without_evidence),
        "claims_with_any_evidence": int(claims_with_any_evidence),
        "claims_with_resolved_evidence": int(claims_with_resolved_evidence),
        "claims_with_unresolved_evidence": int(claims_with_unresolved_evidence),
        "claim_explain_success_count": int(claim_explain_success_count),
        "claim_explain_success_rate": float(claim_explain_success_rate),
        "evidence_catalog_available": bool(evidence_catalog_available),
        "evidence_catalog_size": len(evidence_catalog_ids),
        "unresolved_evidence_examples": unresolved_evidence_examples,
        "interviews_covered": interviews_covered,
        "judge_warn_only": judge_warn_only,
        "propositions_count": int(propositions_count),
        "consequences_count": int(consequences_count),
        "context_count": int(context_count),
        "intervening_conditions_count": int(intervening_count),
        "consequences_types_present": sorted(consequences_types_present),
        "consequences_horizons_present": sorted(consequences_horizons_present),
        "template_policy": policy,
        "blocked": bool(blocked),
        "blocked_reasons": blocked_reasons,
    }


def _build_export_privacy_gate(theory: Theory) -> Dict[str, Any]:
    model_json = theory.model_json if isinstance(theory.model_json, dict) else {}
    validation = theory.validation if isinstance(theory.validation, dict) else {}
    network_metrics_summary = validation.get("network_metrics_summary")
    evidence_index = (
        network_metrics_summary.get("evidence_index", [])
        if isinstance(network_metrics_summary, dict)
        else []
    )
    if not isinstance(evidence_index, list):
        evidence_index = []

    candidates: List[Dict[str, str]] = []

    def _append_candidate(label: str, raw_text: Any) -> None:
        text = str(raw_text).strip() if raw_text is not None else ""
        if not text:
            return
        candidates.append({"label": label, "text": text})

    for section in _CLAIM_SECTIONS:
        raw_items = model_json.get(section) or []
        if not isinstance(raw_items, list):
            raw_items = [raw_items]
        for idx, item in enumerate(raw_items):
            if isinstance(item, dict):
                _append_candidate(f"model_json.{section}[{idx}].text", item.get("text"))
                _append_candidate(f"model_json.{section}[{idx}].name", item.get("name"))
                _append_candidate(f"model_json.{section}[{idx}].description", item.get("description"))
            elif isinstance(item, (str, int, float)):
                _append_candidate(f"model_json.{section}[{idx}]", item)

    propositions = theory.propositions if isinstance(theory.propositions, list) else []
    for idx, p in enumerate(propositions):
        if isinstance(p, dict):
            _append_candidate(f"propositions[{idx}].text", p.get("text"))
        elif isinstance(p, (str, int, float)):
            _append_candidate(f"propositions[{idx}]", p)

    for idx, ev in enumerate(evidence_index[:300]):
        if not isinstance(ev, dict):
            continue
        _append_candidate(f"validation.evidence_index[{idx}].text", ev.get("text"))

    type_counts: Dict[str, int] = {"email": 0, "phone": 0, "rut": 0, "id": 0}
    issues: List[Dict[str, Any]] = []
    for c in candidates:
        types = detect_pii_types(c["text"])
        if not types:
            continue
        for t in types:
            type_counts[t] = type_counts.get(t, 0) + 1
        issues.append(
            {
                "label": c["label"],
                "types": types,
                "preview": redact_pii_text(c["text"])[:220],
            }
        )
        if len(issues) >= 20:
            break

    blocked = len(issues) > 0
    return {
        "blocked": bool(blocked),
        "issues_count": len(issues),
        "candidate_count": len(candidates),
        "type_counts": type_counts,
        "issues": issues,
    }


def _build_export_readiness(theory: Theory, template_key: str = "generic") -> Dict[str, Any]:
    quality_gate = _build_export_quality_gate(theory, template_key=template_key)
    privacy_gate = _build_export_privacy_gate(theory)
    blockers: List[Dict[str, Any]] = []
    if quality_gate.get("blocked"):
        claims_count = int(quality_gate.get("claims_count") or 0)
        claims_without_evidence = int(quality_gate.get("claims_without_evidence") or 0)
        blocked_reasons = quality_gate.get("blocked_reasons") or []
        if claims_count <= 0:
            quality_message = "No hay claims trazables para exportar."
        elif claims_without_evidence > 0:
            quality_message = "Existen claims sin evidencia trazable."
        elif blocked_reasons and isinstance(blocked_reasons, list):
            first_reason = blocked_reasons[0] if blocked_reasons else {}
            quality_message = str(first_reason.get("message") or "La teoria no cumple el gate de calidad de export.")
        else:
            quality_message = "La teoria no cumple el gate de calidad de export."
        blockers.append(
            {
                "code": "EXPORT_QUALITY_GATE_FAILED",
                "message": quality_message,
            }
        )
    if privacy_gate.get("blocked"):
        blockers.append(
            {
                "code": "EXPORT_PRIVACY_GATE_FAILED",
                "message": "Se detecto informacion sensible sin anonimizar.",
            }
        )
    return {
        "exportable": len(blockers) == 0,
        "blockers": blockers,
        "quality_gate": quality_gate,
        "privacy_gate": privacy_gate,
    }


async def _set_task_state(
    task_id: str,
    *,
    status_value: Optional[str] = None,
    step: Optional[str] = None,
    progress: Optional[int] = None,
    error: Optional[str] = None,
    error_code: Optional[str] = None,
    result: Any = None,
) -> None:
    task = _theory_tasks.get(task_id)
    if not task:
        return
    if status_value is not None:
        task["status"] = status_value
    if step is not None:
        task["step"] = step
    if progress is not None:
        task["progress"] = max(0, min(100, int(progress)))
    if error is not None:
        task["error"] = error
    if error_code is not None:
        task["error_code"] = error_code
    if result is not None:
        task["result"] = result
    task["next_poll_seconds"] = max(2, settings.THEORY_STATUS_POLL_HINT_SECONDS)
    task["updated_at"] = datetime.utcnow().isoformat()
    await _persist_task(task_id)


async def _acquire_project_lock(project_id: UUID, task_id: str) -> Optional[str]:
    """Return None when acquired; otherwise return existing task_id."""
    redis = await _get_redis()
    if not redis:
        return None
    lock_key = f"{_LOCK_PREFIX}{project_id}"
    ttl = max(60, settings.THEORY_TASK_LOCK_TTL_SECONDS)
    try:
        acquired = await redis.set(lock_key, task_id, ex=ttl, nx=True)
        if acquired:
            return None
        return await redis.get(lock_key)
    except Exception as e:
        logger.warning("Redis lock acquire failed for project %s: %s", project_id, e)
        return None


async def _refresh_project_lock(project_id: UUID, task_id: str) -> None:
    redis = await _get_redis()
    if not redis:
        return
    lock_key = f"{_LOCK_PREFIX}{project_id}"
    ttl = max(60, settings.THEORY_TASK_LOCK_TTL_SECONDS)
    try:
        current = await redis.get(lock_key)
        if current == task_id:
            await redis.expire(lock_key, ttl)
    except Exception as e:
        logger.warning("Redis lock refresh failed for project %s: %s", project_id, e)


async def _release_project_lock(project_id: UUID, task_id: str) -> None:
    redis = await _get_redis()
    if not redis:
        return
    lock_key = f"{_LOCK_PREFIX}{project_id}"
    try:
        current = await redis.get(lock_key)
        if current == task_id:
            await redis.delete(lock_key)
    except Exception as e:
        logger.warning("Redis lock release failed for project %s: %s", project_id, e)


async def _mark_step(task_id: str, step: str, progress: int) -> None:
    await _set_task_state(task_id, step=step, progress=progress)


async def _run_theory_pipeline(task_id: str, project_id: UUID, user_uuid: UUID, request: TheoryGenerateRequest):
    wall_start = time.perf_counter()
    logger.info("[theory] task %s STARTED for project %s", task_id, project_id)
    await _set_task_state(task_id, status_value="running", step="pipeline_start", progress=2)
    try:
        async with _local_pipeline_semaphore:
            session_local = get_session_local()
            async with session_local() as db:
                await _theory_pipeline(task_id, project_id, user_uuid, request, db)
    except asyncio.CancelledError:
        # Best-effort: mark canceled. If cancellation happens during an uninterruptible I/O,
        # this might be delayed until the next await completes.
        logger.warning("[theory] task %s CANCELLED by user", task_id)
        await _set_task_state(
            task_id,
            status_value="failed",
            step="canceled",
            progress=100,
            error="Canceled by user",
            error_code="CANCELED",
        )
        raise
    except (MultipleResultsFound, JSONDecodeError) as e:
        logger.exception("[theory] task %s failed with known data error", task_id)
        await _set_task_state(
            task_id,
            status_value="failed",
            step="failed",
            progress=100,
            error=str(e),
            error_code="DATA_CONSISTENCY_ERROR",
        )
    except Exception as e:
        logger.exception("[theory] task %s CRASHED: %s", task_id, e)
        await _set_task_state(
            task_id,
            status_value="failed",
            step="failed",
            progress=100,
            error=str(e),
            error_code="PIPELINE_ERROR",
        )
    finally:
        await _release_project_lock(project_id, task_id)
        elapsed = time.perf_counter() - wall_start
        logger.info(
            "[theory] task %s FINISHED status=%s total_elapsed=%.1fs",
            task_id,
            _theory_tasks.get(task_id, {}).get("status"),
            elapsed,
        )


@router.post("/{project_id}/generate-theory", status_code=202)
async def generate_theory(
    project_id: UUID,
    request: TheoryGenerateRequest,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project_result = await db.execute(
        select(Project).where(Project.id == project_id, Project.owner_id == user.user_uuid)
    )
    project = project_result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    task_id = str(uuid.uuid4())
    existing_task_id = await _acquire_project_lock(project_id, task_id)
    if existing_task_id and existing_task_id != task_id:
        existing_task = _theory_tasks.get(existing_task_id) or await _restore_task(existing_task_id)
        if existing_task and existing_task.get("owner_id") == str(user.user_uuid):
            return {
                "task_id": existing_task_id,
                "status": existing_task.get("status", "running"),
                "reused": True,
                "next_poll_seconds": settings.THEORY_STATUS_POLL_HINT_SECONDS,
                "execution_mode": existing_task.get("execution_mode", "local"),
            }
        if not existing_task:
            # Stale lock without task payload: clear and retry once.
            await _release_project_lock(project_id, existing_task_id)
            retry_existing = await _acquire_project_lock(project_id, task_id)
            if retry_existing in (None, task_id):
                existing_task_id = None
            else:
                existing_task = _theory_tasks.get(retry_existing) or await _restore_task(retry_existing)
                if existing_task and existing_task.get("owner_id") == str(user.user_uuid):
                    return {
                        "task_id": retry_existing,
                        "status": existing_task.get("status", "running"),
                        "reused": True,
                        "next_poll_seconds": settings.THEORY_STATUS_POLL_HINT_SECONDS,
                        "execution_mode": existing_task.get("execution_mode", "local"),
                    }
        raise HTTPException(
            status_code=409,
            detail="A theory generation task is already running for this project.",
        )

    _theory_tasks[task_id] = _new_task_payload(task_id, project_id, user.user_uuid)
    _theory_tasks[task_id]["execution_mode"] = "celery" if _use_celery_mode() else "local"
    await _persist_task(task_id)
    try:
        if _use_celery_mode():
            from ..tasks.theory_tasks import run_theory_pipeline_task

            celery_task = run_theory_pipeline_task.delay(
                task_id=task_id,
                project_id=str(project_id),
                user_uuid=str(user.user_uuid),
                request_payload=request.model_dump(),
            )
            _theory_tasks[task_id]["worker_task_id"] = celery_task.id
            await _persist_task(task_id)
            logger.info(
                "[theory] enqueued task %s for project %s via celery worker_task_id=%s",
                task_id,
                project_id,
                celery_task.id,
            )
        else:
            bg_task = asyncio.create_task(_run_theory_pipeline(task_id, project_id, user.user_uuid, request))
            _background_tasks.add(bg_task)
            _background_tasks_by_id[task_id] = bg_task
            bg_task.add_done_callback(_background_tasks.discard)
            bg_task.add_done_callback(lambda _t: _background_tasks_by_id.pop(task_id, None))
            logger.info("[theory] enqueued task %s for project %s in local mode", task_id, project_id)
    except Exception as e:
        await _release_project_lock(project_id, task_id)
        await _set_task_state(
            task_id,
            status_value="failed",
            step="enqueue",
            progress=100,
            error=f"Failed to enqueue theory task: {e}",
            error_code="ENQUEUE_ERROR",
        )
        raise HTTPException(status_code=500, detail="Failed to enqueue theory task")
    return {
        "task_id": task_id,
        "status": "pending",
        "next_poll_seconds": settings.THEORY_STATUS_POLL_HINT_SECONDS,
        "execution_mode": _theory_tasks[task_id]["execution_mode"],
    }


@router.post("/{project_id}/generate-theory/cancel/{task_id}")
async def cancel_theory_task(
    project_id: UUID,
    task_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    task = _theory_tasks.get(task_id) or await _restore_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.get("project_id") != str(project_id) or task.get("owner_id") != str(user.user_uuid):
        raise HTTPException(status_code=404, detail="Task not found")

    if task.get("status") in ("completed", "failed"):
        return task

    # Local-mode: cancel coroutine if still tracked.
    bg = _background_tasks_by_id.get(task_id)
    if bg and not bg.done():
        bg.cancel()

    # Celery-mode: best-effort revoke (does not guarantee termination of a running task).
    worker_task_id = task.get("worker_task_id")
    if worker_task_id:
        try:
            from ..tasks.celery_app import celery_app

            celery_app.control.revoke(worker_task_id, terminate=False)
        except Exception:
            pass

    await _set_task_state(
        task_id,
        status_value="failed",
        step="canceled",
        progress=100,
        error="Canceled by user",
        error_code="CANCELED",
    )
    await _release_project_lock(project_id, task_id)
    return _theory_tasks.get(task_id) or task


@router.get("/{project_id}/generate-theory/status/{task_id}")
async def get_theory_task_status(
    project_id: UUID,
    task_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    task = _theory_tasks.get(task_id) or await _restore_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.get("project_id") != str(project_id) or task.get("owner_id") != str(user.user_uuid):
        raise HTTPException(status_code=404, detail="Task not found")
    task["next_poll_seconds"] = max(2, settings.THEORY_STATUS_POLL_HINT_SECONDS)
    return task


async def _theory_pipeline(
    task_id: str,
    project_id: UUID,
    user_uuid: UUID,
    request: TheoryGenerateRequest,
    db: AsyncSession,
):
    started = time.perf_counter()
    try:
        result_payload = await theory_pipeline.run(
            task_id=task_id,
            project_id=project_id,
            user_uuid=user_uuid,
            request=request,
            db=db,
            mark_step=lambda step, progress: _mark_step(task_id, step, progress),
            refresh_lock=lambda: _refresh_project_lock(project_id, task_id),
        )
        await _set_task_state(
            task_id,
            status_value="completed",
            step="completed",
            progress=100,
            result=result_payload,
        )
        await _refresh_project_lock(project_id, task_id)
        logger.info("[theory][%s] completed in %.1fs", task_id, time.perf_counter() - started)
    except TheoryPipelineError as e:
        await db.rollback()
        await _set_task_state(
            task_id,
            status_value="failed",
            step="failed",
            progress=100,
            error=e.message,
            error_code=e.code,
        )
    except Exception as e:
        await db.rollback()
        await _set_task_state(
            task_id,
            status_value="failed",
            step="failed",
            progress=100,
            error=f"Theory generation failed: {str(e)}",
            error_code="PIPELINE_ERROR",
        )

@router.get("/{project_id}/theories", response_model=List[TheoryResponse])
async def list_theories(
    project_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project_result = await db.execute(
        select(Project).where(Project.id == project_id, Project.owner_id == user.user_uuid)
    )
    if not project_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Project not found")

    result = await db.execute(
        select(Theory)
        .filter(Theory.project_id == project_id)
        .order_by(Theory.created_at.desc())
    )
    return result.scalars().all()


@router.get(
    "/{project_id}/theories/judge-rollout",
    response_model=TheoryJudgeRolloutResponse,
)
async def get_theory_judge_rollout(
    project_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project_result = await db.execute(
        select(Project).where(Project.id == project_id, Project.owner_id == user.user_uuid)
    )
    if not project_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Project not found")

    policy = await theory_pipeline.get_judge_rollout_policy(project_id=project_id, db=db)

    latest_theory = (
        await db.execute(
            select(Theory)
            .where(Theory.project_id == project_id)
            .order_by(Theory.created_at.desc())
            .limit(1)
        )
    ).scalars().first()

    latest_validation: Dict[str, Any] = {}
    latest_theory_id: Optional[UUID] = None
    latest_created_at: Optional[datetime] = None
    if latest_theory:
        latest_theory_id = latest_theory.id
        latest_created_at = latest_theory.created_at
        validation = latest_theory.validation or {}
        if isinstance(validation, dict):
            latest_validation = {
                "judge": validation.get("judge", {}),
                "judge_rollout": validation.get("judge_rollout", {}),
                "claim_metrics": validation.get("claim_metrics", {}),
                "quality_metrics": validation.get("quality_metrics", {}),
                "neo4j_claim_sync": validation.get("neo4j_claim_sync", {}),
                "qdrant_claim_sync": validation.get("qdrant_claim_sync", {}),
            }

    return {
        "project_id": project_id,
        "policy": policy,
        "latest_theory_id": latest_theory_id,
        "latest_created_at": latest_created_at,
        "latest_validation": latest_validation,
    }


def _percentile(values: List[float], q: float) -> float:
    clean = sorted(float(v) for v in values if v is not None)
    if not clean:
        return 0.0
    if len(clean) == 1:
        return round(clean[0], 2)
    q = max(0.0, min(100.0, float(q)))
    rank = int(round((q / 100.0) * (len(clean) - 1)))
    return round(clean[rank], 2)


@router.get(
    "/{project_id}/theories/pipeline-slo",
    response_model=TheoryPipelineSloResponse,
)
async def get_theory_pipeline_slo(
    project_id: UUID,
    window: int = Query(20, ge=5, le=200),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project_result = await db.execute(
        select(Project).where(Project.id == project_id, Project.owner_id == user.user_uuid)
    )
    if not project_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Project not found")

    rows = (
        await db.execute(
            select(Theory.id, Theory.created_at, Theory.validation)
            .where(Theory.project_id == project_id)
            .order_by(Theory.created_at.desc())
            .limit(window)
        )
    ).all()

    if not rows:
        return {
            "project_id": project_id,
            "window_size": int(window),
            "sample_size": 0,
            "latest_theory_id": None,
            "latest_created_at": None,
            "latency_p95_ms": {},
            "latency_p50_ms": {},
            "quality": {},
            "reliability": {},
        }

    latency_keys = [
        "category_summary_sync_ms",
        "neo4j_metrics_ms",
        "qdrant_retrieval_ms",
        "identify_llm_ms",
        "paradigm_llm_ms",
        "gaps_llm_ms",
    ]
    latency_values: Dict[str, List[float]] = {k: [] for k in latency_keys}

    warn_only_runs = 0
    fallback_network = 0
    fallback_evidence = 0
    neo4j_claim_sync_failed = 0
    qdrant_claim_sync_failed = 0
    claims_without_evidence_total = 0
    claim_explain_success_runs = 0
    claim_explain_success_rate_sum = 0.0
    claim_explain_metric_runs = 0

    for _theory_id, _created_at, validation in rows:
        if not isinstance(validation, dict):
            continue
        runtime = validation.get("pipeline_runtime") or {}
        latency = runtime.get("latency_ms") or {}
        for key in latency_keys:
            value = latency.get(key)
            if isinstance(value, (int, float)):
                latency_values[key].append(float(value))

        judge = validation.get("judge") or {}
        if bool(judge.get("warn_only")):
            warn_only_runs += 1

        routing = validation.get("deterministic_routing") or {}
        execution = routing.get("execution") or {}
        if str(execution.get("network_metrics_source") or "").strip().lower() == "sql_fallback":
            fallback_network += 1
        if str(execution.get("semantic_evidence_source") or "").strip().lower() == "sql_fallback":
            fallback_evidence += 1

        neo4j_claim_sync = validation.get("neo4j_claim_sync") or {}
        if bool(neo4j_claim_sync.get("neo4j_sync_failed")):
            neo4j_claim_sync_failed += 1
        qdrant_claim_sync = validation.get("qdrant_claim_sync") or {}
        if bool(qdrant_claim_sync.get("qdrant_sync_failed")):
            qdrant_claim_sync_failed += 1

        claim_metrics = validation.get("claim_metrics") or {}
        claims_without_evidence = int(claim_metrics.get("claims_without_evidence") or 0)
        claims_without_evidence_total += claims_without_evidence

        run_explain_rate: Optional[float] = None
        raw_explain_rate = claim_metrics.get("claim_explain_success_rate")
        if isinstance(raw_explain_rate, (int, float)):
            run_explain_rate = max(0.0, min(1.0, float(raw_explain_rate)))
        else:
            claims_count = claim_metrics.get("claims_count")
            if isinstance(claims_count, int) and claims_count > 0:
                run_explain_rate = max(
                    0.0,
                    min(1.0, float((claims_count - claims_without_evidence) / max(1, claims_count))),
                )
            elif "claims_without_evidence" in claim_metrics:
                run_explain_rate = 1.0 if claims_without_evidence == 0 else 0.0
        if run_explain_rate is not None:
            claim_explain_metric_runs += 1
            claim_explain_success_rate_sum += run_explain_rate
            if run_explain_rate >= 0.999:
                claim_explain_success_runs += 1

    sample_size = len(rows)
    latency_p95 = {k: _percentile(v, 95) for k, v in latency_values.items() if v}
    latency_p50 = {k: _percentile(v, 50) for k, v in latency_values.items() if v}

    latest_theory_id, latest_created_at, _ = rows[0]

    return {
        "project_id": project_id,
        "window_size": int(window),
        "sample_size": sample_size,
        "latest_theory_id": latest_theory_id,
        "latest_created_at": latest_created_at,
        "latency_p95_ms": latency_p95,
        "latency_p50_ms": latency_p50,
        "quality": {
            "claims_without_evidence_total": int(claims_without_evidence_total),
            "claims_without_evidence_rate": round(claims_without_evidence_total / max(1, sample_size), 3),
            "claim_explain_success_runs": int(claim_explain_success_runs),
            "claim_explain_metric_runs": int(claim_explain_metric_runs),
            "claim_explain_success_rate": round(
                claim_explain_success_rate_sum / max(1, claim_explain_metric_runs),
                3,
            ),
            "judge_warn_only_runs": int(warn_only_runs),
            "judge_warn_only_rate": round(warn_only_runs / max(1, sample_size), 3),
        },
        "reliability": {
            "network_sql_fallback_runs": int(fallback_network),
            "evidence_sql_fallback_runs": int(fallback_evidence),
            "network_sql_fallback_rate": round(fallback_network / max(1, sample_size), 3),
            "evidence_sql_fallback_rate": round(fallback_evidence / max(1, sample_size), 3),
            "neo4j_claim_sync_failed_runs": int(neo4j_claim_sync_failed),
            "qdrant_claim_sync_failed_runs": int(qdrant_claim_sync_failed),
        },
    }


def _build_claims_from_validation_fallback(theory: Theory) -> List[Dict[str, Any]]:
    model_json = theory.model_json if isinstance(theory.model_json, dict) else {}
    validation = theory.validation if isinstance(theory.validation, dict) else {}
    network_metrics_summary = validation.get("network_metrics_summary")
    evidence_index = (
        network_metrics_summary.get("evidence_index", [])
        if isinstance(network_metrics_summary, dict)
        else []
    )
    if not isinstance(evidence_index, list):
        evidence_index = []

    def _as_claim_text(value: Any) -> str:
        if isinstance(value, dict):
            return str(
                value.get("text")
                or value.get("name")
                or value.get("description")
                or value.get("definition")
                or ""
            ).strip()
        if isinstance(value, (str, int, float)):
            return str(value).strip()
        return ""

    def _as_evidence_ids(entry: Any) -> List[str]:
        if isinstance(entry, dict):
            raw_ids = entry.get("evidence_ids")
            if isinstance(raw_ids, list):
                return [str(fid).strip() for fid in raw_ids if str(fid).strip()]
            raw_single = entry.get("evidence_id")
            if raw_single is not None and str(raw_single).strip():
                return [str(raw_single).strip()]
        return []

    def _as_counter_evidence_ids(entry: Any) -> List[str]:
        if not isinstance(entry, dict):
            return []
        for key in ("counter_evidence_ids", "contradicted_by_ids", "contrast_evidence_ids"):
            raw = entry.get(key)
            if isinstance(raw, list):
                values = [str(fid).strip() for fid in raw if str(fid).strip()]
                if values:
                    return values
        return []

    evidence_map = {}
    for ev in evidence_index or []:
        if not isinstance(ev, dict):
            continue
        fid = str(ev.get("fragment_id") or ev.get("id") or "").strip()
        if not fid:
            continue
        evidence_map[fid] = {
            "fragment_id": fid,
            "score": ev.get("score"),
            "rank": None,
            "text": ev.get("text"),
            "interview_id": ev.get("interview_id"),
        }

    section_to_type = {
        "conditions": "condition",
        "context": "condition",
        "intervening_conditions": "condition",
        "actions": "action",
        "consequences": "consequence",
        "propositions": "proposition",
    }
    items: List[Dict[str, Any]] = []
    for section, claim_type in section_to_type.items():
        raw = model_json.get(section) or []
        if not isinstance(raw, list):
            raw = [raw]
        for idx, entry in enumerate(raw):
            text = _as_claim_text(entry)
            if not text:
                continue
            evidence = []
            for rank, fid in enumerate(_as_evidence_ids(entry)):
                fragment_id = str(fid).strip()
                if not fragment_id:
                    continue
                base = evidence_map.get(
                    fragment_id,
                    {
                        "fragment_id": fragment_id,
                        "score": None,
                        "rank": None,
                        "text": None,
                        "interview_id": None,
                    },
                )
                evidence.append({**base, "rank": rank})

            counter_evidence = []
            for rank, fid in enumerate(_as_counter_evidence_ids(entry)):
                fragment_id = str(fid).strip()
                if not fragment_id:
                    continue
                base = evidence_map.get(
                    fragment_id,
                    {
                        "fragment_id": fragment_id,
                        "score": None,
                        "rank": None,
                        "text": None,
                        "interview_id": None,
                    },
                )
                counter_evidence.append({**base, "rank": rank})

            category_name = str(entry.get("name") or "").strip() if isinstance(entry, dict) else ""
            categories = [{"id": None, "name": category_name}] if category_name and section != "propositions" else []
            path_examples = []
            for ev in evidence[:3]:
                fragment_id = ev.get("fragment_id")
                if categories:
                    path_examples.append(f"{categories[0].get('name')} -> {text} -> {fragment_id}")
                else:
                    path_examples.append(f"{text} -> {fragment_id}")
            for ev in counter_evidence[:2]:
                fragment_id = ev.get("fragment_id")
                if categories:
                    path_examples.append(f"{categories[0].get('name')} -> {text} -> [contra] {fragment_id}")
                else:
                    path_examples.append(f"{text} -> [contra] {fragment_id}")

            items.append(
                {
                    "claim_id": f"fallback:{theory.id}:{section}:{idx}",
                    "claim_type": claim_type,
                    "section": section,
                    "order": idx,
                    "text": text,
                    "categories": categories,
                    "evidence": evidence,
                    "counter_evidence": counter_evidence,
                    "path_examples": path_examples,
                }
            )
    return items


@router.get(
    "/{project_id}/theories/{theory_id}/claims/explain",
    response_model=TheoryClaimsExplainResponse,
)
async def explain_theory_claims(
    project_id: UUID,
    theory_id: UUID,
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0, le=5000),
    section: Optional[str] = Query(None, pattern="^(conditions|context|intervening_conditions|actions|consequences|propositions)$"),
    claim_type: Optional[str] = Query(None, pattern="^(condition|action|consequence|proposition|gap)$"),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Theory, Project)
        .join(Project, Theory.project_id == Project.id)
        .where(
            Theory.id == theory_id,
            Theory.project_id == project_id,
            Project.owner_id == user.user_uuid,
        )
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Theory or Project not found")
    theory, _project = row

    source = "validation_fallback"
    all_claims = _build_claims_from_validation_fallback(theory)
    if section:
        all_claims = [claim for claim in all_claims if str(claim.get("section") or "") == section]
    if claim_type:
        all_claims = [claim for claim in all_claims if str(claim.get("claim_type") or "") == claim_type]
    total = len(all_claims)
    claims = all_claims[offset : offset + limit]

    try:
        neo_claims = await neo4j_service.get_theory_claims_explain(
            project_id=project_id,
            theory_id=theory_id,
            owner_id=user.user_uuid,
            limit=limit,
            offset=offset,
            section=section,
            claim_type=claim_type,
        )
    except Exception as e:
        logger.warning(
            "Neo4j explain failed project_id=%s theory_id=%s: %s",
            project_id,
            theory_id,
            str(e)[:300],
        )
        neo_claims = {"total": 0, "claims": []}

    if isinstance(neo_claims, dict):
        neo_claims_rows = neo_claims.get("claims") or []
        neo_total = int(neo_claims.get("total") or 0)
    else:
        neo_claims_rows = neo_claims or []
        neo_total = len(neo_claims_rows)

    if neo_claims_rows:
        source = "neo4j"
        total = neo_total
        claims = []
        for claim in neo_claims_rows:
            categories = [
                {"id": str(cat.get("id") or ""), "name": str(cat.get("name") or "")}
                for cat in (claim.get("categories") or [])
                if isinstance(cat, dict)
            ]
            evidence = [
                {
                    "fragment_id": str(ev.get("fragment_id") or ""),
                    "score": ev.get("score"),
                    "rank": ev.get("rank"),
                    "text": ev.get("text"),
                    "interview_id": None,
                }
                for ev in (claim.get("evidence") or [])
                if isinstance(ev, dict) and str(ev.get("fragment_id") or "").strip()
            ]
            counter_evidence = [
                {
                    "fragment_id": str(ev.get("fragment_id") or ""),
                    "score": ev.get("score"),
                    "rank": ev.get("rank"),
                    "text": ev.get("text"),
                    "interview_id": None,
                }
                for ev in (claim.get("counter_evidence") or [])
                if isinstance(ev, dict) and str(ev.get("fragment_id") or "").strip()
            ]
            path_examples = []
            for ev in evidence[:3]:
                if categories:
                    path_examples.append(
                        f"{categories[0].get('name') or 'Category'} -> {claim.get('text') or ''} -> {ev.get('fragment_id')}"
                    )
                else:
                    path_examples.append(f"{claim.get('text') or ''} -> {ev.get('fragment_id')}")
            for ev in counter_evidence[:2]:
                if categories:
                    path_examples.append(
                        f"{categories[0].get('name') or 'Category'} -> {claim.get('text') or ''} -> [contra] {ev.get('fragment_id')}"
                    )
                else:
                    path_examples.append(f"{claim.get('text') or ''} -> [contra] {ev.get('fragment_id')}")

            claims.append(
                {
                    "claim_id": str(claim.get("claim_id") or ""),
                    "claim_type": str(claim.get("claim_type") or ""),
                    "section": str(claim.get("section") or ""),
                    "order": int(claim.get("order") or 0),
                    "text": str(claim.get("text") or ""),
                    "categories": categories,
                    "evidence": evidence,
                    "counter_evidence": counter_evidence,
                    "path_examples": path_examples,
                }
            )

    return {
        "project_id": project_id,
        "theory_id": theory_id,
        "source": source,
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": (offset + len(claims)) < total,
        "section_filter": section,
        "claim_type_filter": claim_type,
        "claim_count": len(claims),
        "claims": claims,
    }


@router.get(
    "/{project_id}/theories/{theory_id}/export/readiness",
    response_model=TheoryExportReadinessResponse,
)
async def get_export_readiness(
    project_id: UUID,
    theory_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Theory, Project)
        .join(Project, Theory.project_id == Project.id)
        .where(
            Theory.id == theory_id,
            Theory.project_id == project_id,
            Project.owner_id == user.user_uuid,
        )
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Theory or Project not found")

    theory, project = row
    readiness = _build_export_readiness(
        theory,
        template_key=_normalize_template_key(getattr(project, "domain_template", "generic")),
    )
    return {
        "project_id": project_id,
        "theory_id": theory_id,
        **readiness,
    }


@router.post("/{project_id}/theories/{theory_id}/export")
async def export_theory_report(
    project_id: UUID,
    theory_id: UUID,
    format: str = Query("pdf", pattern="^(pdf|pptx|xlsx|png)$"),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Theory, Project)
        .join(Project, Theory.project_id == Project.id)
        .where(
            Theory.id == theory_id,
            Theory.project_id == project_id,
            Project.owner_id == user.user_uuid,
        )
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Theory or Project not found")

    theory, project = row

    readiness = _build_export_readiness(
        theory,
        template_key=_normalize_template_key(getattr(project, "domain_template", "generic")),
    )
    quality_gate = readiness.get("quality_gate") or {}
    if quality_gate["blocked"]:
        claims_count = int(quality_gate.get("claims_count") or 0)
        claims_without_evidence = int(quality_gate.get("claims_without_evidence") or 0)
        blocked_reasons = quality_gate.get("blocked_reasons") or []
        if claims_count <= 0:
            quality_message = "No se puede exportar: no hay claims trazables para decision."
            remediation = [
                "Revisa la corrida y confirma que se generaron claims en condiciones/acciones/consecuencias/proposiciones.",
                "Completa codificacion/evidencia y reintenta la generacion de teoria.",
                "Valida readiness antes de exportar.",
            ]
        elif claims_without_evidence > 0:
            quality_message = "No se puede exportar: existen claims sin evidencia trazable."
            remediation = [
                "Revisa claims sin evidencia y completa `evidence_ids` por claim.",
                "Reprocesa teoria con judge en modo estricto.",
                "Valida readiness antes de exportar.",
            ]
        elif blocked_reasons and isinstance(blocked_reasons, list):
            first_reason = blocked_reasons[0] if blocked_reasons else {}
            quality_message = str(first_reason.get("message") or "No se puede exportar: la teoria no cumple el gate de calidad.")
            remediation = [
                "Aumenta cobertura de entrevistas y consistencia metodologica segun la plantilla del proyecto.",
                "Evita modo warn-only en corridas destinadas a export ejecutivo.",
                "Valida readiness antes de exportar.",
            ]
        else:
            quality_message = "No se puede exportar: la teoria no cumple el gate de calidad."
            remediation = ["Valida readiness y corrige brechas de calidad antes de exportar."]
        raise HTTPException(
            status_code=422,
            detail={
                "code": "EXPORT_QUALITY_GATE_FAILED",
                "message": quality_message,
                "remediation": remediation,
                "quality_gate": quality_gate,
            },
        )

    privacy_gate = readiness.get("privacy_gate") or {}
    if privacy_gate["blocked"]:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "EXPORT_PRIVACY_GATE_FAILED",
                "message": "No se puede exportar: se detecto informacion sensible sin anonimizar.",
                "remediation": [
                    "Seudonimiza nombres y elimina identificadores directos en entrevistas.",
                    "Reprocesa la teoria y valida evidencia por claim.",
                    "Reintenta exportar cuando el gate de privacidad quede en limpio.",
                ],
                "privacy_gate": privacy_gate,
            },
        )

    try:
        theory_dict = {
            "version": theory.version,
            "confidence_score": theory.confidence_score,
            "generated_by": theory.generated_by,
            "model_json": theory.model_json,
            "propositions": theory.propositions,
            "gaps": theory.gaps,
            "validation": theory.validation,
        }

        report_buffer, extension, content_type = await export_service.generate_theory_report(
            project_name=project.name,
            language=project.language or "es",
            theory_data=theory_dict,
            format=format,
            template_key=getattr(project, "domain_template", "generic") or "generic",
        )

        blob_name = f"{project_id}/reports/Theory_{theory_id}_{uuid.uuid4().hex[:8]}.{extension}"

        await storage_service.upload_blob(
            container_key="exports",
            blob_name=blob_name,
            data=report_buffer.getvalue(),
            content_type=content_type,
        )

        download_url = await storage_service.generate_sas_url(
            container_key="exports",
            blob_name=blob_name,
            expires_hours=1,
        )

        return {
            "download_url": download_url,
            "filename": f"TheoGen_{project.name.replace(' ', '_')}.{extension}",
            "expires_at_utc": "1h",
            "format": extension,
        }

    except Exception:
        logger.exception(
            "Failed to export report project_id=%s theory_id=%s format=%s",
            project_id,
            theory_id,
            format,
        )
        raise HTTPException(status_code=500, detail="Failed to generate or upload report")
