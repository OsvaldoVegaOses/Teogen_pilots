# Plan ejecutable: Neo4j cerebro lógico + Qdrant cerebro semántico

Fecha: 2026-02-26

## Objetivo de cierre

Consolidar definitivamente:

- **Neo4j** como núcleo lógico auditable (estructura, claims, explainability).
- **Qdrant** como núcleo semántico trazable (recuperación focalizada y segura).

## Fase 1 (ejecutada en este ciclo)

### 1.1 Explainability de Claims (Neo4j-first)

Estado: **Completado**

- Se agregó endpoint:
  - `GET /api/projects/{project_id}/theories/{theory_id}/claims/explain`
- Mejoras:
  - paginación por `limit`/`offset`,
  - filtros por `section` y `claim_type`,
  - metadatos de página: `total`, `has_more`.
- Lógica:
  - Intenta leer paths desde Neo4j (`Claim -> ABOUT -> SUPPORTED_BY -> Fragment`).
  - Si no hay datos en Neo4j, cae a fallback desde `theory.model_json + validation.evidence_index`.
- Archivos:
  - `backend/app/api/theory.py`
  - `backend/app/services/neo4j_service.py`
  - `backend/app/schemas/theory.py`

### 1.2 Validación automática de endpoint

Estado: **Completado**

- Tests agregados:
  - fallback validation-first
  - preferencia por Neo4j cuando existen Claims
- Archivo:
  - `backend/tests/test_theory_api.py`

### 1.3 Integración frontend (ver evidencia por claim)

Estado: **Completado**

- `TheoryViewer` consume endpoint explain con:
  - filtros `section` y `claim_type`,
  - paginación `limit/offset`,
  - navegación `Anterior/Siguiente`,
  - apertura de fragmento en transcripción.
- Persistencia en Dashboard:
  - estado por teoría (`section`, `claim_type`, `page`, `expanded`) en `localStorage`,
  - estado global (`selectedProjectId`, `activeTab`) en `localStorage`,
  - acción `Reset UI` con modal de alcance (teoría activa, dashboard o todo),
  - restauración automática al volver a abrir la teoría.
- Archivo:
  - `frontend/src/components/TheoryViewer/index.tsx`
  - `frontend/src/app/dashboard/page.tsx`

## Fase 2 (ejecución parcial en este ciclo)

### 2.1 Qdrant en dos niveles (coarse -> fine)

Estado: **Parcialmente completado**

- Agregar `source_type=category_summary` y `source_type=claim`.
- Pipeline:
  1) recuperar summaries por subgrafo,
  2) drill-down a fragmentos.
- Métrica esperada:
  - menor latencia/prompt size manteniendo cobertura.

Implementado en este ciclo:

- Coarse-to-fine retrieval en pipeline:
  - primero consulta `source_type=category_summary`,
  - luego consulta `source_type=fragment`.
- Sync best-effort de vectors `category_summary` por proyecto antes del retrieval.
- Sync opcional de vectors `claim` con flag:
  - `THEORY_SYNC_CLAIMS_QDRANT`.

### 2.2 Routing previo al LLM

Estado: **Completado (flagged rollout)**

Implementado en este ciclo:

- Flag de activación:
  - `THEORY_USE_DETERMINISTIC_ROUTING`.
- Plan de routing persistido en `validation.deterministic_routing`:
  - `project_state -> postgresql`,
  - `network_metrics -> neo4j` con fallback `sql`,
  - `semantic_evidence -> qdrant_subgraph|qdrant_basic` con fallback `sql`,
  - `judge -> python_rules`,
  - `llm_paradigm -> model_router|reasoning_advanced` según `use_model_router`.
- Ejecución determinista con degradación segura:
  - si falla Neo4j en métricas, fallback SQL sin romper generación,
  - si Qdrant no entrega evidencia, fallback SQL por fragmentos codificados + muestreo diverso.

## Fase 3 (hardening final)

### 3.1 Judge strict por cohortes

Estado: **Parcialmente completado**

- Piloto: `THEORY_JUDGE_WARN_ONLY=true`
- Producción: `THEORY_JUDGE_WARN_ONLY=false`
- Gate de salida:
  - `claims_without_evidence = 0`
  - `interviews_covered >= min_interviews`

Implementado en este ciclo:

