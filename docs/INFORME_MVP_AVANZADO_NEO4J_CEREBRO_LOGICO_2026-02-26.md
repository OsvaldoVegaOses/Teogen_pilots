# Informe técnico: MVP avanzado — Neo4j como “Cerebro Lógico” de TheoGen

Fecha: 2026-02-26  
Proyecto: TheoGen  
Autor: Codex CLI (GPT-5.2)

## 1) Resumen ejecutivo (impacto inmediato)

El “Cerebro Lógico” con Neo4j aporta valor **hoy** en TheoGen principalmente por:

1) **Trazabilidad fuerte**: convertir teoría (condiciones/acciones/consecuencias/proposiciones/brechas) en **Claims auditables** que siempre referencian evidencia (`fragment_id`) y rutas del grafo.
2) **Control de deriva**: un **Judge determinista** (no‑LLM) valida reglas mínimas (evidencia obligatoria, sanidad de dominio, cobertura, balance) y dispara **reintentos parciales** (solo secciones fallidas).
3) **Brechas accionables**: métricas deterministas de **cobertura** (entrevistas/actores/territorios) + **contraste** (contra-evidencia / comunidades no representadas).
4) **Uso más inteligente de Qdrant**: Qdrant pasa de “buscar en bruto” a “buscar evidencia” solo para **nodos/edges críticos** seleccionados por Neo4j (subgrafo compacto).
5) **Eficiencia y control de contexto**: el pipeline escalonado alimenta al LLM con **subgrafos pequeños** + evidencia focalizada, degradando solo si excede presupuesto.

## 2) Estado actual en el repositorio (lo que ya está implementado)

TheoGen **ya** integra Neo4j y Qdrant en el flujo de codificación y teoría:

