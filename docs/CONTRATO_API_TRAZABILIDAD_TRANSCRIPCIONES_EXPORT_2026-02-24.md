# Contrato API: Trazabilidad de Codigos, Transcripciones y Export de Entrevistas

Fecha: 2026-02-24
Estado: Propuesto (implementable sobre backend actual)

## 1. Objetivo

Definir contratos JSON exactos para:

1. Trazar cada codigo hasta el fragmento/parrafo de origen.
2. Consultar transcripciones por entrevista con navegacion por segmentos.
3. Exportar entrevistas (individual y lote) en formatos descargables.

La propuesta esta alineada con el backend existente:

- `GET /api/codes/{code_id}/fragments` ya existe.
- `GET /api/interviews/{project_id}` ya existe.
- `POST /api/projects/{project_id}/theories/{theory_id}/export` ya existe y sirve como patron para export asincrono + blob.

## 2. Criterios de compatibilidad

1. No romper rutas existentes.
2. Mantener aislamiento multitenant por `owner_id`.
3. Reusar tablas actuales (`fragments`, `code_fragment_links`, `interviews`) con cambios minimos.

Nota de routing: como ya existe `GET /api/interviews/{project_id}`, nuevas rutas por `interview_id` deben usar prefijo estatico (ej: `/api/interviews/id/{interview_id}/...`) para evitar ambiguedad.

## 3. Endpoint A: Evidencia de Codigo (Libro de Codigos -> origen)

### 3.1 Ruta

`GET /api/codes/{code_id}/evidence`

### 3.2 Query params

- `page` (int, opcional, default=1, min=1)
- `page_size` (int, opcional, default=20, max=100)
- `interview_id` (uuid, opcional)
- `speaker_id` (string, opcional)
- `source` (enum opcional: `ai|human|hybrid`)
- `order` (enum opcional: `created_at_desc|created_at_asc|confidence_desc`)

### 3.3 Response 200

```json
{
  "code": {
    "id": "d8b19a72-fef3-4f2f-8f16-20f65f6c6f1b",
    "project_id": "35a0a347-30a8-4bff-a7ec-5e1962f7f721",
    "label": "Maximizacion evaluativa",
    "definition": "Uso de terminos con carga superlativa...",
    "created_by": "ai"
  },
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total": 248,
    "has_next": true
  },
  "items": [
    {
      "link_id": "d8b19a72-fef3-4f2f-8f16-20f65f6c6f1b:3c22e05d-dd93-49aa-9983-3dad7a2829d2",
      "confidence": 0.91,
      "source": "ai",
      "interview": {
        "id": "4a22df28-9a18-4f6f-bf7c-a54d3dd3cf11",
        "participant_pseudonym": "P01",
        "created_at": "2026-02-24T12:11:43Z"
      },
      "fragment": {
        "id": "3c22e05d-dd93-49aa-9983-3dad7a2829d2",
        "paragraph_index": 34,
        "speaker_id": "SPEAKER_01",
        "text": "Nosotros siempre decimos que fue una inundacion terrible...",
        "start_offset": 9421,
        "end_offset": 9540,
        "char_start": 19,
        "char_end": 67,
        "start_ms": 523000,
        "end_ms": 531500,
        "created_at": "2026-02-24T12:15:10Z"
      }
    }
  ]
}
```

### 3.4 Errores

- `404` code no existe o no pertenece al usuario.
- `422` parametros invalidos.

## 4. Endpoint B: Transcripcion de Entrevista (lectura y deep-link)

### 4.1 Ruta

`GET /api/interviews/id/{interview_id}/transcript`

### 4.2 Query params

- `include_full_text` (bool, default=false)
- `q` (string, opcional: filtro simple de busqueda en segmentos)
- `speaker_id` (string, opcional)
- `page` (int, default=1)
- `page_size` (int, default=200, max=1000)

### 4.3 Response 200

```json
{
  "interview": {
    "id": "4a22df28-9a18-4f6f-bf7c-a54d3dd3cf11",
    "project_id": "35a0a347-30a8-4bff-a7ec-5e1962f7f721",
    "participant_pseudonym": "P01",
    "transcription_status": "completed",
    "transcription_method": "axial-speech",
    "language": "es"
  },
  "pagination": {
    "page": 1,
    "page_size": 200,
    "total_segments": 618,
    "has_next": true
  },
  "segments": [
    {
      "fragment_id": "3c22e05d-dd93-49aa-9983-3dad7a2829d2",
      "paragraph_index": 34,
      "speaker_id": "SPEAKER_01",
      "text": "Nosotros siempre decimos que fue una inundacion terrible...",
      "start_offset": 9421,
      "end_offset": 9540,
      "start_ms": 523000,
      "end_ms": 531500,
      "created_at": "2026-02-24T12:15:10Z"
    }
  ],
  "full_text": null
}
```

