# Informe tecnico: Aporte de Qdrant para RAG trazable y util en TheoGen

Fecha: 2026-02-26  
Proyecto: TheoGen

Nota de lectura (PowerShell): si ves caracteres raros al hacer `Get-Content`, usa `Get-Content -Encoding utf8`.

## 1) Objetivo: pasar de "evidencia suelta" a evidencia trazable y util

En TheoGen, Qdrant debe ser el motor de recuperacion semantica del que dependen:

- la teorizacion (central category + paradigma + brechas)
- los informes (citas, trazabilidad, explicabilidad)

Pero para que el RAG sea "bien hecho" en este dominio, Qdrant debe operar por **unidades metodologicas** y estar **guiado por grafo** (Neo4j).

## 2) Estado actual en el repo (baseline)

### 2.1 Que hace hoy Qdrant en TheoGen

- Se indexan **fragmentos** en Qdrant con embedding y payload:
  - `text`
  - `project_id`
  - `codes` (labels de codigo)
  - (id del punto == `fragment_id`)
  - Implementacion: `backend/app/engines/coding_engine.py`

- La teoria usa Qdrant para traer evidencia semantica (top hits) para algunas categorias top (centralidad):
  - `qdrant_service.search_supporting_fragments(...)`
  - Implementacion: `backend/app/engines/theory_pipeline.py`, `backend/app/services/qdrant_service.py`

### 2.2 Que falta para que sea RAG "trazable"

Faltan (o estan incompletos) estos elementos:

- Payload suficiente para trazabilidad metodologica:
  - `interview_id` (para cobertura y diversidad de fuentes)
  - `source_type` (fragment vs resumen de categoria vs claim)
  - `timestamp`/`created_at` (para analisis temporal y auditoria)
  - (recomendado) `owner_id` (defensa extra multi-tenant)
- Recuperacion por etapas (hierarquica):
  - primero "category summaries" para seleccionar que vale la pena,
  - luego drill-down a fragmentos.
- Recuperacion guiada por grafo:
  - Neo4j decide que subgrafo importa,
  - Qdrant trae evidencia solo para ese subgrafo.
- Resiliencia operacional:
  - retries/backoff/circuit-breaker (evitar que teorizacion "se caiga" por Qdrant),
  - fallback degradado (Neo4j + Postgres) si Qdrant falla.

## 3) RAG por unidad metodologica (no por documento)

En TheoGen la unidad no es "documento"; es:

1) Fragmento de entrevista (evidencia primaria)
2) Codigo (etiqueta / concepto de bajo nivel)
3) Categoria (concepto emergente de nivel superior)
4) Relacion (co-ocurrencia / camino / edge critico en Neo4j)
5) Claim (unidad auditable del informe: condicion/accion/consecuencia/proposicion/brecha)

### 3.1 Propuesta: vectorizar 3 tipos de "source_type"

Mantener fragmentos (ya) y agregar:

A) `category_summary`

- Vectoriza un resumen por categoria, construido desde evidencia real:
  - top fragmentos por categoria (no inventado)
  - opcional: definicion de categoria + codigos asociados
- Uso: "RAG por etapas" (primero recuperas que categorias son relevantes, luego fragmentos)

B) `claim`

- Vectoriza claims generados (proposiciones/condiciones/acciones/consecuencias):
  - ayuda a: (i) encontrar claims similares entre proyectos/versiones, (ii) detectar duplicados, (iii) contrastar claims con evidencia nueva
- Uso: validacion y mejora incremental ("si ya dijimos X, que evidencia nueva aparece?")

C) `fragment` (ya existe)

- Permanece como evidencia primaria.

### 3.2 Diseno recomendado de payload (minimo viable)

Payload minimo por punto:

- `project_id` (obligatorio)
- `source_type` = `fragment|category_summary|claim` (obligatorio)
- `owner_id` (recomendado; defensa extra)
- `interview_id` (obligatorio para `fragment`; opcional para otros)
- `fragment_id` (cuando aplique; para `fragment` coincide con point id)
- `category_id` (para `category_summary`; opcional para fragment si se puede derivar)
- `code_ids` y/o `category_ids` (arrays keyword, si se quiere filtrar por subgrafo)
- `created_at` o `ts`
- `run_id` (si hay pipeline por runs)

