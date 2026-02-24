# Informe Desarrollo: Fix PDF + PNG Red (TheoGen)

Fecha y hora: 2026-02-24 10:30:54 -03:00

## Objetivo

- Corregir exportacion a PDF cuando el modelo incluye JSON estructurado (consequences/propositions) y/o texto con caracteres especiales.
- Generar un PNG "presentable" que incluya una red/mapa (categorias + coocurrencia) basada en metricas calculadas en Neo4j (incluyendo GDS cuando esta disponible).
- Mantener compatibilidad hacia atras (no romper endpoints existentes).

## Cambios Implementados

### 1) PDF (ReportLab) robusto

Archivo: `backend/app/services/export_service.py`

- Sanitizacion de caracteres de control (ASCII 0x00-0x1F, excluyendo TAB/CR/LF) para evitar fallas del renderer de ReportLab.
- Escape XML consistente para todo texto que entra a `Paragraph`.
- Central category ahora se renderiza en negrita sin exponer markup no escapado.
- Consecuencias estructuradas (lista de objetos con `name/type/horizon/evidence_ids`) se renderizan como tabla a ancho de pagina (evita overflow por tablas anidadas dentro de celdas estrechas).
- Brechas se renderizan con escape/sanitizacion para evitar rupturas por caracteres como `&`, `<`, `>` o controles.

Impacto esperado:
- PDF deja de romperse por:
  - caracteres invalidos/control en salida de LLM
  - caracteres especiales que ReportLab interpreta como markup
  - overflow por nested tables con colWidths mayores que el ancho de la celda

### 2) PNG: red de categorias (Neo4j) + mejor formateo

Archivo: `backend/app/services/export/infographic_generator.py`

- Se reemplazo el generator por una version que:
  - Formatea consequences dicts como: `name [type/horizon]` (en vez de `str(dict)`).
  - Dibuja un panel "Red de categorias (Neo4j)" usando:
    - nodos: `validation.network_metrics_summary.category_centrality_top`
    - aristas: `validation.network_metrics_summary.category_cooccurrence_top`
    - layout: `networkx.spring_layout` (seed fijo 42 para estabilidad visual)
    - tamanio nodo: centralidad (pagerank si existe; si no, gds_degree; si no, grados cypher)
    - grosor arista: `shared_fragments`
  - Fallbacks:
    - si no hay coocurrencias: lista de top categorias
    - si no hay datos: mensaje "Sin datos de red"
- Ajuste de layout del PNG: altura aumenta a 2200px para incluir red + brechas + metricas sin solapamiento.

### 3) Mas datos para la red (sin romper API)

Archivo: `backend/app/engines/theory_pipeline.py`

- Se aumento el detalle guardado en `validation.network_metrics_summary`:
  - `category_centrality_top`: de 5 a 20
  - `category_cooccurrence_top`: de 5 a 30

Motivo:
- Con 5 elementos la red en PNG queda pobre y no comunica estructura; con 20/30 se obtiene un grafo visible sin inflar demasiado el payload.

## Archivos Modificados

- `backend/app/services/export_service.py`
- `backend/app/services/export/infographic_generator.py`
- `backend/app/engines/theory_pipeline.py`

## Verificacion (Runbook Corto)

1. Generar teoria para un proyecto con suficiente codificacion (para que existan categorias + coocurrencia en Neo4j).
2. Exportar:
   - PDF: verificar que el documento se genera y que "Consecuencias" aparece como tabla con Type/Horizon/Evidence IDs.
   - PNG: verificar que aparece el panel "Red de categorias (Neo4j)" con nodos/aristas y una leyenda.
   - PPTX/XLSX: no deben degradarse (solo reciben mas filas en validation).
3. Probar con contenido "hostil":
   - textos con `&`, `<`, `>` y caracteres de control colados desde LLM
   - consequences/propositions como dicts (schema)

## Notas de Compatibilidad

- No se cambio el contrato de endpoints; solo se enriquecio `validation.network_metrics_summary` con mas elementos (listas mas largas).
- El render PDF sigue aceptando legacy shapes:
  - consequences como string/lista de strings
  - conditions/actions como string/lista de strings/dicts (se convierte a texto)

