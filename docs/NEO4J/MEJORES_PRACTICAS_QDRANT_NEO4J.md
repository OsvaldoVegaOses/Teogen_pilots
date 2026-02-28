# Mejores prácticas: Qdrant ↔ Neo4j

## Resumen ejecutivo
Breve guía en español con recomendaciones prácticas para diseñar, almacenar y consultar datos que combinan Neo4j (grafo + GDS) y Qdrant (vectores + payload). Incluye ejemplos de Cypher, payload de Qdrant y consejos para normalización y transferencia entre ambos sistemas.

**Principio general**: separar claramente la información usada para búsqueda semántica (texto → embeddings) de la información usada para filtrado/exact-match (payload/propiedades). Mantener ambas versiones (raw + normalizada) cuando sea necesario.

## Conceptos clave
- **Neo4j**: orientado a relaciones y topología; algoritmos GDS (PageRank, degree) usan estructura del grafo y valores numéricos (weights), no interpretan símbolos textuales salvo en filtros o nombres de propiedades.
- **Qdrant**: almacena vectores y un `payload` JSON; la semántica proviene del modelo de embeddings, no del motor; payload se usa para filtros (exactos, rangos, facetas).

## Recomendaciones de diseño de esquema
- Nombres de propiedades/keys: usar `snake_case` o `camelCase` sin símbolos (evitar `: { [`) para claves. Si no se puede, acceder por clave dinámica.
  - Neo4j: usar identificadores seguros o escapar con backticks cuando corresponda: ``MATCH (n:`Mi:Label`) RETURN n``.
  - Para propiedades con símbolos: acceder como `n['prop:with:chars']`.
- Mantener dos campos para textos que alimentan embeddings:
  - `code_raw` (texto original, tipo keyword/payload para filtros y facetas). Ej.: `:{[`.
  - `code_norm` (texto normalizado para embeddings): limpiar o transformar símbolos si el modelo produce ruido.

## Neo4j — prácticas concretas
- Escapado de identificadores: use backticks para labels/relacionTypes que contengan caracteres especiales: ``CREATE (n:`Categoria:PageRank` {name: 'X'})``.
- Acceso a propiedades con nombres complejos: `n['mi:prop{[']` o renombrar la propiedad a una forma segura.
- GDS (PageRank, Degree):
  - Los algoritmos usan la topología y propiedades numéricas. Solo las propiedades numéricas (`relationshipWeightProperty`) afectan el cálculo.
  - Si filtras nodos/relaciones por label, tipo o propiedades string para construir la proyección, entonces la presencia de símbolos en esas propiedades solo influye en la selección (filtering), no en el cálculo en sí.
- Para persistir resultados GDS usar `write`/`mutate` con `writeProperty`/`mutateProperty` con nombres sin símbolos.

Ejemplos Cypher
- Propiedad con símbolos (lectura):
```
MATCH (n)
WHERE n['code_raw'] = ': { ['
RETURN n
```
- Crear nodo con propiedad segura:
```
CREATE (c:Categoria {code_raw: ':{[', code_norm: 'colon bracket open'})
```

## Qdrant — prácticas concretas
- Tipos de payload: definir tipos (keyword, integer, float, bool, datetime, uuid). Evitar strings arbitrarios cuando necesites filtrar por rango o facetas.
- Indexar campos de payload que uses en filtros/facetas. Crear `field index` para `keyword` cuando necesites `MatchValue` o faceting.
- No uses filtros de rango sobre strings (no funcionan). Asegúrate que el tipo en payload coincide con el tipo de filtro.
- Separar `payload` para filtrado y texto para embeddings: el vector proviene del texto normalizado que envías al encoder; el payload contiene metadatos y la versión raw para facetas.
- Strict mode (Cloud): ten en cuenta que consultas sobre campos no indexados pueden ser bloqueadas o penalizadas; crea índices antes de hacer consultas masivas.

Ejemplo de upsert Qdrant
```
PUT /collections/mycol/points
{
  "points": [
    {"id": 1, "vector": [0.12,...], "payload": {"code_raw": ":{[", "category": "A", "timestamp": "2026-02-25T12:00:00Z"}}
  ]
}
```

## Integración Neo4j → Qdrant (flujo recomendado)
1. Extraer desde Neo4j los nodos/propiedades relevantes con Cypher (usar parámetros para evitar inyección). Ejemplo:
```
MATCH (c:Categoria)
RETURN id(c) AS id, c.code_raw AS code_raw, c.name AS name
```
2. Normalizar `code_raw` a `code_norm` para embeddings (limpieza de símbolos opcional) y generar embedding con el modelo elegido.
3. Upsert en Qdrant con `id` (preferiblemente UUID o entero consistente) y payload conteniendo `code_raw`, `category`, `neo4j_id`.
4. Crear índices de payload en Qdrant para campos usados en filtros.

Ejemplo Python (esqueleto)
```python
import re
from qdrant_client import QdrantClient

def normalize_text(s: str) -> str:
    s = s.strip()
    s = re.sub(r"\s+", " ", s)
    return s

# pseudo: obtener rows desde Neo4j
rows = [ (1, ':{[', 'CatA'), ... ]
client = QdrantClient(url='http://localhost:6333')
points = []
for id_, code_raw, category in rows:
    code_norm = normalize_text(code_raw)
    vector = embed(code_norm)  # usa tu encoder
    points.append({"id": id_, "vector": vector, "payload": {"code_raw": code_raw, "category": category}})
client.upsert(collection_name='mycol', points=points)
```

## Consideraciones sobre símbolos en texto y embeddings
- Los símbolos (p. ej. `: { [`) afectan al embedding porque forman parte del input al modelo. Si esos símbolos son significativos (identificadores, fragmentos de código), mantener `code_raw` y también crear `code_for_embed` con el contexto deseado.
- Para datos tipo `code` (fragmentos de código), prueba generadores de embeddings entrenados/afinados para código o usa tokenización apropiada.

## Normalización y control de calidad
- Mantener pipelines ETL reproducibles: extracción → limpieza → normalización → embeddings → upsert.
- Validaciones: comprobar tipos de payload antes de crear índices; comprobar que vectores no sean nulos; confirmar que `id` sea único.

## Rendimiento y escalabilidad
- Qdrant: crear índices de payload antes de uso intensivo; revisar `strict mode` si necesitas consultas flexibles.
- Neo4j GDS: estimar memoria antes de ejecuciones grandes (`gds.*.estimate`). Partir con grafos proyectados parciales si la memoria es limitada.

## Checklist rápido antes de producción
- [ ] Propiedades y nombres sin símbolos o accesibles por `['key']`.
- [ ] Campos `keyword` indexados en Qdrant si se filtran.
- [ ] `relationshipWeightProperty` numérico en Neo4j si usas grafos ponderados.
- [ ] Guardadas versiones `raw` y `normalized` del texto.
- [ ] Pruebas de integridad (round-trip) entre Neo4j y Qdrant.

## Conclusión
Separar claramente responsabilidades: Neo4j para relaciones/topología y análisis de grafo; Qdrant para búsqueda vectorial y filtrado por payload. Normaliza, separa raw vs embedding-text, y crea índices al anticipar filtros para mantener latencias y costos razonables.

---
Si quieres, puedo:
- Generar el script concreto para exportar desde Neo4j e insertar en Qdrant (Python runnable).
- Añadir pruebas unitarias o un ejemplo real con 10 registros de muestra.
