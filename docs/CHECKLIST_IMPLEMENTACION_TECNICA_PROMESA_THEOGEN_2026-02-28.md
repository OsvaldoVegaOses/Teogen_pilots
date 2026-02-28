# Checklist de Implementacion Tecnica por Modulo

Fecha: 2026-02-28  
Objetivo: asegurar que TheoGen cumpla su promesa en produccion ("insights trazables y auditables para decision directiva").

## Regla principal
1. Si un claim no tiene evidencia trazable, no se exporta como recomendacion.
2. Si no hay nivel de confianza y brecha explicita, no se marca como insight directivo.

## Modulo 1 - Ingesta y normalizacion
Meta: datos consistentes y utilizables para trazabilidad end-to-end.

Checklist:
1. Validar encoding UTF-8 en toda ingesta (sin mojibake).
2. Requerir `source_id`, `fragment_id`, `timestamp`, `actor_type`, `canal`.
3. Rechazar registros sin texto util o metadatos minimos.
4. Registrar errores de parsing en log auditable.
5. Versionar la fuente de cada carga (dataset_version).

Criterio de aceptacion:
1. 100% de fragmentos procesados con metadatos minimos.
2. 0 errores criticos de encoding en muestra de control.

## Modulo 2 - Motor semantico (Qdrant)
Meta: recuperar evidencia relevante y reproducible por claim.

Checklist:
1. Cada claim debe guardar `top_k` evidencias con score.
2. Persistir parametros de consulta (modelo, umbral, fecha).
3. Exponer endpoint/UI para "Ver evidencia por claim".
4. Diferenciar evidencia positiva vs contradictoria.
5. Alertar claims con evidencia vacia o debajo de umbral.

Criterio de aceptacion:
1. Cobertura minima: >= 90% claims con evidencia recuperada.
2. En claims criticos: >= 1 evidencia contradictoria cuando exista.

## Modulo 3 - Motor logico (Neo4j)
Meta: explicabilidad de relaciones y soporte de auditoria.

Checklist:
1. Modelar relaciones: categoria -> claim -> evidencia -> consecuencia.
2. Guardar trazabilidad de transformaciones (origen y version).
3. Calcular score de confianza por claim con reglas explicitas.
4. Marcar brechas automaticas (falta actor, falta contraste, baja cobertura).
5. Mantener consultas de auditoria para reporte directivo.

Criterio de aceptacion:
1. 100% de claims exportados con ruta de trazabilidad completa.
2. Score de confianza visible y justificable por reglas.

## Modulo 4 - Validacion metodologica
Meta: evitar sobrepromesa causal sin evidencia suficiente.

Checklist:
1. Definir umbrales minimos por insight directivo:
   - evidencias minimas por claim.
   - cobertura por actor.
   - casos desconfirmatorios.
2. Implementar semaforo: Verde/Amarillo/Rojo por recomendacion.
3. Bloquear recomendacion "Go" si alguna condicion critica queda en Rojo.
4. Registrar supuestos y limites de validez por recomendacion.

Criterio de aceptacion:
1. Ninguna recomendacion se exporta sin semaforo y supuestos.
2. 100% recomendaciones con criterio Go/Pilot/No-Go trazable.

## Modulo 5 - Exportes (PDF/PPTX/XLSX/PNG)
Meta: reportes confiables y consistentes con la verdad del sistema.

Checklist:
1. Hard gate previo a exportar:
   - evidencia por claim disponible.
   - score de confianza calculado.
   - brechas visibles.
2. Incluir tabla "evidencia por recomendacion" en exportes ejecutivos.
3. Incluir seccion "limites y riesgos" obligatoria.
4. Validar consistencia de metricas entre formatos (PDF/PPTX/XLSX).

Criterio de aceptacion:
1. 0 exportes con claims sin evidencia trazable.
2. 0 discrepancias criticas de metricas entre formatos.

## Modulo 6 - UI de auditoria
Meta: que cliente/directivo pueda verificar conclusiones sin depender del analista.

Checklist:
1. Boton visible "Ver evidencia" por claim y recomendacion.
2. Filtros por actor, segmento, fecha y tipo de evidencia.
3. Vista de contradicciones y casos negativos.
4. Estado de confianza y brecha en la misma pantalla.
5. Historial de cambios/versiones de recomendaciones.

Criterio de aceptacion:
1. Usuario no tecnico puede auditar un claim en < 3 minutos.
2. Navegacion completa claim -> evidencia -> decision sin pasos manuales externos.

## Modulo 7 - KPI y tablero de valor
Meta: demostrar que la promesa produce impacto real en cliente.

Checklist:
1. KPI baseline por cliente antes de uso:
   - tiempo de analisis.
   - tiempo a decision.
   - calidad percibida del insight.
2. KPI post-implementacion (30/60/90 dias).
3. Tablero con comparativo pre/post y tendencia.
4. Alerta automatica cuando KPI cae bajo umbral.

Criterio de aceptacion:
1. Baseline + primer corte post disponibles en <= 30 dias.
2. Reporte ejecutivo con delta de mejora por KPI.

## Modulo 8 - QA y pruebas de regresion
Meta: estabilidad operacional de la promesa.

Checklist:
1. Test automatizado para cobertura de evidencia por claim.
2. Test de integridad de trazabilidad en Neo4j/Qdrant.
3. Test de exportes con gates de bloqueo.
4. Test UI de flujo de auditoria.
5. Smoke test diario de pipeline completo.

Criterio de aceptacion:
1. Pipeline CI bloquea deploy si falla gate de trazabilidad.
2. Tasa de fallas criticas en produccion < umbral definido.

## Modulo 9 - Comercial y contratos (alineacion promesa)
Meta: vender solo lo demostrado y proteger credibilidad.

Checklist:
1. Propuesta cliente con "lo demostrado hoy" vs "roadmap con fecha".
2. Criterios de aceptacion contractuales por fase.
3. Seccion obligatoria de limites y supuestos.
4. Entregable de decision framework Go/Pilot/No-Go por proyecto.

Criterio de aceptacion:
1. 100% propuestas nuevas con estructura por fases y aceptacion objetiva.

## Plan semanal de ejecucion (4 semanas)
1. Semana 1: Modulos 1, 4 y 9.
2. Semana 2: Modulos 2, 3 y 6.
3. Semana 3: Modulos 5 y 8.
4. Semana 4: Modulo 7 + cierre de brechas pendientes.

## Gate final de promesa cumplida
TheoGen cumple promesa cuando:
1. Todo insight directivo tiene evidencia trazable visible.
2. Todo reporte explicita confianza, contradicciones y limites.
3. Todo cliente recibe decision framework auditable.
4. Existe mejora medible en KPI pre/post.
