# TheoGen MVP Robusto - Adenda de Compatibilidad e Implementacion Segura

Fecha: 2026-02-23  
Base: `docs/CODEX_PLAN_THEOGEN_MVP_ROBUSTO.md`

## 1) Objetivo de esta adenda

Ajustar el plan original para que sea implementable sobre el estado real del proyecto, evitando regresiones.

Principio rector:
- Mantener contrato API y arquitectura operativa actual (`202 + polling`, lock por proyecto, ownership por task, modo local/celery).

## 2) Reglas obligatorias de implementacion

1. No reemplazar `backend/app/api/theory.py` como bloque monolitico.
2. No eliminar la logica actual de:
   - lock distribuido
   - ownership de task
   - estados enriquecidos (`step`, `progress`, `error_code`, `next_poll_seconds`)
   - modo `local/celery`
3. No reescribir desde cero `backend/app/services/azure_openai.py`; solo extender deltas faltantes.
4. Cualquier cambio de modelo de datos requiere migracion formal (no cambios directos sin migrar).
5. Toda nueva funcionalidad debe ser backward-compatible.

## 3) Plan de PRs corregido (implementable)

Orden recomendado:
1. PR2 (delta)
2. PR4 (extraccion controlada)
3. PR1 (con bootstrap migraciones)
4. PR3 (extensiones export)

---

## PR2 - Model Capabilities + Token Budgeting (delta)

### Mantener
- Wrapper actual en `backend/app/services/azure_openai.py` (ya maneja compatibilidad de parametros en tiempo real).

### Agregar/ajustar
1. Crear util de presupuesto:
   - `backend/app/utils/token_budget.py`
2. Integrar budgeter en llamadas LLM de teoria sin romper flujo actual.
3. Logging estructurado de estimacion de tokens y decisiones de degradacion.
4. No usar `os.getenv` inline en `settings`; usar campos tipados en `backend/app/core/settings.py`.

### Criterio de no-ruptura
- Si prompt cabe, no se recorta.
- Si no cabe, degradacion local (sin refetch en loop).

---

## PR4 - Pipeline escalonado (sin romper orquestacion)

### Dise�o compatible
1. Crear:
   - `backend/app/engines/theory_pipeline.py`
2. `backend/app/api/theory.py` queda como orquestador de tareas:
   - enqueue
   - lock
   - status
   - ownership
3. Reemplazar solo la logica interna de `_theory_pipeline(...)` por llamadas a `TheoryPipeline`, preservando:
   - `task_id`, `step`, `progress`
   - modos `local/celery`
   - manejo de errores y persistencia de estado

### Contrato de datos
- Mantener contrato actual de evidencia Qdrant (`fragment_id`, `text`, `score`, `codes`) o versionarlo explicitamente antes de cambiarlo.

---

## PR1 - Domain templates (con migraciones reales)

### Precondicion obligatoria
No existe estructura Alembic activa en repo. Antes de `domain_template`:
1. bootstrap Alembic (`alembic.ini`, `env.py`, `versions/`)
2. baseline migration

### Luego implementar
1. `Project.domain_template` (DB + modelo + schemas + API + UI)
2. Prompt builder por dominio alineado con estructura actual de prompts del repo:
   - usar `backend/app/prompts/...` (no duplicar arbol en `services/prompts` sin necesidad)

---

## PR3 - Export avanzado (compatible)

### Regla de compatibilidad
- Conservar endpoint actual:
  - `POST /projects/{project_id}/theories/{theory_id}/export`

### Extension segura
- Agregar parametro `format` opcional (`pdf|pptx|xlsx|png`) con default `pdf`.
- Mantener comportamiento actual para clientes existentes.

---

## 4) Matriz de riesgo y mitigacion

1. Riesgo: romper estado de tareas en teoria.
   - Mitigacion: no tocar contrato de `task_id/status`; agregar tests de polling.
2. Riesgo: incompatibilidad de modelos IA.
   - Mitigacion: reutilizar wrapper existente y solo ampliar.
3. Riesgo: drift de prompts.
   - Mitigacion: unificar en arbol `backend/app/prompts`.
4. Riesgo: cambio de schema sin migracion.
   - Mitigacion: bootstrap Alembic antes de PR1.

## 5) Gate de calidad por PR

Cada PR debe pasar:
1. Compilacion backend.
2. Build frontend.
3. Smoke test de:
   - `POST /generate-theory` => `202`
   - `GET /generate-theory/status/{task_id}` => progreso y finalizacion coherente
4. No regresion en export PDF.

## 6) Definicion de listo (DoD)

1. Funcionalidad nueva activa.
2. Sin ruptura de endpoints existentes.
3. Logs observables por etapa.
4. Documentacion actualizada en `docs/`.