Si `include_full_text=true`, `full_text` contiene el texto completo.

### 4.4 Errores

- `404` entrevista no encontrada/no autorizada.
- `409` transcripcion no completada.

## 5. Endpoint C: Export de Entrevistas

### 5.1 Crear export

Ruta: `POST /api/interviews/export`

Request:

```json
{
  "project_id": "35a0a347-30a8-4bff-a7ec-5e1962f7f721",
  "interview_ids": [
    "4a22df28-9a18-4f6f-bf7c-a54d3dd3cf11"
  ],
  "scope": "selected",
  "format": "pdf",
  "include_metadata": true,
  "include_codes": true,
  "include_timestamps": true,
  "language": "es"
}
```

Reglas:

- `scope` enum: `selected|all_project`.
- Si `scope=all_project`, `interview_ids` se ignora.
- `format` enum inicial: `txt|json|pdf|docx|xlsx`.

Response 202:

```json
{
  "task_id": "b2d44bba-8dea-4d42-9486-0efd93f76ef2",
  "status": "queued",
  "created_at": "2026-02-24T13:10:00Z"
}
```

### 5.2 Estado export

Ruta: `GET /api/interviews/export/status/{task_id}`

Response 200:

```json
{
  "task_id": "b2d44bba-8dea-4d42-9486-0efd93f76ef2",
  "status": "completed",
  "progress": 100,
  "message": "Export completed",
  "result": {
    "blob_path": "exports/interviews/35a0.../interviews_export_20260224_131005.pdf",
    "download_url": "https://...sas...",
    "expires_at": "2026-02-24T14:10:05Z",
    "content_type": "application/pdf",
    "size_bytes": 1249934
  }
}
```

### 5.3 Descargar directo (opcional)

Ruta: `GET /api/interviews/export/download/{task_id}`

Comportamiento:

- `302` a URL SAS si `completed`.
- `409` si no esta lista.

## 6. Cambios minimos de esquema (PostgreSQL)

Tabla `code_fragment_links`:

1. `char_start INTEGER NULL` (offset relativo al fragmento)
2. `char_end INTEGER NULL` (offset relativo al fragmento)
3. `source VARCHAR(20) NULL` (`ai|human|hybrid`)
4. `linked_at TIMESTAMP NULL DEFAULT now()`

Indices:

1. `idx_code_fragment_links_code_id` en `(code_id)`
2. `idx_code_fragment_links_fragment_id` en `(fragment_id)`
3. `idx_code_fragment_links_code_confidence` en `(code_id, confidence DESC)`

Tabla `fragments`:

1. `paragraph_index INTEGER NULL`
2. `start_ms INTEGER NULL`
3. `end_ms INTEGER NULL`

Indices:

1. `idx_fragments_interview_paragraph` en `(interview_id, paragraph_index)`
2. `idx_fragments_interview_created` en `(interview_id, created_at)`

Notas:

- `start_offset/end_offset` ya existen y se mantienen.
- Campos nuevos son opcionales para no romper historico.

## 7. Reglas de seguridad y tenancy

Todos los endpoints deben validar `owner_id` via join con `projects`.

1. `codes` -> `codes.project_id = projects.id AND projects.owner_id = user_uuid`
2. `interviews` -> `interviews.project_id = projects.id AND projects.owner_id = user_uuid`
3. `exports` -> validar `project_id` y cada `interview_id` contra ese proyecto del usuario

## 8. Reglas de performance

1. Endpoint A y B obligatoriamente paginados.
2. `page_size` tope duro para evitar payloads masivos.
3. Export siempre asincrono si `scope=all_project` o `interview_ids > 3`.
4. Reusar Redis/task pipeline ya existente de teoria para estado de export.

## 9. Plan de implementacion (orden)

1. Migracion SQL minima (campos + indices).
2. Endpoint A (`/codes/{code_id}/evidence`) + schema de respuesta.
3. Endpoint B (`/interviews/id/{interview_id}/transcript`) + filtros/paginacion.
4. Endpoint C (`/interviews/export` + status/download).
5. Integracion frontend:
   - Libro de Codigos: panel evidencia + abrir en transcripcion.
   - Entrevistas: vista transcripcion + buscador + export.

## 10. Definicion de hecho (DoD)

1. Desde Libro de Codigos, usuario abre evidencia y navega al parrafo origen en <= 2 clics.
2. Entrevistas accesibles por segmentos con `speaker/timestamp`.
3. Export de una entrevista funciona sin timeout.
4. Export de lote funciona asincrono con `task_id` y descarga SAS.
5. Tests de autorizacion cubren lectura cruzada entre usuarios (debe fallar).

