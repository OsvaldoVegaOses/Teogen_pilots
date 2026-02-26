from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Any, Dict, List


_PROHIBITED_META_TERMS = [
    "informante",
    "identificacion",
    "identificación",
    "entrevista",
    "solicitud de identificacion",
    "solicitud de identificación",
    "consentimiento",
    "diarizacion",
    "diarización",
    "transcripcion",
    "transcripción",
    "cuestionario",
]


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    if isinstance(value, list):
        return " ".join(_as_text(v) for v in value)
    if isinstance(value, dict):
        parts = []
        for k in ("name", "text", "description", "definition", "evidence"):
            if k in value and value[k] is not None:
                parts.append(str(value[k]))
        return " ".join(parts) if parts else str(value)
    return str(value)


def _contains_prohibited_terms(value: Any) -> bool:
    text = _as_text(value).lower()
    return any(term in text for term in _PROHIBITED_META_TERMS)


def _iter_section_items(paradigm: Dict[str, Any], key: str) -> List[dict]:
    value = paradigm.get(key) or []
    if not isinstance(value, list):
        return []
    return [v for v in value if isinstance(v, dict)]


@dataclass
class TheoryJudgeError(Exception):
    result: Dict[str, Any]

    def __str__(self) -> str:
        errors = self.result.get("errors") or []
        if not errors:
            return "TheoryJudgeError"
        codes = ", ".join(str(e.get("code")) for e in errors[:6])
        return f"TheoryJudgeError({codes})"