- Variables requeridas en runtime: `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `QDRANT_URL` (`README.md`).
- Sync desde codificación:
  - Qdrant: embedding por `Fragment` + payload `{text, project_id, codes:[labels]}` (`backend/app/engines/coding_engine.py`).
  - Neo4j: `Project`, `Code`, `Fragment`, `Category` y edges `HAS_*`, `Category-[:CONTAINS]->Code-[:APPLIES_TO]->Fragment` (`backend/app/services/neo4j_service.py`).
- Teoría:
  - El pipeline consume métricas reales del grafo (centralidad, co‑ocurrencias) (`backend/app/services/neo4j_service.py`).
  - Recupera evidencia semántica desde Qdrant para algunas categorías top (`backend/app/engines/theory_pipeline.py`).
  - Tiene repairs parciales (p. ej. reescritura de consecuencias y proposiciones) y reglas anti‑términos meta‑metodológicos (`backend/app/engines/theory_engine.py`, `backend/app/prompts/theory_prompts_v2.py`).

### Limitación clave actual (raíz de problemas “consecuencias raras” y claims flojos)

El pipeline construye un `evidence_index` **muy pequeño** (≈ 3 fragmentos: top 3 categorías × 1 fragmento), y el validador actual:

- valida conteos (proposiciones >= 5),
- valida **tipos/horizontes** de consecuencias,
- valida “términos prohibidos” en consecuencias,

pero **no valida de forma determinista** que:

- cada item tenga `evidence_ids` no vacíos,
- esos `fragment_id` existan y pertenezcan al proyecto,
- haya cobertura por entrevistas (diversidad),
- se usen constructos del universo permitido (categorías/subgrafo).

## 3) Qué queremos lograr (criterios de producto)

Objetivos (alineados a tu propuesta):

- **Teorías auditables**: cada Claim debe apuntar a evidencia (`fragment_id`) + ruta simple en el grafo.
- **Menos conceptos raros**: validación determinista basada en evidencia y ontología mínima; reintentos parciales.
- **Mejor tratamiento de brechas**: cobertura/contraste medible con métricas y caminos del grafo.
- **Mejor uso de Qdrant**: Qdrant se consulta para evidencia de rutas/nodos críticos, no como “busca por categoría en bruto”.
- **Eficiencia**: subgrafo compacto + evidencia focalizada; degradación controlada si excede contexto.

## 4) Arquitectura propuesta (3 capas, compatible con el pipeline actual)

### A) Memoria estructurada (Neo4j)

Responsabilidades:

- Estructura (categorías, códigos, actores/territorio si existe, relaciones y métricas).
- Trazabilidad (qué fragmentos soportan qué relación/claim).
- Consultas multi-hop para explicar teoría (paths + weights).

### B) Evidencia (Qdrant; opcional pgvector)

Responsabilidades:

- Dado un “X” (nodo/edge/claim), devolver fragmentos similares (evidencia).
- Payload como filtros: `project_id`, `codes`, (ideal) `interview_id`, `category_ids`.

### C) Síntesis (LLM) + Judge determinista

Responsabilidades:

- El LLM **no inventa estructura**: redacta usando `subgrafo + evidencia`.
- El **Judge** valida/rechaza y fuerza reintentos parciales si falla.

## 5) Modelo de grafo mínimo pero “cognitivo” (MVP avanzado)

Nota: esto **no** reemplaza Postgres; Postgres sigue como fuente de verdad. Neo4j es memoria simbólica derivada, trazable e idempotente.

### 5.1 Nodos (propuesta incremental)

Base (ya existe parcialmente):

- `Project {id, name, project_id?, owner_id?}`
- `Category {id, name, project_id}`
- `Code {id, label, project_id}`
- `Fragment {id, text_snippet, project_id}`

Agregar (MVP avanzado):

- `Interview {id, project_id, owner_id, participant_alias?, meta?}`
- `Claim {id, project_id, owner_id, theory_id, claim_type, text, stage, created_at, run_id}`
  - `claim_type`: `condition|action|consequence|proposition|gap`

Opcional P1:

- `ActorGroup {key, project_id}` (si hay metadata utilizable).

### 5.2 Relaciones (con propiedades críticas)

Estructura/evidencia:

- `(:Project)-[:HAS_INTERVIEW]->(:Interview)`
- `(:Interview)-[:HAS_FRAGMENT]->(:Fragment)`  *(recomendado para cobertura determinista)*
- `(:Fragment)-[:CODED_AS {confidence, source, run_id, ts, char_start, char_end}]->(:Code)`
  - En el repo hoy existe `(:Code)-[:APPLIES_TO]->(:Fragment)`; se puede mantener y evolucionar.
- `(:Code)-[:IN_CATEGORY {run_id, ts}]->(:Category)` *(hoy: `(:Category)-[:CONTAINS]->(:Code)`; equivalente invertido)*

Métricas / caminos:

- `(:Category)-[:CO_OCCURS_WITH {count, weight, run_id}]->(:Category)`
- `(:Category)-[:RELATES_TO {type, strength, run_id}]->(:Category)`
  - `type`: `supports|contrasts|causal_hint` (evitar “causa” dura en MVP si aún no corresponde).

Teoría auditable:

- `(:Claim)-[:SUPPORTED_BY {score, rank}]->(:Fragment)`
- `(:Claim)-[:ABOUT]->(:Category)` (1..N categorías)
- `(:Claim)-[:CONTRADICTED_BY {score}]->(:Fragment)` (cuando exista contraste)

### 5.3 Constraints/índices (multi-tenant y desempeño)

Recomendación:

- Unicidad por IDs:
  - `Project(id)`, `Interview(id)`, `Fragment(id)`, `Code(id)`, `Category(id)`, `Claim(id)`
- Índices por `project_id` (y opcional `owner_id`) en nodos principales.

Ejemplo Cypher (orientativo):

```cypher
CREATE CONSTRAINT project_id_unique IF NOT EXISTS FOR (p:Project) REQUIRE p.id IS UNIQUE;
CREATE CONSTRAINT category_id_unique IF NOT EXISTS FOR (c:Category) REQUIRE c.id IS UNIQUE;
CREATE CONSTRAINT code_id_unique IF NOT EXISTS FOR (c:Code) REQUIRE c.id IS UNIQUE;
CREATE CONSTRAINT fragment_id_unique IF NOT EXISTS FOR (f:Fragment) REQUIRE f.id IS UNIQUE;
CREATE CONSTRAINT interview_id_unique IF NOT EXISTS FOR (i:Interview) REQUIRE i.id IS UNIQUE;
CREATE CONSTRAINT claim_id_unique IF NOT EXISTS FOR (c:Claim) REQUIRE c.id IS UNIQUE;

