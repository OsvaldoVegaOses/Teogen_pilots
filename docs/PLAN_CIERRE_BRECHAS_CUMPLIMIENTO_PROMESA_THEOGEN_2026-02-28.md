# Plan de Cierre de Brechas para Cumplir la Promesa TheoGen

Fecha: 2026-02-28  
Objetivo: que TheoGen cumpla de forma consistente la promesa "claim + evidencia trazable para decision directiva" en los 6 casos de uso visibles.

## 1) Promesa operativa (version verificable)
TheoGen se considera "promesa cumplida" cuando:
1. Ningun claim exportado carece de evidencia trazable.
2. Cada recomendacion incluye nivel de confianza, contradicciones y limites.
3. Los reportes son comparables entre establecimientos/segmentos segun plantilla.
4. La UI permite auditar claim -> evidencia -> decision sin pasos manuales externos.

## 2) Brechas criticas a cerrar
1. 6 presets comerciales mapean a 5 templates reales; B2C y Consultoria usan `generic`.
2. Las plantillas influyen sobre prompts, pero no gobiernan gates duros de calidad.
3. Se permiten corridas con warnings y luego exportar, incluso con claims sin evidencia.
4. El flujo de evidencia por claim depende de sync/fallback y no siempre es robusto.
5. PDF no refleja control de calidad por plantilla con el mismo rigor que otros formatos.
6. Falta contrato de aceptacion por fase para no sobreprometer al cliente.

## 3) Metas de 45 dias (numericas)
1. `claims_without_evidence = 0` en todo reporte exportado.
2. `claim_explain_success_rate >= 99%` (sin error en UI ni API).
3. `export_block_rate` por calidad: 100% de reportes invalidos bloqueados.
4. Cobertura por actor minima por plantilla: >= 3 tipos de actor en casos directivos.
5. 100% de propuestas comerciales con alcance por fases y criterios de aceptacion.

## 4) Plan por fases
## Fase 0 (Dia 1-3): Congelamiento de sobrepromesa
Objetivo: alinear ventas con capacidad real mientras se implementan cambios.

Acciones:
1. Actualizar pitch y propuesta comercial con "lo demostrado hoy" y "roadmap con fecha".
2. Prohibir mensajes de causalidad fuerte sin evidencia suficiente.
3. Definir plantilla contractual por fases: Discovery, Decision Readiness, Escalamiento.

Entregables:
1. Script comercial final.
2. Plantilla de propuesta/SOW por fases.
3. Matriz de riesgos y limites por cliente.

## Fase 1 (Semana 1): Gates duros de calidad y trazabilidad
Objetivo: impedir que salgan reportes que rompen la promesa.

Cambios tecnicos:
1. En pipeline: si `claims_without_evidence > 0`, marcar corrida como no exportable.
2. En API export: validar calidad antes de generar PDF/PPTX/XLSX/PNG; si no cumple, responder 422 con detalle.
3. En UI: mostrar "Estado de calidad" (Apto / No Apto) antes de exportar.
4. En validacion: incluir umbrales por plantilla (min evidencias, min actores, min entrevistas).

Aceptacion:
1. Test automatico: un theory con claim sin evidencia no se exporta.
2. Test UI: boton export bloqueado con razon visible.

## Fase 2 (Semana 2): Robustecer evidencia por claim (end-to-end)
Objetivo: que "Ver evidencia por claim" sea confiable en todos los casos.

Cambios tecnicos:
1. Fortalecer fallback para claims no-dict y estructuras mixtas.
2. Sincronizacion obligatoria y monitoreada de claims en Neo4j/Qdrant.
3. Alertas cuando la fuente caiga a fallback degradado.
4. Exponer metrica por corrida: fuente de evidencia usada y nivel de cobertura.

Aceptacion:
1. `claim_explain_success_rate >= 99%` en pruebas de regresion.
2. 0 claims renderizados en UI sin evidencia cuando status sea "Apto".

## Fase 3 (Semana 3): Normalizar plantillas y casos de uso
Objetivo: cerrar brecha entre 6 casos de uso comerciales y templates reales.

