# Informe Implementacion: Trazabilidad, Transcripcion y Export de Entrevistas

Fecha y hora: 2026-02-24 11:26:47 -03:00

## Alcance implementado

Se implemento backend para los 3 bloques aprobados:

1. Trazabilidad Libro de Codigos -> evidencia origen.
2. Lectura de transcripcion por entrevista (segmentos).
3. Export de entrevistas con estado de tarea.

## Cambios de codigo

### 1) Endpoint de evidencia por codigo

Archivo: `backend/app/api/codes.py`

- Nuevo endpoint: `GET /api/codes/{code_id}/evidence`
- Incluye:
  - paginacion (`page`, `page_size`)
  - filtros (`interview_id`, `speaker_id`, `source`)
  - orden (`created_at_desc|created_at_asc|confidence_desc`)
- Response enriquecida con:
  - metadata del codigo
  - entrevista fuente
  - fragmento con offsets y timestamps
  - confianza y origen del link

Archivo: `backend/app/schemas/code.py`

- Nuevos schemas:
  - `CodeEvidenceResponse`
  - `CodeEvidenceItem`
  - `CodeEvidenceFragment`
  - `CodeEvidenceInterview`
  - `CodeEvidencePagination`
  - `CodeEvidenceCode`

### 2) Transcripcion navegable por entrevista

Archivo: `backend/app/api/interviews.py`

- Nuevo endpoint: `GET /api/interviews/id/{interview_id}/transcript`
  - filtros: `q`, `speaker_id`
  - paginacion: `page`, `page_size`
  - opcion `include_full_text`

Archivo: `backend/app/schemas/interview.py`

- Nuevos schemas:
  - `InterviewTranscriptResponse`
  - `TranscriptInterviewResponse`
  - `TranscriptPaginationResponse`
  - `TranscriptSegmentResponse`

### 3) Export de entrevistas (async)

Archivo: `backend/app/api/interviews.py`

- Nuevo endpoint: `POST /api/interviews/export` (202)
- Nuevo endpoint: `GET /api/interviews/export/status/{task_id}`
- Nuevo endpoint: `GET /api/interviews/export/download/{task_id}`
- Task store:
  - memoria local + persistencia en Redis (si disponible)

Archivo: `backend/app/services/interview_export_service.py`

- Nuevo servicio de export:
  - `txt`
  - `json`
  - `pdf`
  - `xlsx`

### 4) Anchors en fragmentos desde transcription

Archivo: `backend/app/api/interviews.py`

- `process_transcription` ahora guarda en `Fragment`:
  - `paragraph_index`
  - `start_ms` / `end_ms`
  - `start_offset` / `end_offset` (busqueda del segmento en `full_text`)

### 5) Metadata de trazabilidad en code_fragment_links

Archivo: `backend/app/engines/coding_engine.py`

- En insercion de `code_fragment_links` (single + batch):
  - `source = "ai"`
  - `char_start` / `char_end` inferidos desde evidencia textual si existe (`evidence_text|quote|evidence|text_span`)

### 6) Modelo de datos

Archivo: `backend/app/models/models.py`

- `code_fragment_links`: `char_start`, `char_end`, `source`, `linked_at`
- `fragments`: `paragraph_index`, `start_ms`, `end_ms`

### 7) Migracion Alembic

Archivo: `backend/alembic/versions/20260224_0002_add_fragment_and_code_link_trace_fields.py`

- Agrega columnas nuevas en `fragments` y `code_fragment_links`.
- Crea indices:
  - `idx_code_fragment_links_code_id`
  - `idx_code_fragment_links_fragment_id`
  - `idx_code_fragment_links_code_confidence`
  - `idx_fragments_interview_paragraph`
  - `idx_fragments_interview_created`

## Compatibilidad y routing

Archivo: `backend/app/api/interviews.py`

- Se agrego ruta principal `GET /api/interviews/project/{project_id}`
- Se mantiene `GET /api/interviews/{project_id}` como legacy (oculta en schema), ubicada al final para no bloquear rutas `/export`.

## Verificacion tecnica

- `python -m compileall -q backend/app backend/alembic` ejecutado sin errores.
- Import end-to-end del modulo API no se pudo validar por falta de variables obligatorias (`NEO4J_USER`) en el shell de prueba.

## Siguiente paso operativo

1. Aplicar migracion Alembic `20260224_0002`.
2. Probar endpoints nuevos con datos reales:
   - `/api/codes/{code_id}/evidence`
   - `/api/interviews/id/{interview_id}/transcript`
   - `/api/interviews/export` + status/download
3. Integrar frontend:
   - Libro de codigos -> panel evidencia y deep-link a transcript.
   - Vista entrevista -> transcripcion paginada + export.

