from __future__ import annotations

from typing import Any, Dict

from .axial_coding import AXIAL_CODING_SYSTEM_PROMPT
from .central_category import CENTRAL_CATEGORY_SYSTEM_PROMPT, get_central_category_user_prompt
from .domain_templates import DOMAIN_TEMPLATES, DomainTemplate
from .gap_analysis import GAP_ANALYSIS_SYSTEM_PROMPT
from .straussian_model import STRAUSSIAN_MODEL_SYSTEM_PROMPT, get_straussian_build_prompt
from .theory_prompts_v2 import (
    ANALYZE_GAPS_BASE,
    BUILD_PARADIGM_BASE,
    IDENTIFY_CENTRAL_CATEGORY_BASE,
)


def get_template(key: str) -> DomainTemplate:
    return DOMAIN_TEMPLATES.get((key or "generic").strip().lower(), DOMAIN_TEMPLATES["generic"])


def _domain_brief(template: DomainTemplate) -> str:
    return (
        f"Template={template.key}; "
        f"Actores={', '.join(template.actors)}; "
        f"Dimensiones={', '.join(template.critical_dimensions)}; "
        f"Metricas={', '.join(template.metrics)}; "
        f"Instrucciones={template.extra_instructions}"
    )


def build_prompt(step: str, template_key: str, payload: Dict[str, Any]) -> str:
    template = get_template(template_key)
    step_norm = (step or "").strip().lower()

    if step_norm == "identify":
        legacy = get_central_category_user_prompt(payload["categories"], payload["network"])
        return IDENTIFY_CENTRAL_CATEGORY_BASE.format(
            domain_brief=_domain_brief(template),
            payload=legacy,
        )
    if step_norm == "paradigm":
        legacy = get_straussian_build_prompt(payload["central_cat"], payload["other_cats"])
        return BUILD_PARADIGM_BASE.format(
            domain_brief=_domain_brief(template),
            payload=legacy,
        )
    if step_norm == "gaps":
        legacy = f"Theory Current Data: {payload['theory_data']}"
        return ANALYZE_GAPS_BASE.format(
            domain_brief=_domain_brief(template),
            payload=legacy,
        )
    raise ValueError(f"Unsupported prompt step: {step}")


def build_messages(system_role: str, prompt: str):
    return [
        {"role": "system", "content": system_role},
        {"role": "user", "content": prompt},
    ]


def get_system_prompt_for_step(step: str) -> str:
    step_norm = (step or "").strip().lower()
    if step_norm == "identify":
        return CENTRAL_CATEGORY_SYSTEM_PROMPT
    if step_norm == "paradigm":
        return STRAUSSIAN_MODEL_SYSTEM_PROMPT
    if step_norm == "gaps":
        return GAP_ANALYSIS_SYSTEM_PROMPT
    if step_norm == "coding":
        return AXIAL_CODING_SYSTEM_PROMPT
    raise ValueError(f"Unsupported prompt step: {step}")
