# TheoGen MVP Robusto — Plan de Implementación Incremental (para Codex 5.3 High en VSCode)

> **Propósito:** Este documento guía a Codex para implementar mejoras **incrementales y seguras** en TheoGen (sin romper lo existente), siguiendo el orden de PRs **Ruta A**:  
> **PR2 → PR4 → PR1 → PR3**  
>
> **Reglas de oro:**
> - No cambiar endpoints públicos existentes (mantener compatibilidad).
> - No truncar/limitar tokens “por defecto”. **Solo** aplicar degradación cuando el prompt exceda el límite del modelo en Azure.
> - Implementar “capabilities-aware” para evitar errores 400 por parámetros no soportados por ciertos modelos (DeepSeek/Kimi).
> - Cada PR debe compilar, pasar smoke tests y desplegar sin cambios arquitectónicos mayores.

---

## Tabla de contenidos
1. [Contexto y objetivos](#contexto-y-objetivos)  
2. [Riesgos/errores comunes (revisión crítica)](#riesgoserrores-comunes-revisión-crítica)  
3. [Feature flags y variables de entorno](#feature-flags-y-variables-de-entorno)  
4. [Ruta A — PR2](#ruta-a--pr2--model-capabilities--dynamic-token-budgeting)  
5. [Ruta A — PR4](#ruta-a--pr4--pipeline-escalonado-multi-llm--aprovechamiento-qdrantneo4j)  
6. [Ruta A — PR1](#ruta-a--pr1--plantillas-de-dominio--prompt-builder-incluye-estudios-de-mercado)  
7. [Ruta A — PR3](#ruta-a--pr3--exportación-avanzada-pptxxlsxpng)  
8. [Criterios de aceptación globales](#criterios-de-aceptación-globales)  
9. [Checklist final para merge](#checklist-final-para-merge)  

---

## Contexto y objetivos

TheoGen produce una **Teoría Fundamentada** desde entrevistas: transcripción → fragmentación → codificación → métricas de red (Neo4j) → evidencia semántica (Qdrant) → teoría (LLM) → exportación.

Problemas observados:
- **Errores 400** por parámetros no soportados (`temperature`, `response_format`) en ciertos modelos.
- **`context_length_exceeded`** por prompts demasiado largos (evidencia + categorías + red).
- Necesidad de un **pipeline escalonado** (múltiples llamadas LLM) para robustez y mejor uso de Qdrant/Neo4j.
- Mejorar **calidad del output** con plantillas por dominio (Educación, ONG, Gobierno, **Estudios de Mercado**).
- Exportaciones premium: **PPTX/XLSX/PNG** además de PDF.

---

## Riesgos/errores comunes (revisión crítica)

### 1) Parámetros de LLM no compatibles (Azure / Foundry / modelos alternativos)
**Riesgo:** Enviar `temperature != default`, `response_format`, etc. a modelos que no lo soportan → error 400.
**Mitigación:** Centralizar en un wrapper:
- Determinar capacidades por modelo (`supports_temperature`, `supports_json_mode`).
- Eliminar argumentos no soportados antes de llamar a la API.
- Añadir fallback: si falla con 400, reintentar una vez sin el parámetro conflictivo (opcional pero recomendado).

### 2) Confusión `max_tokens` vs `max_output_tokens`
**Riesgo:** Distintos endpoints/SDKs pueden usar nombres distintos.
**Mitigación:** Mantener compatibilidad con el SDK actual del repo.  
- Si se usa `client.chat.completions.create(...)`, el parámetro usual es `max_tokens`.
- Implementar un wrapper que permita ajustar si el SDK cambia (sin tocar todos los callers).

### 3) JSON mode no soportado o salida inválida
**Riesgo:** Sin `response_format`, el modelo puede devolver texto no JSON → `json.loads` falla.
**Mitigación:**
- En prompts: exigir “**JSON válido y solo JSON**”.
- Implementar un parser robusto: intentar `json.loads`; si falla, extraer bloque JSON (regex) o reintentar con un “fixer” (segunda llamada breve).
- Loggear el contenido problemático (con redacción básica para no filtrar PII si aplica).

### 4) “Degradación” que recarga Qdrant/Neo4j innecesariamente
**Riesgo:** Si cada loop de token budget re-ejecuta búsquedas, el costo/latencia se dispara.
**Mitigación:** Diseñar degradación como:
- **Primero recortar localmente** estructuras ya recuperadas (evidencia, network metrics).
- Solo si es necesario, reconsultar (y aún así con límites).
- Ideal: “fetch once + trim”.

### 5) Concurrencia excesiva y rate limits (429)
**Riesgo:** Con pipeline escalonado + paralelismo, se puede golpear TPM/RPM.
**Mitigación:** Semáforos por etapa y reintentos con backoff:
- Limitar concurrencia por proyecto/usuario.
- Reintentar 429 con jitter.
- Telemetría de tokens y latencia.

### 6) Migraciones y compatibilidad de schemas
**Riesgo:** Agregar `Project.domain_template` requiere:
- Alembic migration
- Ajustes Pydantic schemas
- Cambios en endpoints de Project (create/update)
- Frontend (selector)
**Mitigación:** Implementar cambios “end-to-end” en el PR1.

### 7) Exportación y dependencias
**Riesgo:** PPTX/XLSX/PNG requiere librerías extra y fuentes.
**Mitigación:**
- Agregar dependencias en `requirements.txt` o equivalente.
- En infografía (Pillow), usar fuentes “default” si Arial no existe (fallback).
- Validar generación en contenedor Linux.

---

## Feature flags y variables de entorno

**Agregar/confirmar en `.env` y `settings.py`:**
- `THEORY_LLM_MAX_OUTPUT_TOKENS=4096`
- `MODEL_CONTEXT_LIMIT_GPT_52_CHAT=272000`
- `THEORY_PROMPT_VERSION=v2` (default)
- `THEORY_PIPELINE_MODE=staged` (opcional; default staged una vez implementado)
- (si existe) `MODEL_KIMI`, `MODEL_DEEPSEEK`, etc.
- Export: `AZURE_STORAGE_*` ya configurado y contenedor `theogen-exports` existe.

---

# Ruta A — PR2 — Model Capabilities + Dynamic Token Budgeting

## Objetivo PR2
1) Evitar errores 400 por parámetros no soportados.  
2) Definir un “budgeter” que **solo degrade** si el prompt excede el contexto permitido.

## Archivos a crear/modificar

### 1) `backend/app/core/settings.py`
Agregar:
- `THEORY_LLM_MAX_OUTPUT_TOKENS: int = int(os.getenv("THEORY_LLM_MAX_OUTPUT_TOKENS", "4096"))`
- `MODEL_CONTEXT_LIMIT_GPT_52_CHAT: int = int(os.getenv("MODEL_CONTEXT_LIMIT_GPT_52_CHAT", "272000"))`
- `MODEL_CONTEXT_LIMITS = {"gpt-5.2-chat": MODEL_CONTEXT_LIMIT_GPT_52_CHAT}`

Budgets fallback (solo para degradación):
- `THEORY_BUDGET_FALLBACK_MAX_CATS=60`
- `THEORY_BUDGET_FALLBACK_MAX_FRAGS_PER_CAT=3`
- `THEORY_BUDGET_FALLBACK_MAX_FRAG_CHARS=900`
- `THEORY_BUDGET_FALLBACK_NETWORK_TOP=60`

### 2) `backend/app/utils/token_budget.py` (nuevo)
Implementar:
- `estimate_tokens(text: str, model: str) -> int`
  - usar `tiktoken` si disponible; fallback `len(text)//4`
- `estimate_messages_tokens(messages: list[dict], model: str) -> int`
- `fits_context(messages, model, context_limit, max_output_tokens, margin_tokens=2000) -> bool`
- `ensure_within_budget(messages, model, context_limit, max_output_tokens, degrade_cb) -> (messages, debug)`
  - **Si cabe**: return sin cambios
  - **Si no**: llamar `degrade_cb()` iterativamente (máx 6) y re-evaluar

> Nota: `degrade_cb` debe **recortar payload local**, no reconsultar servicios externos en loop.

### 3) `backend/app/services/azure_openai.py`
Modificar `_chat_call`:
- Default `max_tokens=settings.THEORY_LLM_MAX_OUTPUT_TOKENS` si no viene.
- Capabilities:
  - `supports_temperature(model)` y `supports_json_mode(model)`
  - Si no soporta, eliminar `temperature` y/o `response_format`.
  - Primer approach robusto:
    - si `deepseek` o `kimi` en nombre → no enviar `temperature` ni `response_format`.
- Logging debug de parámetros enviados.

Opcional (recomendado): “retry-on-400-unsupported-parameter”
- Si error 400 y `param` es `temperature` o `response_format`, reintentar una vez sin ese param.

### 4) Tests mínimos
`backend/tests/test_token_budget.py`
- `test_budget_no_change_when_under_limit`
- `test_budget_degrades_when_over_limit`

## Criterios de aceptación PR2
- No hay fallos 400 por `temperature`/`response_format` en modelos no compatibles.
- Existe `max_tokens` default.
- No se recorta input si el prompt está bajo el límite.
- Logs reportan estimación de tokens.

---

# Ruta A — PR4 — Pipeline escalonado (multi-LLM) + aprovechamiento Qdrant/Neo4j

## Objetivo PR4
Reestructurar la generación de teoría en **etapas**:
- reduce riesgo de overflow
- permite mejor uso de Neo4j (estructura) + Qdrant (evidencia)
- facilita debug y reintentos

## Diseño de etapas

**Etapa 0 — collect_data**
- entrevistar completadas, categorías, códigos, conteos (PostgreSQL)

**Etapa 1 — compute_network_metrics (Neo4j)**
- centralidad, coocurrencia, counts
- producir `network_metrics` compacto (pero sin recortar si cabe)

**Etapa 2 — gather_evidence (Qdrant)**
- Para categorías top y sus vecindarios (Neo4j), obtener evidencia semántica (top fragments)
- Guardar evidencia como estructura:
  ```json
  { "category_id": "...", "category_name": "...", "fragments": [{"id":"...","text":"...","score":0.12,"metadata":{...}}] }
  ```

**Etapa 3 — LLM Step 1: identify central**
- Input: categorías + network + evidencia (si cabe)
- Output JSON: central + justificación + observaciones críticas

**Etapa 4 — LLM Step 2: build paradigm**
- Input: central + categorías relacionadas (vecinos en red) + evidencia focalizada
- Output JSON: paradigma completo (condiciones, acciones, consecuencias, tensiones/contradicciones)

**Etapa 5 — LLM Step 3: analyze gaps**
- Input: paradigma + categorías resumidas (sin re-enviar evidencia cruda si ya fue usada)
- Output JSON: brechas + recomendaciones + saturación

**Etapa 6 — save**
- persistir `Theory` en PostgreSQL
- opcional: sincronizar taxonomía en Neo4j si aplica

## “Degradación progresiva” SOLO si overflow
Para cada etapa LLM:
1) reducir `fragments per category`
2) truncar `chars per fragment`
3) reducir `# categorías` (top por centralidad)
4) reducir `network top lists`
5) remover evidence en Step2/Step3 (si Step1 ya la incluyó)

## Archivos a crear/modificar

### 1) `backend/app/engines/theory_pipeline.py` (nuevo)
Crear:
- `StrategyState` (dataclass):
  - `max_cats`, `max_frags_per_cat`, `max_frag_chars`, `max_network_top`
  - `remove_evidence_step2`, `remove_evidence_step3`
  - método `degrade()` que aplica un paso y retorna “qué cambió”
- `TheoryPipeline` con:
  - `collect_data(...)`
  - `compute_network_metrics(...)`
  - `gather_evidence(...)`
  - `llm_identify_central(...)`
  - `llm_build_paradigm(...)`
  - `llm_analyze_gaps(...)`
  - `save(...)`

Integración con `ensure_within_budget(...)`:
- Construir `messages`
- Si no cabe: llamar a `degrade_cb` que **recorta el payload local** (cats/network/evidence) y reconstruye el prompt.

### 2) `backend/app/api/theory.py`
Reemplazar el bloque monolítico actual del pipeline por la llamada a `TheoryPipeline`.
- Mantener endpoints públicos:
  - `/generate-theory` (inicia task)
  - `/generate-theory/status/{task_id}`
- Logging por stage:
  - `task_id`, `project_id`, `stage`, `elapsed_ms`, `tokens_estimated`, `degradation_steps`

### 3) `backend/app/services/qdrant_service.py`
Asegurar:
- `search_supporting_fragments(project_id, query_vector, limit)` retorna consistentemente `id/text/score/metadata`.

## Criterios de aceptación PR4
- Pipeline funciona end-to-end con status.
- Si el prompt cabe, no recorta.
- Si no cabe, degrada hasta caber sin romper semántica.
- Logs permiten ver:
  - en qué etapa falló
  - tokens estimados
  - degradaciones aplicadas
- Sin loops de reconsulta Qdrant/Neo4j por cada degradación (trim local).

---

# Ruta A — PR1 — Plantillas de dominio + Prompt Builder (incluye Estudios de Mercado)

## Objetivo PR1
Mejorar calidad del output y relevancia por vertical, manteniendo estructura de teoría.

## Archivos a crear/modificar

### 1) `backend/app/services/prompts/domain_templates.py` (nuevo)
Definir:
- `DomainTemplate` y templates:
  - `generic`
  - `education`
  - `ngo`
  - `government`
  - `market_research` ✅

Campos:
- `actors`, `critical_dimensions`, `lexicon_map`, `metrics`, `export_formats`, `extra_instructions`

### 2) `backend/app/services/prompts/theory_prompts_v2.py` (nuevo)
Prompts base v2 con placeholders:
- `IDENTIFY_CENTRAL_CATEGORY_BASE`
- `BUILD_PARADIGM_BASE`
- `ANALYZE_GAPS_BASE`
Incluye “pensamiento crítico” y soporte a lexicon/actores/dimensiones.

### 3) `backend/app/services/prompts/prompt_builder.py` (nuevo)
Implementar:
- `get_template(key)`
- `build_prompt(step, template_key, payload)`
- `build_messages(system_role, prompt)`

### 4) `backend/app/models/models.py` + Alembic
Agregar columna:
- `Project.domain_template` default `"generic"`
Migración:
- `add_domain_template_to_projects`

### 5) Integración en `TheoryPipeline`
- Obtener `template_key` desde `Project.domain_template`
- Construir prompts para cada step con `prompt_builder`

### 6) Frontend
- Selector simple de template en create/edit project.
- Default `generic` si no se define.

## Criterios de aceptación PR1
- Proyecto `market_research` produce lenguaje de insights:
  - drivers/barriers, journey, segmentos, WTP, NPS/CSAT, etc.
- Proyecto `education` produce “comunidad educativa”, prácticas pedagógicas, etc.
- No rompe estructura JSON existente.

---

# Ruta A — PR3 — Exportación avanzada (PPTX/XLSX/PNG)

## Objetivo PR3
Además del PDF, exportar entregables profesionales:
- PPTX (deck)
- XLSX (tablas)
- PNG (infografía/poster)

## Dependencias
Agregar (si no están):
- `python-pptx`
- `openpyxl`
- `Pillow`

## Archivos a crear/modificar

### 1) `backend/app/services/export/pptx_generator.py` (nuevo)
Generar presentación (8–12 slides):
- portada
- resumen ejecutivo
- categoría central
- paradigma (causas/contexto/interacciones/consecuencias)
- proposiciones
- brechas
- próximos pasos

### 2) `backend/app/services/export/xlsx_generator.py` (nuevo)
Workbook con hojas:
- Resumen
- Categorías
- Evidencia
- Paradigma
- Proposiciones
- Brechas
- (opcional) Métricas

### 3) `backend/app/services/export/infographic_generator.py` (nuevo)
PNG 1200x1600:
- header proyecto
- círculo central
- 3 causas + 3 estrategias + 2 consecuencias
- footer métricas (confianza, entrevistas, brechas)

### 4) `backend/app/services/export_service.py`
Añadir:
- `generate_theory_report(theory_id, format="pdf|pptx|xlsx|png", template_key=None)`
- Subir a `theogen-exports`, retornar SAS URL.

### 5) API
Nuevo endpoint:
- `POST /projects/{project_id}/theories/{theory_id}/export?format=pdf|pptx|xlsx|png`

### 6) Frontend
Botones:
- Descargar PDF / PPTX / XLSX / Infografía

## Criterios de aceptación PR3
- Archivos generados no vacíos y descargables.
- Portada o títulos aplican template (education/ngo/government/market_research).
- PDF sigue funcionando.

---

## Criterios de aceptación globales

1) **Robustez**: No más `context_length_exceeded` para casos típicos; si hay overflow extremo, la degradación lo resuelve o falla con mensaje claro.  
2) **Compatibilidad**: No se rompen endpoints existentes ni el flujo UI actual.  
3) **Observabilidad**: Logs por etapa + tokens estimados + degradación aplicada + latencia por llamada.  
4) **Calidad**: Plantillas aumentan relevancia por vertical (Market Research incluido).  
5) **Export**: PPTX/XLSX/PNG operativos en contenedor Linux.

---

## Checklist final para merge

- [ ] PR2 mergeable: tests pasan, no 400 por params.
- [ ] PR4 mergeable: pipeline escalonado, status OK, degradación solo si overflow.
- [ ] PR1 mergeable: `domain_template` end-to-end (DB + API + UI).
- [ ] PR3 mergeable: exportes funcionan y se suben a Blob.

---

## Notas operativas

- **No re-consultar Qdrant/Neo4j en loop**: degradación debe recortar local.
- Si el SDK/endpoint de Azure cambia y `max_tokens` falla, ajustar solo el wrapper.
- Las plantillas no deben forzar cambios de ontología (solo lenguaje, foco y formato).
