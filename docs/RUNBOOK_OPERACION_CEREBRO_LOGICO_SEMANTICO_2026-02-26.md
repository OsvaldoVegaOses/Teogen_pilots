# Runbook operación: Neo4j lógico + Qdrant semántico

Fecha: 2026-02-26

## 1) Health operativo

- Endpoint base:
  - `GET /health/dependencies`
- Protección recomendada:
  - configurar `HEALTHCHECK_DEPENDENCIES_KEY` y enviar `X-Health-Key`.
- Interpretación:
  - `healthy`: dependencias activas responden.
  - `degraded`: al menos una dependencia activa falla o excede timeout.
- Señales útiles por dependencia:
  - `ok`
  - `latency_ms`
  - `error_code`

## 2) SLO de pipeline de teoría

- Endpoint:
  - `GET /api/projects/{project_id}/theories/pipeline-slo?window=20`
- Campos clave:
  - `latency_p95_ms` / `latency_p50_ms`
  - `quality.claims_without_evidence_total`
  - `reliability.network_sql_fallback_rate`
  - `reliability.evidence_sql_fallback_rate`

## 3) Umbrales sugeridos para alertas

- Dependencias:
  - alerta crítica si `/health/dependencies.status=degraded` por 5 min.
- Latencia p95:
  - `qdrant_retrieval_ms > 3000` por 3 ventanas.
  - `paradigm_llm_ms > 25000` por 3 ventanas.
- Calidad:
  - `claims_without_evidence_total > 0` en teorías nuevas.
- Fiabilidad:
  - `evidence_sql_fallback_rate > 0.3` (degradación recurrente de Qdrant).

## 4) Backups (pendiente de automatización completa)

- Qdrant:
  - habilitar snapshots programados (por colección/proyecto).
  - retención mínima sugerida: 7 diarios + 4 semanales.
- Neo4j:
  - usar backup administrado del proveedor (Aura/managed) y verificar restore.
  - mantener política de retención equivalente.
- Validación mensual:
  - prueba de restore en entorno de staging.

## 5) Judge adaptativo (proyectos chicos)

- Objetivo: evitar bloqueos innecesarios cuando el proyecto aún tiene pocas entrevistas/evidencia.
- Parámetros:
  - `THEORY_JUDGE_ADAPTIVE_THRESHOLDS=true`
  - `THEORY_JUDGE_MIN_INTERVIEWS_FLOOR`
  - `THEORY_JUDGE_MIN_INTERVIEWS_RATIO`
  - `THEORY_JUDGE_BALANCE_MIN_EVIDENCE`
  - `THEORY_JUDGE_STRICT_PROMOTE_MAX_BAD_RUNS`
  - `THEORY_JUDGE_STRICT_DEGRADE_MIN_BAD_RUNS`
  - `THEORY_JUDGE_STRICT_COOLDOWN_RUNS`
  - `THEORY_JUDGE_STRICT_MAX_MODE_CHANGES_PER_WINDOW`
- Observabilidad:
  - revisar en `validation.quality_metrics`:
    - `judge_available_interviews`
    - `judge_min_interviews_configured`
    - `judge_min_interviews_effective`
