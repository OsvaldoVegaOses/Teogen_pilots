# Runbook: Theory Task Stuck At 25% ("auto_code")

Fecha/Hora (local): 2026-02-24 19:54:41 -03:00

## Sintoma
- En UI: progreso fijo en `25%` y mensaje tipo "Auto-codificando entrevistas..."
- En API: `GET /api/projects/{project_id}/generate-theory/status/{task_id}` retorna `status=running`, `step=auto_code`, `progress=25` repetidamente.
- En logs de Container Apps: solo aparecen access logs (OPTIONS/GET 200), sin error de aplicacion visible.

## Diagnostico (codigo)
- El `25%` es un punto fijo al inicio de auto-codificacion:
  - `backend/app/engines/theory_pipeline.py` marca `auto_code` en `25` y luego ejecuta auto-coding de entrevistas completadas.
- Antes del parche, el stage `auto_code` corria `asyncio.gather(...)` sobre entrevistas:
  - Si 1 entrevista quedaba bloqueada (LLM/embeddings/Qdrant/Neo4j), `gather` nunca terminaba.
  - No habia progreso incremental dentro del stage, por lo que UI quedaba "pegada" en 25%.
- Adicional: `generate_embeddings(...)` no tenia timeout; si el upstream se quedaba colgado, el task quedaba indefinido.
- Adicional: el runtime estaba mostrando access logs pero no `logger.info` de la app (root logger no estaba forzado a INFO).

## Fix Implementado (parche)
- Timeouts + retries + batching en embeddings:
  - `backend/app/services/azure_openai.py`
  - Configurable via settings:
    - `AI_EMBEDDINGS_TIMEOUT_SECONDS`
    - `AI_EMBEDDINGS_MAX_RETRIES`
    - `AI_EMBEDDINGS_BATCH_SIZE`
- Guardas de timeout en writes a Qdrant y sync a Neo4j:
  - `backend/app/engines/coding_engine.py`
  - Configurable:
    - `CODING_QDRANT_UPSERT_TIMEOUT_SECONDS`
    - `CODING_NEO4J_SYNC_TIMEOUT_SECONDS`
- Auto-code por entrevistas con progreso incremental y timeout por entrevista:
  - `backend/app/engines/theory_pipeline.py`
  - Cambios:
    - `asyncio.as_completed(...)` para avanzar progreso 25% -> 40% segun entrevistas completadas
    - `asyncio.wait_for(..., THEORY_AUTOCODE_INTERVIEW_TIMEOUT_SECONDS)` por entrevista
    - fallas parciales no bloquean el resto; se loggea warning y el pipeline valida minimo de categorias mas adelante
- Log de aplicacion visible en Container Apps:
  - `backend/app/main.py` ahora fuerza root logger a `INFO` (o `APP_LOG_LEVEL`)
- Cancelacion segura (local/celery):
  - `backend/app/api/theory.py`
  - Nuevo endpoint:
    - `POST /api/projects/{project_id}/generate-theory/cancel/{task_id}`
  - En local mode: cancela el `asyncio.Task` si sigue vivo (best-effort).
  - En celery: `revoke(..., terminate=False)` best-effort.

## Como operar / recuperar
1. Ver estado del task:
   - `GET /api/projects/{project_id}/generate-theory/status/{task_id}`
   - Revisar `step`, `progress`, `updated_at`, `error` / `error_code`.
2. Si el task quedo pegado con versiones antiguas:
   - Usar cancelacion (requiere deploy del parche):
     - `POST /api/projects/{project_id}/generate-theory/cancel/{task_id}`
   - Luego reintentar `POST /api/projects/{project_id}/generate-theory`.
3. Revisar logs de app (con parche):
   - Buscar tags:
     - `[theory]`
     - `[theory_stage]`
     - `[coding]`
4. Si vuelve a ocurrir:
   - Subir temporalmente `THEORY_INTERVIEW_CONCURRENCY` o bajar `CODING_FRAGMENT_CONCURRENCY` si hay rate-limit.
   - Ajustar timeouts:
     - si fallan por timeout pero completan, subir `THEORY_AUTOCODE_INTERVIEW_TIMEOUT_SECONDS`.

