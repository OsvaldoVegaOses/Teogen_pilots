# TheoGen

Backend de analisis cualitativo con integracion de Neo4j (grafo) y Qdrant (busqueda semantica).

## Requisitos operativos

- `NEO4J_URI`
- `NEO4J_USER`
- `NEO4J_PASSWORD`
- `QDRANT_URL`

Notas:
- En runtime normal, estas integraciones son obligatorias.
- En pruebas (`TESTING=true`) se omiten los startup checks remotos para permitir mocks.

## Flujo de procesamiento

1. Se transcribe entrevista y se crean `Fragment` en Postgres.
2. `POST /api/codes/auto-code/{interview_id}` ejecuta codificacion AI.
3. Cada fragmento codificado se sincroniza a:
   - Qdrant: embedding + payload (`text`, `project_id`, `codes`).
   - Neo4j: nodos/relaciones (`Project`, `Code`, `Fragment`, `APPLIES_TO`).
4. `POST /api/projects/{project_id}/generate-theory` consume:
   - Metricas reales del grafo (`counts`, `category_centrality`, `category_cooccurrence`).
   - Evidencia semantica de Qdrant (`semantic_evidence_top`).

## Verificacion E2E sugerida

1. Ejecutar `POST /api/codes/auto-code/{interview_id}`.
2. Ejecutar `POST /api/projects/{project_id}/generate-theory`.
3. Verificar en respuesta: `validation.network_metrics_summary` y `validation.network_metrics_summary.semantic_evidence_top`.

## Tests

- `backend/tests/integration/test_neo4j_sync.py`
- `backend/tests/integration/test_theory_graph_input.py`
