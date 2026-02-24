# Runbook Implementacion PR2-PR4-PR1-PR3

Fecha y hora de emision: 2026-02-23 14:28:23 -03:00
Proyecto: TheoGen
Ruta aplicada: PR2 -> PR4 -> PR1 -> PR3

## 1. Objetivo

Operar y desplegar de forma segura la optimizacion del pipeline de codificacion y teoria,
con plantillas de dominio y exportes avanzados, manteniendo compatibilidad del contrato API.

## 2. Cambios aplicados

1. PR2 (capabilities + budget)
- Wrapper LLM capability-aware en `backend/app/services/azure_openai.py`.
- Presupuesto dinamico de tokens en `backend/app/utils/token_budget.py`.
- Pruebas en `backend/tests/test_token_budget.py`.

2. PR4 (pipeline escalonado)
- Pipeline por etapas en `backend/app/engines/theory_pipeline.py`.
- Orquestacion async con lock y estado en `backend/app/api/theory.py`.
- Evidencia Qdrant normalizada en `backend/app/services/qdrant_service.py`.

3. PR1 (domain templates)
- Plantillas y prompt builder en:
  - `backend/app/prompts/domain_templates.py`
  - `backend/app/prompts/theory_prompts_v2.py`
  - `backend/app/prompts/prompt_builder.py`
- Integracion en teoria:
  - `backend/app/engines/theory_engine.py`
  - `backend/app/engines/theory_pipeline.py`
- Campo `domain_template`:
  - modelo `backend/app/models/models.py`
  - schemas/API `backend/app/schemas/project.py`, `backend/app/api/projects.py`
  - migration `backend/alembic/versions/20260223_0001_add_domain_template_to_projects.py`
  - UI `frontend/src/app/dashboard/page.tsx`

4. PR3 (export avanzado)
- Generadores:
  - `backend/app/services/export/pptx_generator.py`
  - `backend/app/services/export/xlsx_generator.py`
  - `backend/app/services/export/infographic_generator.py`
- Orquestador y endpoint:
  - `backend/app/services/export_service.py`
  - `backend/app/api/theory.py`
- UI export multi-formato:
  - `frontend/src/components/TheoryViewer/index.tsx`

## 3. Pre-requisitos

1. Variables de entorno cargadas (`.env`) para PostgreSQL, Azure OpenAI, Qdrant y Neo4j.
2. Dependencias instaladas con `backend/requirements.txt` (incluye `python-pptx`, `openpyxl`, `Pillow`, `tiktoken`).
3. Base de datos PostgreSQL accesible.

## 4. Migracion de base de datos

Nota: se agrega `projects.domain_template` NOT NULL con default `generic`.

Comandos sugeridos (desde `backend`):

```powershell
.\.venv\Scripts\python.exe -m alembic -c alembic.ini upgrade head
```

Validacion SQL recomendada:

```sql
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_name = 'projects' AND column_name = 'domain_template';
```

## 5. Validaciones operativas

1. Backend compile

```powershell
.\.venv\Scripts\python.exe -m compileall backend/app
```

2. Test de budget

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_token_budget.py -q
```

3. Frontend build

```powershell
cd frontend
npm run build
```

## 6. Smoke test API

1. Crear proyecto con template:
- `POST /api/projects/` con `domain_template`.

2. Generar teoria:
- `POST /api/projects/{project_id}/generate-theory` -> 202.
- `GET /api/projects/{project_id}/generate-theory/status/{task_id}` hasta `completed|failed`.

3. Exportes:
- `POST /api/projects/{project_id}/theories/{theory_id}/export?format=pdf`
- `...format=pptx`
- `...format=xlsx`
- `...format=png`

## 7. Controles de rendimiento

1. Ajustar concurrencia por entorno:
- `CODING_FRAGMENT_CONCURRENCY`
- `THEORY_INTERVIEW_CONCURRENCY`
- `THEORY_LOCAL_MAX_CONCURRENT_TASKS`

2. Ajustar limites de budget:
- `THEORY_BUDGET_MARGIN_TOKENS`
- `THEORY_BUDGET_MAX_DEGRADATION_STEPS`
- `THEORY_LLM_MAX_OUTPUT_TOKENS`
- `THEORY_LLM_MAX_OUTPUT_TOKENS_LARGE`

3. Ajustar polling:
- `THEORY_STATUS_POLL_HINT_SECONDS`

## 8. Rollback

1. Desactivar uso de templates en frontend (enviar `generic`).
2. Mantener endpoint export en `pdf` (default) sin usar formatos nuevos.
3. Revertir release de backend y frontend a revision anterior.
4. Si se requiere rollback de schema:

```powershell
.\.venv\Scripts\python.exe -m alembic -c alembic.ini downgrade -1
```

(Usar downgrade solo si no hay dependencias funcionales activas sobre `domain_template`.)

## 9. Riesgos residuales

1. Si no se aplica migracion, el campo `domain_template` puede causar fallo en consultas ORM.
2. En modelos externos, cambios de compatibilidad API pueden requerir ampliar heuristicas del wrapper LLM.
3. En cargas extremas, puede requerirse aumentar pool DB o replicas worker.