- Política de rollout por cohortes con bucket determinístico por `project_id`.
- Auto-promoción a strict cuando hay estabilidad en ventana reciente.
- Endpoint de observabilidad:
  - `GET /api/projects/{project_id}/theories/judge-rollout`
- Nuevos parámetros:
  - `THEORY_JUDGE_STRICT_COHORT_PERCENT`
  - `THEORY_JUDGE_STRICT_WINDOW`
  - `THEORY_JUDGE_STRICT_MIN_THEORIES`
  - `THEORY_JUDGE_STRICT_MAX_BAD_RUNS`
- Resultado guardado en `validation.judge_rollout`.
- Judge con thresholds adaptativos para proyectos con pocos datos:
  - reduce `min_interviews` efectivo según entrevistas disponibles del proyecto,
  - degrada `BALANCE_CONSEQUENCES` a warning cuando la evidencia total es muy baja,
  - mantiene modo estricto en proyectos con cobertura suficiente.
- Hysteresis anti-flapping en rollout Judge:
  - promoción/degradación con umbrales separados,
  - cooldown por número de corridas,
  - límite de cambios de modo por ventana.
- Parámetros nuevos:
  - `THEORY_JUDGE_ADAPTIVE_THRESHOLDS`
  - `THEORY_JUDGE_MIN_INTERVIEWS_FLOOR`
  - `THEORY_JUDGE_MIN_INTERVIEWS_RATIO`
  - `THEORY_JUDGE_BALANCE_MIN_EVIDENCE`
  - `THEORY_JUDGE_STRICT_PROMOTE_MAX_BAD_RUNS`
  - `THEORY_JUDGE_STRICT_DEGRADE_MIN_BAD_RUNS`
  - `THEORY_JUDGE_STRICT_COOLDOWN_RUNS`
  - `THEORY_JUDGE_STRICT_MAX_MODE_CHANGES_PER_WINDOW`

### 3.2 Operación y resiliencia

Estado: **Parcialmente completado**

- Backups automáticos Qdrant/Neo4j
- Alertas SLO y latencias p95
- Retry/backoff + fallback degradado documentado

Implementado en este ciclo:

- Qdrant con retry/backoff configurable en búsquedas semánticas:
  - `QDRANT_SEARCH_MAX_RETRIES`
  - `QDRANT_SEARCH_BACKOFF_SECONDS`
- Healthcheck operativo de dependencias:
  - `GET /health/dependencies`
  - reporta estado `healthy|degraded`, latencia y `error_code` por `neo4j` y `qdrant`.
  - soporta protección por header cuando se configura `HEALTHCHECK_DEPENDENCIES_KEY`.
- Timeout configurable para healthcheck profundo:
  - `HEALTHCHECK_TIMEOUT_SECONDS`.
- Endpoint SLO por proyecto (base para alertas p95):
  - `GET /api/projects/{project_id}/theories/pipeline-slo?window=20`
  - entrega `latency_p95_ms`, `latency_p50_ms`, tasas de fallback SQL y fallas de sync.

Pendiente para cerrar 3.2 al 100%:

- Automatizar backups externos (Qdrant snapshots + respaldo Neo4j administrado).
- Conectar alertas sobre `pipeline-slo` y `/health/dependencies` (SLO + dependencia degradada).

Pendiente acordado (sin implementar en este ciclo):

- Automatizar backups programados (Qdrant/Neo4j) con verificación de restore.

## Secuencia de rollout recomendada (flags)

1. `THEORY_USE_SUBGRAPH_EVIDENCE=true`
2. `THEORY_USE_JUDGE=true`
3. `THEORY_SYNC_CLAIMS_NEO4J=true`
4. `THEORY_USE_DETERMINISTIC_GAPS=true`
5. `THEORY_JUDGE_WARN_ONLY=false` (solo tras estabilidad)

## Criterios de aceptación final

- Explainability disponible por API con `source=neo4j` en proyectos sincronizados.
- `claims_without_evidence = 0` en teorías nuevas.
- Cobertura mínima de entrevistas cumplida por configuración.
- Sin fuga multi-tenant en búsquedas semánticas (scope por `project_id` siempre).

## Cierre y próximos pasos

- Cierre actual: arquitectura y hardening principal completados para operar en producción controlada por flags.
- Pendiente crítico para cerrar 100% de operación:
  - backups programados de Qdrant/Neo4j + restore validado.
- Mejora siguiente recomendada:
  - alertas automáticas sobre degradación de dependencias y p95 de pipeline.
