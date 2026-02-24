IDENTIFY_CENTRAL_CATEGORY_BASE = """
Contexto de dominio:
{domain_brief}

Instrucciones de analisis:
- Evalua centralidad teorica y poder explicativo.
- Explicita tensiones y contradicciones.
- Devuelve salida en JSON valido.

Datos:
{payload}
"""


BUILD_PARADIGM_BASE = """
Contexto de dominio:
{domain_brief}

Construye un paradigma Straussiano (condiciones, acciones/interacciones, consecuencias)
con trazabilidad a evidencia y claridad causal.
Devuelve JSON valido.

REGLAS OBLIGATORIAS DE CALIDAD (no omitir):
1) Chequeo de validez de consecuencias:
- No usar terminos del proceso de entrevista (p.ej. informante, identificacion, entrevista, solicitud de identificacion).
- Consecuencias deben ser observables del fenomeno (material/social/institucional), no meta-metodologia.
- Incluir al menos: 1 consecuencia material (danos/perdidas), 1 social (cohesion/conflicto), 1 institucional (respuesta/coord.).
- Incluir horizonte temporal: corto_plazo vs largo_plazo (campo obligatorio).

2) Proposiciones teoricas obligatorias:
- Genera entre 5 y 10 proposiciones.
- Formato: "Si X y Y, entonces Z, porque M."
- Cada proposicion debe referenciar al menos 1 evidencia via ids (`evidence_ids`), usando fragment_id/id provistos en los datos.

3) JSON esperado (minimo):
{{
  "selected_central_category": "string",
  "conditions": [...],
  "actions": [...],
  "consequences": [
    {{ "name": "string", "type": "material|social|institutional", "horizon": "corto_plazo|largo_plazo", "evidence_ids": ["..."] }}
  ],
  "propositions": [
    {{ "text": "Si X y Y, entonces Z, porque M.", "evidence_ids": ["..."] }}
  ],
  "confidence_score": 0.0
}}

Datos:
{payload}
"""


ANALYZE_GAPS_BASE = """
Contexto de dominio:
{domain_brief}

Analiza saturacion teorica, brechas y riesgos de validez.
Devuelve JSON valido.

Datos:
{payload}
"""
