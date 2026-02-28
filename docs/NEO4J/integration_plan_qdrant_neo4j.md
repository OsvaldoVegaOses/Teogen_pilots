# Plan de Integracion de Qdrant y Neo4j en TheoGen

**Ultima actualizacion:** 2026-02-20
**Estado:** Completado en produccion para sincronizacion y teoria (pendientes frontend y pruebas con infraestructura real)

Este documento detalla los pasos para integrar busqueda semantica (Qdrant) y analisis de grafos (Neo4j) en TheoGen.

## 1. Fase 1: Servicios Base y Conexiones (Completada)

- [x] Configuracion en `backend/app/core/settings.py` para variables QDRANT/NEO4J.
- [x] Servicio Qdrant (`backend/app/services/qdrant_service.py`):
  - [x] `ensure_collection`
  - [x] `upsert_vectors`
  - [x] `search_similar`
  - [x] `search_supporting_fragments` (evidencia para teoria)
- [x] Servicio Neo4j (`backend/app/services/neo4j_service.py`):
  - [x] `create_project_node`
  - [x] `create_code_node`
  - [x] `create_fragment_node`
  - [x] `create_category_node`
  - [x] `create_code_fragment_relation`
  - [x] `link_code_to_category`
  - [x] `get_project_network_metrics`

## 2. Fase 2: Sincronizacion de Datos (Completada)

- [x] `coding_engine.py` genera embeddings y sincroniza fragmentos a Qdrant.
- [x] `coding_engine.py` asegura nodo Project en Neo4j antes de sincronizar.
- [x] Se mantiene trazabilidad de embeddings en `Fragment.embedding_synced`.

## 3. Fase 3: Capacidades de Analisis (Completada)

- [x] Endpoint semantico `POST /api/search/fragments`.
- [x] Teoria sin placeholder:
  - [x] `POST /api/projects/{project_id}/generate-theory` usa metricas reales de Neo4j.
  - [x] La teoria incluye `validation.network_metrics_summary`.
  - [x] La teoria incorpora evidencia semantica de Qdrant (`semantic_evidence_top`).

## 4. Endurecimiento Operativo (Completada)

- [x] Startup fail-fast en `backend/app/main.py` (excepto `TESTING=true`).
- [x] Neo4j/Qdrant requeridos en settings (con validacion de integraciones).
- [x] Consistencia defensiva con `MERGE (p:Project ...)` para nodos dependientes.

## 5. Pruebas y Despliegue

- [x] Tests de integracion agregados:
  - [x] `backend/tests/integration/test_neo4j_sync.py`
  - [x] `backend/tests/integration/test_theory_graph_input.py`
- [ ] Pruebas de integracion contra Neo4j/Qdrant reales en entorno dev.
- [ ] Verificacion E2E autenticada en entorno desplegado.

## Registro de avance

| Fecha | Tarea | Estado | Notas |
|---|---|---|---|
| 2026-02-17 | Implementacion de servicios | Completado | Servicios base de Qdrant y Neo4j. |
| 2026-02-17 | Integracion Coding Engine | Completado | Sincronizacion automatica de fragmentos/codigos. |
| 2026-02-17 | Search endpoint | Completado | Endpoint `/api/search/fragments`. |
| 2026-02-20 | Endurecimiento operativo | Completado | Startup checks + settings requeridos. |
| 2026-02-20 | Teoria con grafo real y Qdrant | Completado | Sin placeholder y con evidencia semantica. |
| 2026-02-20 | Tests de integracion | Completado | Nuevos tests en `backend/tests/integration/`. |
