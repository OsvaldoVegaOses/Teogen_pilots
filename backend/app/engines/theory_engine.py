from __future__ import annotations

import logging
from typing import Any, Dict, List

from ..core.json_utils import safe_json_loads
from ..core.settings import settings
from ..engines.model_router import model_router
from ..prompts import (
    CENTRAL_CATEGORY_SYSTEM_PROMPT,
    GAP_ANALYSIS_SYSTEM_PROMPT,
    STRAUSSIAN_MODEL_SYSTEM_PROMPT,
    get_central_category_user_prompt,
    get_straussian_build_prompt,
)
from ..prompts.prompt_builder import build_messages, build_prompt, get_system_prompt_for_step
from ..services.azure_openai import foundry_openai

logger = logging.getLogger(__name__)

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


class TheoryGenerationEngine:
    """Orchestrates central category, paradigm, and gap analysis steps."""

    def __init__(self):
        self.ai = foundry_openai
        self.router = model_router

    @staticmethod
    def _use_v2_prompts() -> bool:
        return (settings.THEORY_PROMPT_VERSION or "v2").strip().lower().startswith("v2")

    def build_identify_messages(
        self,
        categories: list,
        network: dict,
        template_key: str = "generic",
    ) -> list[dict]:
        if self._use_v2_prompts():
            prompt = build_prompt(
                step="identify",
                template_key=template_key,
                payload={"categories": categories, "network": network},
            )
            return build_messages(get_system_prompt_for_step("identify"), prompt)

        return [
            {"role": "system", "content": CENTRAL_CATEGORY_SYSTEM_PROMPT},
            {"role": "user", "content": get_central_category_user_prompt(categories, network)},
        ]

    def build_paradigm_messages(
        self,
        central_cat: str,
        other_cats: list,
        template_key: str = "generic",
    ) -> list[dict]:
        if self._use_v2_prompts():
            prompt = build_prompt(
                step="paradigm",
                template_key=template_key,
                payload={"central_cat": central_cat, "other_cats": other_cats},
            )
            return build_messages(get_system_prompt_for_step("paradigm"), prompt)

        return [
            {"role": "system", "content": STRAUSSIAN_MODEL_SYSTEM_PROMPT},
            {"role": "user", "content": get_straussian_build_prompt(central_cat, other_cats)},
        ]

    def build_gaps_messages(
        self,
        theory_data: dict,
        template_key: str = "generic",
    ) -> list[dict]:
        if self._use_v2_prompts():
            prompt = build_prompt(
                step="gaps",
                template_key=template_key,
                payload={"theory_data": theory_data},
            )
            return build_messages(get_system_prompt_for_step("gaps"), prompt)

        return [
            {"role": "system", "content": GAP_ANALYSIS_SYSTEM_PROMPT},
            {"role": "user", "content": f"Theory Current Data: {theory_data}"},
        ]

    @staticmethod
    def _as_text(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, (str, int, float, bool)):
            return str(value)
        if isinstance(value, list):
            return " ".join(TheoryGenerationEngine._as_text(v) for v in value)
        if isinstance(value, dict):
            parts = []
            for k in ("name", "text", "description", "definition", "evidence"):
                if k in value and value[k] is not None:
                    parts.append(str(value[k]))
            return " ".join(parts) if parts else str(value)
        return str(value)

    @staticmethod
    def _contains_prohibited_terms(value: Any) -> bool:
        text = TheoryGenerationEngine._as_text(value).lower()
        return any(term in text for term in _PROHIBITED_META_TERMS)

    @staticmethod
    def normalize_paradigm(paradigm: Dict[str, Any], central_cat: str) -> Dict[str, Any]:
        out = dict(paradigm or {})
        out.setdefault("selected_central_category", central_cat)

        if "conditions" not in out and "causal_conditions" in out:
            out["conditions"] = out.get("causal_conditions")
        if "actions" not in out and "action_strategies" in out:
            out["actions"] = out.get("action_strategies")
        if "propositions" not in out:
            out["propositions"] = []
        # Keep the Straussian fields available to support proposition→context coherence.
        out.setdefault("context", [])
        out.setdefault("intervening_conditions", [])

        return out

    @staticmethod
    def validate_paradigm(paradigm: Dict[str, Any]) -> Dict[str, Any]:
        props = paradigm.get("propositions") or []
        consequences = paradigm.get("consequences") or []
        context = paradigm.get("context") or []
        intervening = paradigm.get("intervening_conditions") or []

        validation: Dict[str, Any] = {
            "propositions_count": len(props) if isinstance(props, list) else 0,
            "propositions_ok": isinstance(props, list) and len(props) >= 5,
            "consequences_has_prohibited_terms": TheoryGenerationEngine._contains_prohibited_terms(consequences),
            "consequences_ok": False,
            "consequences_types_present": [],
            "consequences_horizons_present": [],
            "context_count": len(context) if isinstance(context, list) else 0,
            "intervening_conditions_count": len(intervening) if isinstance(intervening, list) else 0,
        }

        types_present = set()
        horizons_present = set()
        if isinstance(consequences, list):
            for c in consequences:
                if isinstance(c, dict):
                    t = str(c.get("type") or "").strip().lower()
                    h = str(c.get("horizon") or "").strip().lower()
                    if t:
                        types_present.add(t)
                    if h:
                        horizons_present.add(h)

        validation["consequences_types_present"] = sorted(types_present)
        validation["consequences_horizons_present"] = sorted(horizons_present)

        required_types = {"material", "social", "institutional"}
        required_horizons = {"corto_plazo", "largo_plazo"}
        validation["consequences_ok"] = (
            not validation["consequences_has_prohibited_terms"]
            and required_types.issubset(types_present)
            and required_horizons.issubset(horizons_present)
        )

        return validation

    async def repair_context_intervening(
        self,
        *,
        central_cat: str,
        paradigm: Dict[str, Any],
        evidence_index: List[Dict[str, Any]],
        available_categories: List[str],
        target_min_each: int = 2,
    ) -> Dict[str, Any]:
        """
        Best-effort repair: ensure constructs introduced in propositions are represented in context/intervening.
        Returns a dict with keys: context, intervening_conditions (each list).
        """

        target_min_each = max(0, min(6, int(target_min_each)))
        evidence_rule = (
            "- Cuando sea posible, incluye evidence_ids con al menos 1 id del evidence_index.\n"
            if evidence_index
            else "- Incluye evidence_ids (puede ser lista vacia si no hay evidencia_index).\n"
        )

        prompt = "".join(
            [
                "Ajusta SOLO los campos context e intervening_conditions.\n",
                "Objetivo: si alguna proposicion introduce un constructo que NO esta representado como categoria en conditions/actions/consequences,\n",
                "debes agregarlo como categoria en context o intervening_conditions.\n",
                "Reglas:\n",
                "- NO inventar nuevos conceptos; solo usar conceptos presentes en propositions o en available_categories.\n",
                "- No usar terminos meta-metodologicos (entrevista, informante, identificacion, etc.).\n",
                "- Usa nombres canonicos y consistentes.\n",
                f"- Apunta a minimo {target_min_each} items en cada lista cuando haya material suficiente.\n",
                evidence_rule,
                "- Devuelve JSON valido y SOLO JSON con este schema:\n",
                "{\n",
                "  \"context\": [ { \"name\": \"string\", \"evidence_ids\": [\"...\"] } ],\n",
                "  \"intervening_conditions\": [ { \"name\": \"string\", \"evidence_ids\": [\"...\"] } ]\n",
                "}\n\n",
                f"selected_central_category: {central_cat}\n",
                f"conditions: {paradigm.get('conditions')}\n",
                f"actions: {paradigm.get('actions')}\n",
                f"consequences: {paradigm.get('consequences')}\n",
                f"propositions: {paradigm.get('propositions')}\n",
                f"current_context: {paradigm.get('context')}\n",
                f"current_intervening_conditions: {paradigm.get('intervening_conditions')}\n",
                f"available_categories: {available_categories[:80]}\n",
                f"evidence_index: {evidence_index}\n",
            ]
        )

        messages = build_messages(get_system_prompt_for_step("gaps"), prompt)
        raw = await self.ai.reasoning_fast(messages=messages)
        repaired = safe_json_loads(raw) or {}
        out = {
            "context": repaired.get("context", []),
            "intervening_conditions": repaired.get("intervening_conditions", []),
        }
        if not isinstance(out["context"], list):
            out["context"] = []
        if not isinstance(out["intervening_conditions"], list):
            out["intervening_conditions"] = []
        return out

    async def repair_propositions(
        self,
        *,
        central_cat: str,
        paradigm: Dict[str, Any],
        evidence_index: List[Dict[str, Any]],
        target_count: int = 7,
    ) -> List[Dict[str, Any]]:
        target_count = max(5, min(10, int(target_count)))
        evidence_rule = (
            "- Cada proposicion DEBE incluir evidence_ids con al menos 1 id del evidence_index.\n"
            if evidence_index
            else "- Incluye evidence_ids (puede ser lista vacia si no hay evidencia_index).\n"
        )

        prompt = "".join(
            [
                "Completa SOLO el campo propositions.\n",
                "Reglas:\n",
                f"- Genera entre 5 y 10 proposiciones (objetivo={target_count}).\n",
                "- Formato: 'Si X y Y, entonces Z, porque M.'\n",
                evidence_rule,
                "- Devuelve JSON valido y solo JSON: {\"propositions\": [{\"text\": \"...\", \"evidence_ids\": [\"...\"]}]}\n\n",
                f"selected_central_category: {central_cat}\n",
                (
                    "paradigm_summary: "
                    f"{{\"conditions\": {paradigm.get('conditions')}, "
                    f"\"actions\": {paradigm.get('actions')}, "
                    f"\"consequences\": {paradigm.get('consequences')}}}\n"
                ),
                f"evidence_index: {evidence_index}\n",
            ]
        )

        messages = build_messages(get_system_prompt_for_step("gaps"), prompt)
        raw = await self.ai.reasoning_fast(messages=messages)
        repaired = safe_json_loads(raw)
        propositions = repaired.get("propositions", [])
        return propositions if isinstance(propositions, list) else []

    async def repair_consequences(
        self,
        *,
        central_cat: str,
        paradigm: Dict[str, Any],
        evidence_index: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        evidence_rule = (
            "- Cada consecuencia DEBE incluir evidence_ids con al menos 1 id del evidence_index.\n"
            if evidence_index
            else "- Incluye evidence_ids (puede ser lista vacia si no hay evidencia_index).\n"
        )

        prompt = "".join(
            [
                "Reescribe SOLO el campo consequences.\n",
                "Reglas:\n",
                "- NO usar terminos del proceso de entrevista (informante, identificacion, entrevista, solicitud de identificacion, etc.).\n",
                "- Consecuencias observables del fenomeno, no meta-metodologia.\n",
                "- Debe incluir al menos 1 material, 1 social, 1 institutional.\n",
                "- Debe incluir horizonte: corto_plazo y largo_plazo (campo obligatorio por item).\n",
                evidence_rule,
                "- Devuelve JSON valido y solo JSON: {\"consequences\": [{\"name\": \"...\", \"type\": \"material|social|institutional\", \"horizon\": \"corto_plazo|largo_plazo\", \"evidence_ids\": [\"...\"]}]}\n\n",
                f"selected_central_category: {central_cat}\n",
                (
                    "paradigm_context: "
                    f"{{\"conditions\": {paradigm.get('conditions')}, "
                    f"\"actions\": {paradigm.get('actions')}}}\n"
                ),
                f"evidence_index: {evidence_index}\n",
            ]
        )

        messages = build_messages(get_system_prompt_for_step("gaps"), prompt)
        raw = await self.ai.reasoning_fast(messages=messages)
        repaired = safe_json_loads(raw)
        consequences = repaired.get("consequences", [])
        return consequences if isinstance(consequences, list) else []

    async def identify_central_category(
        self,
        categories: list,
        network: dict,
        template_key: str = "generic",
    ) -> dict:
        logger.info(
            "Identifying central category (template=%s, prompt_version=%s)",
            template_key,
            settings.THEORY_PROMPT_VERSION,
        )

        required_network_keys = {"counts", "category_centrality", "category_cooccurrence"}
        missing = required_network_keys - set(network.keys())
        if missing:
            raise ValueError(f"Network payload missing required keys: {', '.join(sorted(missing))}")

        messages = self.build_identify_messages(categories, network, template_key)
        response = await self.ai.reasoning_advanced(
            messages=messages,
            max_completion_tokens=settings.THEORY_LLM_MAX_OUTPUT_TOKENS_LARGE,
        )
        return safe_json_loads(response)

    async def build_straussian_paradigm(
        self,
        central_cat: str,
        other_cats: list,
        template_key: str = "generic",
    ) -> dict:
        logger.info(
            "Building Straussian paradigm (template=%s, prompt_version=%s)",
            template_key,
            settings.THEORY_PROMPT_VERSION,
        )

        messages = self.build_paradigm_messages(central_cat, other_cats, template_key)
        route_result = await self.router.route_and_generate(
            task_type="qualitative_modeling",
            prompt=messages[1]["content"],
            system_prompt=messages[0]["content"],
        )
        return safe_json_loads(route_result["result"])

    async def analyze_saturation_and_gaps(
        self,
        theory_data: dict,
        template_key: str = "generic",
    ) -> dict:
        logger.info(
            "Analyzing saturation and gaps (template=%s, prompt_version=%s)",
            template_key,
            settings.THEORY_PROMPT_VERSION,
        )

        messages = self.build_gaps_messages(theory_data, template_key)
        response = await self.ai.reasoning_fast(messages=messages)
        return safe_json_loads(response)


theory_engine = TheoryGenerationEngine()