CREATE INDEX category_project_id IF NOT EXISTS FOR (c:Category) ON (c.project_id);
CREATE INDEX fragment_project_id IF NOT EXISTS FOR (f:Fragment) ON (f.project_id);
CREATE INDEX claim_project_id IF NOT EXISTS FOR (c:Claim) ON (c.project_id);
```

## 6) Cómo construir el cerebro sin romper el pipeline actual

### 6.1 Sync por “runs” + UNWIND (batch, idempotente)

Principio: cada etapa relevante produce un `run_id` y sincroniza por lotes.

En el repo ya existe batch sync:

- `neo4j_service.batch_sync_interview(...)` (fragments, codes, pairs) usando UNWIND.
- `neo4j_service.batch_sync_taxonomy(...)` (categories + code→category) usando UNWIND.

Extensión MVP avanzada (sin romper):

A) `batch_sync_interview(run_id, interview_id)`

- upsert `Interview` + `Fragment` + `HAS_FRAGMENT`
- (si ya existe `Fragment` por project) solo linkear.

B) `batch_sync_coding(run_id, interview_id)`

- persistir `CODED_AS` con propiedades (confidence, char span, source).
- mantener `APPLIES_TO` como compatibilidad si se desea, pero preferir `CODED_AS` por auditabilidad.

C) `batch_sync_metrics(run_id, project_id)`

- materializar `CO_OCCURS_WITH` con `count/weight` para caminos “fuertes”.

D) `batch_sync_claims(run_id, theory_id)`

- crear `Claim` por cada item del JSON del paradigma/gaps.
- `SUPPORTED_BY` desde `evidence_ids`.
- `ABOUT` mapeado a categorías (por nombre/cat_id).

### 6.2 Dónde enchufa en código hoy (puntos exactos)

- Evidencia y subgrafo: `backend/app/engines/theory_pipeline.py` (stage `semantic_evidence`, `evidence_index`).
- Repairs parciales ya existen: `backend/app/engines/theory_engine.py` (`repair_consequences`, `repair_propositions`, `repair_context_intervening`).
- Persistencia en Neo4j: tras `save_theory` en `backend/app/engines/theory_pipeline.py` (best-effort, no rompe contrato).

## 7) GraphRAG “de verdad” en TheoGen (donde más aporta)

Objetivo: reemplazar “categorías + evidencia en bruto” por:

- **subgrafo compacto** (nodos + edges con pesos y paths),
- evidencia Qdrant **solo** para esos nodos/edges,
- diversidad (cobertura por entrevistas) incluida en el set de evidencia.

### Step 1 — Central category (Neo4j-driven)

Neo4j calcula:

- top por centralidad (ya existe: `get_project_network_metrics`),
- top co‑occurrences (ya existe),
- opcional: GDS PageRank/Degree si está instalado (ya hay fallback GDS en `neo4j_service.get_project_network_metrics`).

Subgrafo sugerido:

- top 13 categorías por ranking,
- vecinos fuertes por co‑ocurrencia,
- puentes (betweenness) si GDS lo permite; si no, aproximar con “nodos que conectan comunidades” vía co‑ocurrencias top.

Evidencia:

- Qdrant busca fragmentos para cada categoría del subgrafo y para edges top (query conjunta: “A + B”).

Beneficio: selección central más estable y justificable (ruta + evidencia).

### Step 2 — Paradigma (subgrafo + evidencia focalizada)

Neo4j entrega:

- vecindario del central (1–2 hops),
- caminos más fuertes central→otros (por weight),
- clusters relevantes (si GDS).

Qdrant entrega evidencia por:

- categorías clave,
- edges clave (evidencia “conjunta”).

Output esperado: paradigma + Claims estructurados con `evidence_ids` obligatorios.

### Step 3 — Brechas (determinista + LLM)

Brechas deterministas:

- cobertura por entrevistas citadas,
- ausencia de contra‑evidencia (`CONTRADICTED_BY` vacío),
- cluster sin representación en claims,
- edges fuertes sin claims que los expliquen.

Luego el LLM redacta recomendaciones (muestreo/entrevista/territorio) **a partir de esas señales**.

## 8) TheoryJudge determinista (la pieza de mayor ROI)

### 8.1 Reglas mínimas (alta ganancia)

1) **Evidence required**: cada item (conditions/actions/consequences/propositions) debe tener `evidence_ids` con al menos 1 id.
2) **Evidence exists**: cada `fragment_id` debe existir en Postgres y pertenecer a `project_id`.
3) **Domain sanity**: prohibir meta‑términos (informante/entrevista/identificación/diarización/etc.) en todas las secciones (no solo consecuencias).
4) **Coverage**: mínimo N entrevistas distintas citadas en claims (configurable; p. ej. N=3).
5) **Balance consequences**: al menos 1 `material`, 1 `social`, 1 `institutional` y horizontes `corto_plazo`/`largo_plazo`.

### 8.2 Reintentos parciales (baratos)

Si falla:

- regenerar **solo** el campo fallido (p. ej. `consequences` o `propositions`) usando:
  - subgrafo seleccionado,
  - evidencia re‑muestreada desde Qdrant (incluyendo queries dirigidas a impactos materiales),
  - evidencia_index ampliado y diverso.

Esto reduce costo y evita “romper” el resto del paradigma válido.

## 9) Qdrant + Neo4j para consecuencias materiales (anti “informe solo social”)

Señal: el Judge detecta ausencia de consecuencias materiales.

Acción: Qdrant consulta dirigida (solo si el subgrafo lo sugiere o el Judge lo exige) con queries:

- `daños`, `pérdidas`, `costos`, `vivienda`, `infraestructura`, `salud`, `ambiente`, `largo plazo`

Resultado:

- si hay evidencia fuerte → exigir incorporar consecuencias materiales con `evidence_ids`.
- si no hay evidencia → brecha explícita: “no aparece evidencia material suficiente; muestreo recomendado”.

## 10) Cambios visibles de producto (sin tocar demasiado)

1) Botón “Ver evidencia” por sección/claim:
   - lista de citas (fragments) + score,
   - ruta simple: `Category -> Claim -> Fragment`.
2) Sección “Cobertura”:
   - qué entrevistas aportan a la teoría (por `evidence_ids`).
3) Brechas con sugerencia de muestreo:
   - qué segmento/territorio/actor falta (si hay metadata) o, mínimo, qué entrevistas faltan para contraste.

Nota: ya existe endpoint para lookup de fragmentos en Postgres:

- `POST /api/search/fragments/lookup` (`backend/app/api/search.py`)

## 11) Roadmap sugerido (MVP en 3 semanas, extensible)

Semana 1 — Claims + evidencia + Judge (sin UI)

- Expandir `evidence_index` (más categorías y diversidad de entrevistas).
- Implementar TheoryJudge determinista (gates + reintentos parciales).
- Persistir `Claim` en Neo4j en best-effort (post-save).

Semana 2 — GraphRAG subgrafo + evidencia focalizada

- `graph_retriever`: subgrafo central + vecindario + edges top.
- `evidence_retriever`: evidencia Qdrant por nodos/edges seleccionados.

Semana 3 — Explainability + brechas deterministas

- Endpoint mínimo “explain”: claims + fragments + paths.
- Brechas deterministas (coverage/contrast) antes del LLM.

Extensión (largo plazo / 23 semanas): incorporar ActorGroup, territorios, Louvain/betweenness robustos (GDS), contradicción explícita, y panel UX completo.

## 11.1 Rollout seguro por flags (recomendado)

Para integrar sin romper contrato ni comportamiento existente, activar por variables (defaults seguros):

- `THEORY_USE_SUBGRAPH_EVIDENCE=true`
- `THEORY_USE_JUDGE=true`
- `THEORY_SYNC_CLAIMS_NEO4J=true` (best-effort: si falla no rompe teoría)
- `THEORY_USE_DETERMINISTIC_GAPS=true`
- `THEORY_EVIDENCE_TARGET_MIN=30`
- `THEORY_EVIDENCE_TARGET_MAX=80`
- `THEORY_EVIDENCE_MIN_INTERVIEWS=4`
- `THEORY_EVIDENCE_MAX_SHARE_PER_INTERVIEW=0.4`

## 12) Criterios de éxito (medibles)

- **0 claims sin evidencia** (o <5% si hay excepciones explícitas).
- **Proposiciones siempre presentes** (>=5).
- **Reducción drástica** de términos meta‑metodológicos en consecuencias y proposiciones (gates + reintentos parciales).
- **Brechas más específicas**: incluyen cobertura y contraste (entrevistas/actores).
- **Menor costo/tiempo**: Qdrant consultado sobre subgrafo, no sobre universo completo.

## 13) Riesgos y mitigaciones

- Riesgo: “Neo4j queda inconsistente con Postgres”.
  - Mitigación: sync idempotente + `run_id` + best-effort; Postgres sigue siendo truth.
- Riesgo: “GDS no está disponible”.
  - Mitigación: fallback Cypher (ya existe en `get_project_network_metrics`).
- Riesgo: “Judge demasiado estricto bloquea entregas”.
  - Mitigación: thresholds configurables + degradación controlada (reintentos parciales) + modo “warn-only” por flag.

## 14) Próximos pasos recomendados

1) Definir flags de rollout y thresholds del Judge (N entrevistas mínimas, mínimo evidence_ids por claim).
2) Implementar expansión de `evidence_index` y validación de `evidence_ids` (determinista).
3) Añadir persistencia de `Claim` en Neo4j tras `save_theory` (best-effort).
