from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


@dataclass(frozen=True)
class DomainTemplate:
    key: str
    actors: List[str]
    critical_dimensions: List[str]
    lexicon_map: Dict[str, str]
    metrics: List[str]
    export_formats: List[str]
    extra_instructions: str


DOMAIN_TEMPLATES: Dict[str, DomainTemplate] = {
    "generic": DomainTemplate(
        key="generic",
        actors=["participantes", "organizacion", "entorno"],
        critical_dimensions=["causas", "acciones", "consecuencias", "tensiones"],
        lexicon_map={},
        metrics=["consistencia", "saturacion", "trazabilidad"],
        export_formats=["pdf", "pptx", "xlsx", "png"],
        extra_instructions="Usa lenguaje analitico claro y falsable.",
    ),
    "education": DomainTemplate(
        key="education",
        actors=["estudiantes", "docentes", "familias", "gestion escolar"],
        critical_dimensions=["aprendizaje", "practicas pedagogicas", "equidad", "retencion"],
        lexicon_map={"clientes": "estudiantes/familias", "producto": "proceso educativo"},
        metrics=["logro", "asistencia", "permanencia", "satisfaccion"],
        export_formats=["pdf", "pptx", "xlsx", "png"],
        extra_instructions="Prioriza comunidad educativa, barreras de aprendizaje y condiciones institucionales.",
    ),
    "ngo": DomainTemplate(
        key="ngo",
        actors=["beneficiarios", "equipo tecnico", "voluntariado", "aliados"],
        critical_dimensions=["impacto", "inclusion", "sostenibilidad", "gobernanza"],
        lexicon_map={"cliente": "beneficiario", "mercado": "territorio/poblacion objetivo"},
        metrics=["alcance", "impacto percibido", "continuidad", "adopcion"],
        export_formats=["pdf", "pptx", "xlsx", "png"],
        extra_instructions="Destaca cambio social, riesgos operativos y mecanismos de rendicion de cuentas.",
    ),
    "government": DomainTemplate(
        key="government",
        actors=["ciudadania", "funcionariado", "entidades", "proveedores"],
        critical_dimensions=["eficiencia", "cobertura", "calidad de servicio", "transparencia"],
        lexicon_map={"cliente": "ciudadania", "producto": "servicio publico"},
        metrics=["tiempo de atencion", "cobertura", "satisfaccion", "cumplimiento"],
        export_formats=["pdf", "pptx", "xlsx", "png"],
        extra_instructions="Enfatiza cuellos de botella institucionales, normativa y capacidad de implementacion.",
    ),
    "market_research": DomainTemplate(
        key="market_research",
        actors=["segmentos", "compradores", "usuarios", "canales"],
        critical_dimensions=["drivers", "barriers", "journey", "trade-offs", "willingness_to_pay"],
        lexicon_map={"beneficiario": "segmento objetivo", "intervencion": "propuesta de valor"},
        metrics=["NPS", "CSAT", "conversion", "retencion", "WTP"],
        export_formats=["pdf", "pptx", "xlsx", "png"],
        extra_instructions="Produce insights accionables de mercado y explicita contradicciones entre segmentos.",
    ),
}
