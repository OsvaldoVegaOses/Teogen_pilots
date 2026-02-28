# Cierre de pendientes: GraphRAG / Claims / Judge (TheoGen)

Fecha: 2026-02-26  
Proyecto: TheoGen

## 1) Veredicto sobre la hipótesis

Hipótesis evaluada: **"la integración es parcial y aún no se aprovecha a nivel cerebro lógico (GraphRAG/Claims/Judge)"**.

Veredicto:

- **Era correcta como diagnóstico base**.
- Con los cambios aplicados en este ciclo, **ya no está en estado "solo parcial" técnico**, pero sí en **rollout parcial** porque varias capacidades avanzadas quedan controladas por flags.

En términos prácticos: el backend ya tiene las piezas de cerebro lógico, pero su activación en producción depende de la estrategia de flags y datos legacy.

## 2) Aporte real implementado

### Qdrant (seguridad + calidad de recuperación)

- Filtro de alcance reforzado en `backend/app/services/qdrant_service.py`:
  - `project_id` obligatorio en todas las búsquedas (sin fallback inseguro).
  - `owner_id` opcional como doble candado.
- Recuperación con preferencia por `source_type=fragment` y fallback compatible para datos legacy.
- Metadata de evidencia ampliada: `owner_id`, `interview_id`, `source_type`, `created_at`.
- Payload de indexación enriquecido en `backend/app/engines/coding_engine.py` con:
  - `owner_id`, `interview_id`, `fragment_id`, `source_type`, `created_at`.

### GraphRAG guiado por subgrafo

- En `backend/app/engines/theory_pipeline.py`:
  - selección de subgrafo crítico configurable (categorías/edges/puentes),
  - evidencia por nodo y por edge,
  - muestreo determinista con diversidad por entrevistas.
- Controles de costo/latencia:
  - límites de queries y concurrencia (`THEORY_MAX_QDRANT_QUERIES`, `THEORY_QDRANT_RETRIEVAL_CONCURRENCY`).

### Judge determinista + repairs parciales

- `backend/app/engines/theory_judge.py`:
  - gates por evidencia, cobertura y sanity de dominio,
  - gate de balance de consecuencias (`BALANCE_CONSEQUENCES`),
  - métrica de concentración observada por entrevista.
- `backend/app/engines/theory_pipeline.py`:
  - re-muestreo real de evidencia cuando falla cobertura,
  - recuperación dirigida de evidencia material/económica/ambiental cuando falla balance,
  - repairs parciales por sección,
  - modo `THEORY_JUDGE_WARN_ONLY` para pilotos.

### Claim graph auditable en Neo4j

- `backend/app/services/neo4j_service.py`:
  - `batch_sync_claims(...)` para persistir `Claim`, `ABOUT`, `SUPPORTED_BY`,
  - ids deterministas de claim por teoría/sección/orden/texto,
  - `MERGE` para idempotencia,
  - constraint único `Claim.id` best-effort.
- `backend/app/engines/theory_pipeline.py`:
  - sync post-save best-effort con estado persistido en `validation.neo4j_claim_sync`.

### Observabilidad útil para rollout

- Nuevas métricas de calidad/runtime en `validation`:
  - `evidence_index_size`,
  - `distinct_interviews_in_evidence`,
  - `max_share_per_interview`,
  - `judge_fail_reason`,
  - `repairs_triggered_count`,
  - `repairs_success_rate`,
  - latencias (`neo4j_metrics_ms`, `qdrant_retrieval_ms`, `identify_llm_ms`, `paradigm_llm_ms`, `gaps_llm_ms`),
  - `claims_synced_count`, `neo4j_sync_failed`.

## 3) Riesgos del feedback y estado actual

A) **Fallback en Qdrant degrade seguridad/calidad**  
Estado: **mitigado parcialmente**.

- Seguridad: `project_id` no se relaja en fallback (correcto).
- Calidad: fallback legacy puede bajar precisión si faltan `source_type/owner_id` en datos históricos.

B) **Duplicados de Claim en regeneraciones**  
Estado: **mitigado**.

- `MERGE` + `Claim.id` determinístico + constraint de unicidad.

C) **Judge excesivamente estricto bloqueando pilotos**  
Estado: **mitigado**.

- Umbrales configurables + `THEORY_JUDGE_WARN_ONLY`.

D) **Repair sin re-muestreo real**  
Estado: **mitigado**.

- Re-muestreo por cobertura y recuperación dirigida para balance.

E) **Costo/latencia por evidencia ampliada**  
Estado: **mitigado parcialmente**.

- Hay límites y concurrencia configurables.
- Falta observación en producción para ajustar umbrales por carga real.

## 4) Qué sigue para cerrar rollout (sin romper app)

1. Activar flags por etapas:
   - `THEORY_USE_SUBGRAPH_EVIDENCE=true`
   - `THEORY_USE_JUDGE=true` (piloto con `THEORY_JUDGE_WARN_ONLY=true`)
   - `THEORY_SYNC_CLAIMS_NEO4J=true`
   - `THEORY_USE_DETERMINISTIC_GAPS=true`
2. Monitorear métricas nuevas por proyecto durante 1 semana.
3. Pasar `THEORY_JUDGE_WARN_ONLY=false` cuando la tasa de repairs y fallos sea estable.

## 5) Validación ejecutada

Pruebas backend ejecutadas:

- `.\.venv\Scripts\python.exe -m pytest backend/tests -q`
- Resultado: **10 passed**.

## 6) Comentario final de cierre

Estado de cierre técnico:

- **Arquitectura núcleo lógico/semántico**: implementada y operativa (Neo4j auditable + Qdrant trazable + GraphRAG + Judge).
- **Hardening de operación y seguridad**: avanzado (routing determinista, retry/backoff, SLO endpoint, health protegido y sanitizado, hysteresis Judge).

Pendientes explícitos:

1. **Backups programados + restore verificado** (Qdrant/Neo4j) con evidencia de prueba en staging.
2. **Alertas automáticas** conectadas a `/health/dependencies` y `pipeline-slo`.

Futuras mejoras recomendadas:

- Staleness-control incremental para `category_summary` (sync por hash/cambio).
- Endpoint de explain con paths ampliados multi-hop para auditoría avanzada.
- Migración de `@app.on_event("startup")` a lifespan de FastAPI para eliminar deprecations.
