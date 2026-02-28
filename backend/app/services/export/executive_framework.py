from __future__ import annotations

from typing import Any, Dict, List


def _as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _extract_claim_metrics(theory_data: Dict[str, Any]) -> Dict[str, int]:
    validation = theory_data.get("validation") if isinstance(theory_data.get("validation"), dict) else {}
    claim_metrics = validation.get("claim_metrics") if isinstance(validation.get("claim_metrics"), dict) else {}
    model_json = theory_data.get("model_json") if isinstance(theory_data.get("model_json"), dict) else {}

    claims_count = claim_metrics.get("claims_count")
    claims_without_evidence = claim_metrics.get("claims_without_evidence")
    interviews_covered = claim_metrics.get("interviews_covered")

    if not isinstance(claims_count, int) or not isinstance(claims_without_evidence, int):
        total = 0
        missing = 0
        for section in ("conditions", "context", "intervening_conditions", "actions", "consequences", "propositions"):
            raw_items = model_json.get(section) or []
            if not isinstance(raw_items, list):
                continue
            for item in raw_items:
                if isinstance(item, dict):
                    text = str(item.get("text") or item.get("name") or "").strip()
                    if not text:
                        continue
                    total += 1
                    ev = item.get("evidence_ids")
                    valid_ev = [str(x).strip() for x in ev] if isinstance(ev, list) else []
                    if not valid_ev:
                        missing += 1
                    continue
                if isinstance(item, str) and item.strip():
                    total += 1
                    missing += 1
        if not isinstance(claims_count, int):
            claims_count = total
        if not isinstance(claims_without_evidence, int):
            claims_without_evidence = missing

    if not isinstance(interviews_covered, int):
        interviews_covered = 0

    return {
        "claims_count": int(claims_count or 0),
        "claims_without_evidence": int(claims_without_evidence or 0),
        "interviews_covered": int(interviews_covered or 0),
    }


def _extract_gap_metrics(theory_data: Dict[str, Any]) -> Dict[str, int]:
    gaps = _as_list(theory_data.get("gaps"))
    high = 0
    medium = 0
    for g in gaps:
        if not isinstance(g, dict):
            continue
        sev = str(g.get("severity") or "").strip().lower()
        if sev == "high":
            high += 1
        elif sev == "medium":
            medium += 1
    return {"gaps_count": len(gaps), "gaps_high": high, "gaps_medium": medium}


def build_executive_framework(theory_data: Dict[str, Any]) -> Dict[str, Any]:
    metrics = _extract_claim_metrics(theory_data)
    gap_metrics = _extract_gap_metrics(theory_data)
    validation = theory_data.get("validation") if isinstance(theory_data.get("validation"), dict) else {}
    judge = validation.get("judge") if isinstance(validation.get("judge"), dict) else {}
    warn_only = bool(judge.get("warn_only"))

    claims_count = metrics["claims_count"]
    claims_without_evidence = metrics["claims_without_evidence"]
    gaps_high = gap_metrics["gaps_high"]

    recommendation = "GO"
    if claims_count <= 0:
        recommendation = "NO_GO"
    elif claims_without_evidence > 0 and claims_without_evidence >= max(1, int(claims_count * 0.2)):
        recommendation = "NO_GO"
    elif warn_only or claims_without_evidence > 0 or gaps_high > 0:
        recommendation = "PILOT"

    reasons: List[str] = []
    if claims_count <= 0:
        reasons.append("No hay claims suficientes para una decision directiva.")
    if claims_without_evidence > 0:
        reasons.append(
            f"Existen {claims_without_evidence} claims sin evidencia trazable sobre {claims_count} claims totales."
        )
    if warn_only:
        reasons.append("La corrida se valido en modo warn-only.")
    if gaps_high > 0:
        reasons.append(f"Se detectaron {gaps_high} brechas criticas de severidad alta.")
    if not reasons:
        reasons.append("Calidad de evidencia y consistencia metodologica en umbral de decision.")

    gaps = _as_list(theory_data.get("gaps"))
    limitations: List[str] = []
    for gap in gaps[:4]:
        if isinstance(gap, dict):
            text = str(gap.get("gap_description") or gap.get("description") or "").strip()
            if text:
                limitations.append(text)
        elif isinstance(gap, str) and gap.strip():
            limitations.append(gap.strip())
    if not limitations:
        limitations.append("No se registraron limites explicitos en la corrida actual.")

    if recommendation == "GO":
        action_plan = [
            "Escalar implementacion en el frente priorizado con seguimiento quincenal.",
            "Asignar responsables por recomendacion y definir metas a 90 dias.",
            "Mantener auditoria de evidencia por claim en cada comite mensual.",
        ]
    elif recommendation == "PILOT":
        action_plan = [
            "Ejecutar piloto acotado con muestra de contraste y control de riesgos.",
            "Cerrar brechas de evidencia critica antes de escalar.",
            "Reevaluar decision en 2 a 4 semanas con KPI de trazabilidad.",
        ]
    else:
        action_plan = [
            "No escalar en el estado actual; priorizar cierre de brechas metodologicas.",
            "Reforzar captura de evidencia directa y casos desconfirmatorios.",
            "Reintentar decision cuando claims sin evidencia sean cero.",
        ]

    return {
        "recommendation": recommendation,
        "reasons": reasons,
        "action_plan": action_plan,
        "limitations": limitations,
        "quality_metrics": {
            **metrics,
            **gap_metrics,
            "judge_warn_only": warn_only,
        },
    }