Texto para embedding:

- `fragment`: `fragment.text`
- `category_summary`: `"{category_name}. {definition}. Evidencia: ..."`
- `claim`: texto canonicamente estructurado ("Si X y Y, entonces Z, porque M.")

## 4) Recuperacion guiada por grafo (Neo4j define, Qdrant evidencia)

Principio: Neo4j es el "cerebro logico" (selecciona caminos/nodos criticos) y Qdrant es el "cerebro semantico" (trae evidencia concreta).

### 4.1 Flujo recomendado (Graph-guided RAG)

Paso 0 (Neo4j): seleccionar subgrafo critico

- categoria central + vecinos fuertes
- edges top por co-ocurrencia/peso
- huecos (clusters no representados, falta contraste)

Paso 1 (Qdrant): evidencia por nodos

- para cada categoria del subgrafo:
  - buscar `category_summary` relevante (si existe)
  - luego buscar `fragment` con filtros por `project_id` y opcionalmente por `category_ids/code_ids`

Paso 2 (Qdrant): evidencia por edges

- para edges top (A--B):
  - query combinada "A + B" y filtrar a fragmentos que contengan ambos (si hay payload para eso)

Paso 3 (Contraste)

- si Neo4j detecta comunidad vecina o hueco:
  - buscar fragmentos en categorias "vecinas" para contra-evidencia o contraste

Resultado:

- menos consultas
- evidencia mas relevante
- menos ruido
- menos riesgo de "consecuencias raras" (porque el universo de evidencia esta guiado por grafo)

### 4.2 Por que esto reduce tokens y mejora relevancia

- Los `category_summary` permiten "seleccion semantica" de alto nivel sin cargar decenas de fragmentos.
- El drill-down a fragmentos se hace solo para categorias/edges que realmente importan.
- El LLM recibe contexto compacto + evidencia focalizada + trazabilidad (ids).

## 5) Alta disponibilidad y latencia (minimo viable en Azure)

Objetivo practico: evitar que la teorizacion falle cuando Qdrant no responde y mantener latencias razonables (LatAm <-> East US).

### 5.1 Despliegue pragmatico (MVP hoy)

Si el backend corre en East US:

- poner Qdrant en la misma region (East US) para minimizar saltos.
- no necesitas multi-zona inmediata si el costo es critico, pero si necesitas:
  - backups/snapshots automaticos
  - healthchecks
  - retries con backoff y timeouts
  - modo fallback degradado

### 5.2 AKS vs Container Apps (realidad stateful)

- Qdrant es stateful: AKS suele ser mas comodo (StatefulSet + PV).
- En Container Apps se puede operar, pero la experiencia suele ser mas facil en AKS para discos, snapshots y operaciones.

Recomendacion MVP:

- 1 replica + backups automaticos si costo manda
- si necesitas HA: Qdrant cluster (3 nodos) + PV (y considerar ZRS si aplica)

### 5.3 Resiliencia en aplicacion (debe existir aunque haya HA)

Imprescindible:

- timeouts estrictos en llamadas a Qdrant
- retries con backoff (limitados)
- circuit breaker (si hay falla sostenida, no seguir golpeando)
- fallback: si falla Qdrant, usar Neo4j + Postgres para evidencia reducida

En TheoGen hoy ya hay timeouts alrededor de upsert/sync; el mismo patron aplica a retrieval de evidencia.

## 6) Multi-tenencia: coleccion unica + filtros obligatorios (y alternativa pragmatica)

### 6.1 Recomendacion "coleccion unica"

Practica recomendada para multi-tenant a mediano plazo:

- una sola coleccion
- **filtro obligatorio** por `project_id` (y opcional `owner_id` como doble candado)
- `source_type` para mezclar unidades metodologicas en el mismo indice (fragment/summary/claim)

Ventajas:

- operacion mas simple (menos colecciones)
- mejor reuse de indices y tuning
- habilita routing regional/sharding futuro