class TheoryJudge:
    """
    Deterministic validator for theory outputs.
    Designed to be strict but actionable: it returns structured error codes so the
    pipeline can trigger partial repairs.
    """

    def __init__(
        self,
        *,
        min_interviews: int = 4,
        max_share_per_interview: float = 0.4,
        adaptive_thresholds: bool = True,
        available_interviews: int = 0,
        min_interviews_floor: int = 1,
        min_interviews_ratio: float = 0.6,
        balance_min_evidence: int = 12,
    ) -> None:
        self.min_interviews = max(1, int(min_interviews))
        self.adaptive_thresholds = bool(adaptive_thresholds)
        self.available_interviews = max(0, int(available_interviews))
        self.min_interviews_floor = max(1, int(min_interviews_floor))
        self.min_interviews_ratio = max(0.1, min(1.0, float(min_interviews_ratio)))
        self.balance_min_evidence = max(1, int(balance_min_evidence))
        self.max_share_per_interview = float(max_share_per_interview)
        self.effective_min_interviews = self._resolve_effective_min_interviews()

    def _resolve_effective_min_interviews(self) -> int:
        if not self.adaptive_thresholds:
            return self.min_interviews
        if self.available_interviews <= 0:
            return self.min_interviews
        adaptive_target = max(
            self.min_interviews_floor,
            int(ceil(self.available_interviews * self.min_interviews_ratio)),
        )
        return max(1, min(self.min_interviews, adaptive_target, self.available_interviews))

    @staticmethod
    def _evidence_ids_for_section(paradigm: Dict[str, Any], key: str) -> List[str]:
        ids: List[str] = []
        for item in _iter_section_items(paradigm, key):
            ev = item.get("evidence_ids")
            if isinstance(ev, list):
                for fid in ev:
                    if fid is None:
                        continue
                    s = str(fid).strip()
                    if s:
                        ids.append(s)
        return ids

    @staticmethod
    def _has_missing_evidence_ids(paradigm: Dict[str, Any], key: str) -> bool:
        items = _iter_section_items(paradigm, key)
        if not items:
            return False
        for item in items:
            ev = item.get("evidence_ids")
            if not isinstance(ev, list) or len([x for x in ev if str(x).strip()]) == 0:
                return True
        return False

    def evaluate(
        self,
        *,
        paradigm: Dict[str, Any],
        fragment_to_interview: Dict[str, str],
        missing_evidence_ids: List[str],
        known_category_names: List[str] | None = None,
    ) -> Dict[str, Any]:
        errors: List[Dict[str, Any]] = []
        warnings: List[Dict[str, Any]] = []

        # KnownConstructs: keep construct vocabulary anchored to the category set when possible.
        if known_category_names:
            allowed = {str(n).strip().lower() for n in known_category_names if str(n).strip()}
            unknown: List[str] = []
            checked = 0
            for key in ("conditions", "actions", "context", "intervening_conditions"):
                for item in _iter_section_items(paradigm, key):
                    name = str(item.get("name") or "").strip().lower()
                    if not name:
                        continue
                    checked += 1
                    if name not in allowed:
                        unknown.append(name)
            if checked > 0 and (len(unknown) / checked) >= 0.4:
                errors.append(
                    {
                        "code": "UNKNOWN_CONSTRUCTS",
                        "message": "Demasiados constructos fuera del set de categorias permitido (amarrar por ontologia minima).",
                        "unknown_ratio": round(len(unknown) / checked, 3),
                        "unknown_sample": sorted(set(unknown))[:10],
                    }
                )

        # Global domain sanity (not just consequences).
        if _contains_prohibited_terms(paradigm):
            errors.append(
                {
                    "code": "DOMAIN_SANITY",
                    "message": "Se detectaron terminos meta-metodologicos prohibidos en la teoria.",
                }
            )

        # EvidenceRequired across core sections.
        if self._has_missing_evidence_ids(paradigm, "conditions") or self._has_missing_evidence_ids(paradigm, "actions"):
            errors.append(
                {
                    "code": "CONDITIONS_ACTIONS_INVALID",
                    "message": "Conditions/actions deben incluir evidence_ids no vacios por item.",
                }
            )
        if self._has_missing_evidence_ids(paradigm, "consequences"):
            errors.append(
                {
                    "code": "CONSEQUENCES_INVALID",
                    "message": "Consequences deben incluir evidence_ids no vacios por item.",
                }
            )
        # Balance consequences gate (material/social/institutional + corto/largo).
        consequences = _iter_section_items(paradigm, "consequences")
        if consequences:
            types_present = {
                str(c.get("type") or "").strip().lower()
                for c in consequences
                if str(c.get("type") or "").strip()
            }
            horizons_present = {
                str(c.get("horizon") or "").strip().lower()
                for c in consequences
                if str(c.get("horizon") or "").strip()
            }
            required_types = {"material", "social", "institutional"}
            required_horizons = {"corto_plazo", "largo_plazo"}
            used_ids_preview: List[str] = []
            for section_key in ("conditions", "actions", "consequences", "propositions", "context", "intervening_conditions"):
                used_ids_preview.extend(self._evidence_ids_for_section(paradigm, section_key))
            used_evidence_count_preview = len([s for s in used_ids_preview if s])
            balance_missing = (not required_types.issubset(types_present)) or (not required_horizons.issubset(horizons_present))
            if balance_missing:
                issue = {
                    "code": "BALANCE_CONSEQUENCES",
                    "message": "Consequences debe cubrir material/social/institutional y corto/largo plazo.",
                    "types_present": sorted(types_present),
                    "horizons_present": sorted(horizons_present),
                    "min_evidence_for_hard_gate": self.balance_min_evidence,
                    "used_evidence_count": used_evidence_count_preview,
                }
                if self.adaptive_thresholds and used_evidence_count_preview < self.balance_min_evidence:
                    issue["code"] = "BALANCE_CONSEQUENCES_WARN"
                    issue["message"] = (
                        "Balance de consecuencias incompleto, pero se degrada a warning por evidencia limitada del proyecto."
                    )
                    warnings.append(issue)
                else:
                    errors.append(issue)
        if self._has_missing_evidence_ids(paradigm, "propositions") or len(paradigm.get("propositions") or []) < 5:
            errors.append(
                {
                    "code": "PROPOSITIONS_INVALID",
                    "message": "Propositions deben ser >= 5 y cada una debe incluir evidence_ids no vacios.",
                }
            )
        if self._has_missing_evidence_ids(paradigm, "context") or self._has_missing_evidence_ids(paradigm, "intervening_conditions"):
            errors.append(
                {
                    "code": "CONTEXT_INTERVENING_INVALID",
                    "message": "Context/intervening_conditions deben incluir evidence_ids no vacios por item.",
                }
            )

        # EvidenceExists in project (computed by pipeline).
        if missing_evidence_ids:
            errors.append(
                {
                    "code": "EVIDENCE_MISSING",
                    "message": "Hay evidence_ids que no existen o no pertenecen al proyecto.",
                    "missing_ids_count": len(missing_evidence_ids),
                    "missing_ids_sample": missing_evidence_ids[:10],
                }
            )

        # Coverage by interviews (from evidence used by paradigm).
        used_ids: List[str] = []
        for key in ("conditions", "actions", "consequences", "propositions", "context", "intervening_conditions"):
            used_ids.extend(self._evidence_ids_for_section(paradigm, key))
        used_ids = [s for s in used_ids if s]

        interviews = {fragment_to_interview.get(fid) for fid in used_ids if fragment_to_interview.get(fid)}
        interviews_covered = len(interviews)
        if interviews_covered < self.effective_min_interviews:
            errors.append(
                {
                    "code": "COVERAGE_MIN_INTERVIEWS",
                    "message": (
                        f"Cobertura insuficiente: {interviews_covered} entrevistas citadas "
                        f"(min={self.effective_min_interviews})."
                    ),
                    "interviews_covered": interviews_covered,
                    "min_interviews": self.effective_min_interviews,
                    "min_interviews_configured": self.min_interviews,
                    "available_interviews": self.available_interviews,
                }
            )

        # Concentration warning (not a hard gate).
        counts: Dict[str, int] = {}
        for fid in used_ids:
            iv = fragment_to_interview.get(fid)
            if not iv:
                continue
            counts[iv] = counts.get(iv, 0) + 1
        total = sum(counts.values())
        if total > 0 and counts:
            top_iv, top_cnt = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0]
            share = top_cnt / total
            if share >= self.max_share_per_interview:
                warnings.append(
                    {
                        "code": "COVERAGE_CONCENTRATION",
                        "message": "Concentracion de evidencia: una sola entrevista aporta por encima del umbral configurado.",
                        "top_interview_id": top_iv,
                        "top_share": round(share, 3),
                        "max_share_per_interview": self.max_share_per_interview,
                    }
                )

        return {
            "enabled": True,
            "ok": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "stats": {
                "used_evidence_ids": len(used_ids),
                "interviews_covered": interviews_covered,
                "min_interviews_configured": self.min_interviews,
                "min_interviews_effective": self.effective_min_interviews,
                "adaptive_thresholds": self.adaptive_thresholds,
                "available_interviews": self.available_interviews,
                "max_share_per_interview_observed": (
                    round(max((cnt / total for cnt in counts.values()), default=0.0), 3)
                    if total > 0
                    else 0.0
                ),
            },
        }
