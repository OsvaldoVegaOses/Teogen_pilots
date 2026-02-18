# Plan de Integración de Qdrant y Neo4j en TheoGen

**Última actualización:** 2026-02-17
**Estado:** ✅ Fase 1, 2 y 3 Completadas
**Autores:** Asistente (DeepMind) y Osvaldo

Este documento detalla los pasos para integrar **búsqueda semántica (Qdrant)** y **análisis de grafos (Neo4j)** en TheoGen. El objetivo es potenciar el motor de codificación y teoría sin afectar la funcionalidad actual.

## 1. Fase 1: Servicios Base y Conexiones (✅ Completada)

Objetivo: Establecer conexiones a las bases de datos externas de forma segura y robusta.

- [x] **Configuración del Entorno**
    - [x] Verificar definiciones en `backend/app/core/settings.py` (variables QDRANT/NEO4J).
    - [x] Verificar dependencias en `backend/requirements.txt` (`qdrant-client`, `neo4j`).
    - [x] Asegurar variables en `.env` (QDRANT_API_KEY, NEO4J_PASSWORD).

- [x] **Servicio Qdrant (`services/qdrant_service.py`)**
    - [x] Implementar clase `FoundryQdrantService`.
    - [x] Método `initialize_collection`: Crear colección si no existe.
    - [x] Método `upsert_vectors`: Insertar embeddings + metadatos (ProjectID, CodeID).
    - [x] Método `search_similar`: Búsqueda por vector (kNN).
    - [x] Manejo de errores tolerante a fallos (log warning si falla, no crash).

- [x] **Servicio Neo4j (`services/neo4j_service.py`)**
    - [x] Implementar clase `FoundryGraphService`.
    - [x] Método `create_code_node`: Crear nodo (:Code).
    - [x] Método `create_fragment_node`: Crear nodo (:Fragment).
    - [x] Método `create_relationship`: (:Code)-[:APPLIES_TO]->(:Fragment).
    - [x] Manejo de errores tolerante a fallos.

## 2. Fase 2: Sincronización de Datos (Coding Engine) (✅ Completada)

Objetivo: Alimentar las bases de datos de conocimiento de forma automática y asíncrona.

- [x] **Generación de Embeddings (Coding Engine)**
    - [x] Modificar `coding_engine.py` para generar embeddings de fragmentos usando `FoundryOpenAI`.
    - [x] Usar `BackgroundTasks` de FastAPI para subir vectores a Qdrant tras codificación exitosa.
    - [x] Actualizar bandera `binding_synced=True` en Postgres.

- [x] **Construcción del Grafo (Coding Engine)**
    - [x] Usar `BackgroundTasks` para crear nodos y relaciones en Neo4j tras codificación.
    - [x] Sincronizar Jerarquías: (:Category)-[:CONTAINS]->(:Code).

## 3. Fase 3: Nuevas Capacidades (Search & Analysis) (✅ Completada)

Objetivo: Explotar los datos para mejorar la teorización y sugerencias.

- [x] **Endpoint de Búsqueda Semántica (`api/search.py`)**
    - [x] `POST /api/search/fragments`: Recibe texto, vectoriza y consulta Qdrant.
    - [x] Retorna fragmentos similares de otros proyectos (si aplica) o del mismo.

- [ ] **Análisis de Red (Theory Engine)** (Pendiente)
    - [ ] Integrar Neo4j en `theory_engine.py`.
    - [ ] Calcular PageRank/Centralidad para sugerir Categoría Central automáticamente.
    - [ ] Visualizar el grafo real en el frontend (futuro).

## 4. Fase 4: Pruebas y Despliegue

- [ ] **Testing**
    - [ ] Unit tests para servicios con mocks.
    - [ ] Integration tests con bases de datos reales (dev).
    - [ ] Verificar tolerancia a fallos: ¿Qué pasa si Qdrant está caído? (La app debe seguir funcionando).

- [ ] **Documentación**
    - [ ] Actualizar README.md con requisitos de Qdrant/Neo4j.
    - [ ] Documentar nuevos endpoints en OpenAPI/Swagger.

---

## Registro de Avance

| Fecha | Tarea | Estado | Notas |
|---|---|---|---|
| 2026-02-17 | Implementación de Servicios | ✅ Completado | `qdrant_service.py`, `neo4j_service.py` creados. |
| 2026-02-17 | Integración Coding Engine | ✅ Completado | Sincronización automática a Qdrant y Neo4j implementada. |
| 2026-02-17 | Search Endpoint | ✅ Completado | Endpoint `/api/search` implementado. |