Riesgo:

- si se omite un filtro, hay riesgo de fuga; por eso el "filtro obligatorio" debe ser enforced en el servicio (no en el caller).

### 6.2 Situacion actual en TheoGen (coleccion por proyecto)

Hoy Qdrant usa **una coleccion por proyecto** (`project_{project_id}_fragments`).

Esto ya aporta aislamiento natural y reduce riesgo de fuga por omision de filtro, pero:

- multiplica colecciones e indices
- dificulta agregar `source_type` y "unidades metodologicas" sin proliferar mas colecciones

Ruta recomendada:

P0: mantener coleccion por proyecto pero estandarizar payload (incluyendo `interview_id`, `source_type`).
P1: migrar a coleccion unica cuando el volumen lo justifique (o cuando se agreguen summaries/claims a escala).

## 7) Sistemas compuestos: separar cargas y routing antes del LLM

### 7.1 Separar etapas (operacion y costo)

- CPU: limpieza/segmentacion
- LLM: codificacion + teoria
- Vector DB: embeddings + index + busqueda (Qdrant)

Beneficio:

- reduces timeouts
- escalas por tipo de tarea (no escalas "todo" a la vez)
- reduces costo global

### 7.2 Routing semantico (planner) antes del LLM

Antes de llamar al LLM, decidir:

- consulta estructurada (Neo4j) vs
- consulta semantica (Qdrant) vs
- SQL (Postgres) vs
- respuesta directa

Beneficio:

- menos tokens
- menos costo
- menos latencia

## 8) Secure-by-design: Qdrant fuerza controles explicitos

Qdrant no trae autorizacion por si mismo; el diseno correcto exige:

### 8.1 Propagacion de identidad y filtros obligatorios

- Rechazar queries si falta `project_id`.
- Validar ownership de `project_id` antes de query (ya se hace en API `search_fragments`).
- En el servicio Qdrant: no exponer un metodo "raw search" sin filtros.

### 8.2 Control por entrevista/seccion (futuro)

- filtros por `interview_id`
- filtros por `speaker_id`/metadata (cuando exista)
- control por rol/equipo (futuro)

### 8.3 Proteccion de datos

MVP:

- cifrado en reposo (discos/almacenamiento Azure)
- secretos en Key Vault
- red privada (VNet) si aplica
- minimizar payload sensible (no meter PII evitable)

## 9) Recomendacion: cambios concretos para TheoGen (ordenados por impacto)

### P0 (calidad + seguridad inmediata)

1) Estandarizar payload de fragmentos:
   - agregar `interview_id`, `source_type="fragment"`, `created_at/ts` y (recomendado) `owner_id`
2) Enforzar filtro por `project_id` en todas las busquedas del servicio Qdrant (aunque haya coleccion por proyecto).
3) Expandir evidencia usada por teorizacion:
   - dejar de construir `evidence_index` con ~3 items; aumentar y diversificar por entrevistas.

### P1 (mejora fuerte de teoria y brechas)

4) RAG por etapas:
   - crear `category_summary` vectors
   - recuperar summaries primero y luego drill-down a fragmentos
5) Integrar Neo4j->Qdrant (subgrafo->evidencia):
   - evidencia solo para nodos/edges criticos
6) Queries dirigidas:
   - impactos materiales/economicos/ambientales
   - contra-evidencia (contraste)

### P2 (escala y operacion)

7) Backups/snapshots y procedimiento de restore
8) Healthchecks + retries/backoff + circuit breaker
9) (Opcional) pgvector como retrieval hibrido / resiliencia (si tiene sentido operacional)

## 10) Que cambia en el producto (resultado visible)

Con estas mejoras, TheoGen pasa de:

- "teoria basada en texto + algo de evidencia"

a:

- "Graph-guided RAG con evidencia trazable, sin fugas, con muestreo contrastivo y control de deriva"

Dolores que ataca directo:

- timeouts (menos consultas, mas focalizacion)
- overflow tokens (menos contexto redundante)
- alucinacion/deriva (evidencia obligatoria, guiada por grafo)
- brechas pobres (brechas con contraste y cobertura)

