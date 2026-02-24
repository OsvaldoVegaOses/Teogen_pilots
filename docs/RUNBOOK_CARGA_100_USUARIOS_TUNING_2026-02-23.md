# Runbook Cierre Punto 5 - Prueba de Carga 100 Usuarios y Tuning

Fecha: 2026-02-23

## 1. Objetivo

Validar el flujo `generate-theory` con 100 usuarios concurrentes y dejar un perfil de tuning reproducible.

## 2. Script de carga

Archivo:
- `backend/scripts/load_test_theory_api.py`

Capacidades:
- simula usuarios concurrentes contra:
  - `POST /api/projects/{project_id}/generate-theory`
  - `GET /api/projects/{project_id}/generate-theory/status/{task_id}`
- distribuye usuarios round-robin sobre multiples `project_id`
- reporta `p50/p95/max` de latencia de enqueue y tiempo total
- reporta conteo por estado (`completed`, `failed`, `timeout`, etc.)

## 3. Ejecucion sugerida

Desde raiz del repo:

```powershell
.\.venv\Scripts\python.exe backend\scripts\load_test_theory_api.py \
  --base-url "https://<backend-domain>" \
  --token "<bearer-token>" \
  --project-ids <project-id-1> <project-id-2> <project-id-3> <project-id-4> <project-id-5> \
  --users 100 \
  --spawn-interval 0.15 \
  --poll-interval 5 \
  --pipeline-timeout 1200 \
  --output docs\load_test_100_users_results.json
```

## 4. Criterios de aceptacion recomendados

1. `enqueue p95 < 1500 ms`
2. `completed >= 95%`
3. `failed + timeout <= 5%`
4. sin errores recurrentes `unsupported_parameter` en logs backend

## 5. Perfil de tuning recomendado

Ajustes iniciales:
- `THEORY_LOCAL_MAX_CONCURRENT_TASKS=4`
- `THEORY_INTERVIEW_CONCURRENCY=3`
- `CODING_FRAGMENT_CONCURRENCY=8`
- `THEORY_STATUS_POLL_HINT_SECONDS=5`
- `DB_POOL_SIZE=20`
- `DB_MAX_OVERFLOW=10`

Reglas de ajuste:
1. Si sube `timeout` de pipelines:
- bajar `THEORY_LOCAL_MAX_CONCURRENT_TASKS` a `3`
- subir `THEORY_STATUS_POLL_HINT_SECONDS` a `6-8`

2. Si sube latencia DB o errores de pool:
- subir `DB_POOL_SIZE` a `30`
- subir `DB_MAX_OVERFLOW` a `20`

3. Si aparecen 429 o saturacion de LLM:
- bajar `CODING_FRAGMENT_CONCURRENCY` a `6`
- bajar `THEORY_INTERVIEW_CONCURRENCY` a `2`

## 6. Salida esperada

El script genera JSON con:
- `status_counts`
- `enqueue_ms` (`avg`, `p50`, `p95`, `max`)
- `total_ms` (`avg`, `p50`, `p95`, `max`)
- listado parcial de errores

## 7. Nota operativa

La prueba de carga debe ejecutarse en entorno de staging/produccion controlado.
No ejecutar 100 usuarios simultaneos en desarrollo local.