Cambios tecnicos:
1. Crear templates dedicados para `b2c` y `consulting` (no mas fallback a `generic`).
2. Definir `template_policy` por dominio:
   - actores obligatorios
   - dimensiones obligatorias
   - KPI obligatorios
   - umbrales de evidencia
3. Aplicar esas politicas en judge/validation/export.
4. Hacer que `lexicon_map` y `export_formats` se usen realmente en output.

Aceptacion:
1. 6 casos de uso con reglas propias verificables.
2. Reportes comparables por plantilla con campos obligatorios presentes.

## Fase 4 (Semana 4): Decision readiness para directivos
Objetivo: convertir hallazgos en decisiones defendibles.

Cambios tecnicos/funcionales:
1. Hoja obligatoria "Decision Framework":
   - recomendacion
   - evidencia a favor
   - evidencia en contra
   - riesgo
   - decision sugerida (Go/Pilot/No-Go)
2. Hoja "Plan de accion" por claim:
   - accion
   - responsable
   - plazo
   - indicador de seguimiento
3. Seccion fija de limites y supuestos en todos los exportes.

Aceptacion:
1. Cada reporte "Apto" contiene decision framework + plan de accion.
2. Comite puede auditar cada decision sin acceso tecnico al backend.

## Fase 5 (Semana 5-6): Privacidad, compliance y hardening
Objetivo: sostener la promesa en sector publico/educacion sin riesgo reputacional.

Cambios tecnicos:
1. Pseudonimizacion por rol por defecto en todo flujo.
2. Deteccion y minimizacion de PII antes de indexar/exportar.
3. Auditoria de acceso a evidencia sensible (quien vio que y cuando).
4. Pruebas de regresion en privacidad y trazabilidad.

Aceptacion:
1. 0 hallazgos de PII expuesta en muestra QA.
2. Log auditable habilitado para evidencia sensible.

## 5) Matriz por caso de uso (6 presets)
1. Educacion:
- Falta: comparabilidad territorial y reglas de privacidad escolar.
- Cierre: policy education con actores minimos + seudonimizacion estricta.

2. ONG:
- Falta: evidencia de rendicion para donantes/aliados.
- Cierre: campos obligatorios de impacto + riesgos operativos.

3. Market Research:
- Falta: baseline y contradicciones como requisito, no opcional.
- Cierre: KPI y casos negativos obligatorios para export "Apto".

4. B2C:
- Falta: template propio (hoy generic).
- Cierre: template b2c con retention/churn/conversion y journey.

5. Consultoria:
- Falta: template propio y estandar de entregable multi-cliente.
- Cierre: template consulting con comparativos y trazabilidad contractual.

6. Sector Publico:
- Falta: decision framework institucional obligatorio.
- Cierre: template government reforzado con compliance y accountability.

## 6) Backlog tecnico priorizado (PRs)
1. PR-A: Quality Gate de export (backend API + UI).
2. PR-B: Claim Explain hardening (fallback + observabilidad).
3. PR-C: Nuevos templates b2c/consulting + policy engine.
4. PR-D: Exportes directivos (decision framework + plan accion + limites).
5. PR-E: Privacidad by design + auditoria.
6. PR-F: Test suite e2e por plantilla/caso.

## 7) KPIs de control semanal
1. `% reportes bloqueados por calidad` (debe bajar semana a semana por mejora real).
2. `% claims sin evidencia en corridas completadas`.
3. `% corridas warn_only`.
4. `% explain requests fallidas`.
5. `% proyectos con policy de plantilla aplicada`.
6. `% reportes con decision framework completo`.

## 8) RACI minimo
1. Product Owner: define umbrales "Apto" y prioriza backlog.
2. Backend Lead: gates, pipeline, claims explain, export API.
3. Frontend Lead: UX de calidad, auditoria y bloqueo preventivo.
4. Data/Research Lead: politicas por plantilla y criterios metodologicos.
5. Comercial: ajuste de promesa y contratos por fase.

## 9) Criterio final de "Promesa Cumplida"
Se declara cumplimiento cuando durante 2 semanas consecutivas:
1. 0 reportes "Apto" con claims sin evidencia.
2. >= 99% de disponibilidad de evidencia por claim.
3. 100% de reportes con decision framework y limites.
4. 100% de nuevos pilotos vendidos con alcance por fases y aceptacion objetiva.
