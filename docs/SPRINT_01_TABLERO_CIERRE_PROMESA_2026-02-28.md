# Sprint 01 - Cierre de Brechas de Promesa TheoGen

Inicio: 2026-02-28  
Fin objetivo: 2026-03-13  
Meta del sprint: activar gates de calidad para que no salgan reportes con claims sin evidencia y dejar el framework operativo para los 6 casos de uso.

## Estado de arranque
1. Sprint iniciado el 2026-02-28.
2. PR-A (Quality Gate export) en progreso.
3. Tablero semanal activo para seguimiento tecnico + comercial.

## Backlog del sprint (ejecutable)
| ID | Item | Owner | Fecha objetivo | Estado | Riesgo |
|---|---|---|---|---|---|
| PR-A | Quality Gate en export (`claims_without_evidence`) | Backend Lead | 2026-03-03 | completed | medio |
| PR-A.1 | Error 422 estructurado para export bloqueado | Backend Lead | 2026-03-03 | completed | bajo |
| PR-A.2 | Test API de bloqueo de export | QA/Backend | 2026-03-03 | completed | bajo |
| PR-A.3 | Pre-check de readiness de export (API + UI) | Backend + Frontend | 2026-03-04 | completed | bajo |
| PR-B | Hardening de `claims/explain` (fallback robusto) | Backend Lead | 2026-03-05 | completed | medio |
| PR-B.1 | Normalizar claims no-dict en fallback | Backend Lead | 2026-03-05 | completed | medio |
| PR-B.2 | Métrica `claim_explain_success_rate` | Data/Platform | 2026-03-05 | completed | medio |
| PR-C | Nuevas plantillas `b2c` y `consulting` | Product + Backend | 2026-03-07 | completed | alto |
| PR-C.1 | `domain_template` soporta `b2c` y `consulting` | Backend Lead | 2026-03-06 | completed | medio |
| PR-C.2 | Presets dashboard alineados 1:1 con templates reales | Frontend Lead | 2026-03-07 | completed | bajo |
| PR-D | Exportes directivos (decision framework + limites) | Backend/Frontend | 2026-03-10 | completed | medio |
| PR-E | Privacidad por defecto (seudonimos + PII gate) | Backend Lead | 2026-03-12 | completed | alto |
| PR-F | SOW comercial por fases y criterios de aceptacion | Comercial + Product | 2026-03-04 | completed | bajo |
| PR-G | Trazabilidad fuerte claim-evidence (resolucion auditable) | Backend Lead | 2026-03-06 | completed | alto |
| PR-G.1 | Gate bloquea referencias de evidencia no resolubles | Backend Lead | 2026-03-06 | completed | medio |
| PR-G.2 | Catalogo `evidence_ids` persistido en validacion de teoria | Backend Lead | 2026-03-06 | completed | medio |
| PR-H | KPI real de explainabilidad de claims en SLO | Data/Platform | 2026-03-07 | completed | medio |
| PR-I | Fallback de transcripcion con segmentos trazables | Backend Lead | 2026-03-07 | completed | medio |
| PR-J | Activacion por entorno + validacion automatica de runtime teorico | Backend Lead | 2026-03-08 | completed | medio |
| PR-J.1 | Perfiles `development/staging/production` para judge/sync en Foundry | Backend Lead | 2026-03-08 | completed | medio |
| PR-J.2 | Health expone estado de configuracion teorica y degrada si hay incoherencias | Backend + Platform | 2026-03-08 | completed | bajo |

## Criterios de aceptacion del sprint
1. Ningun export "Apto" con `claims_without_evidence > 0`.
2. Endpoint de export devuelve 422 con detalle de calidad cuando bloquea.
3. Cobertura de pruebas para gate de export en backend.
4. Definicion aprobada de nuevas plantillas `b2c` y `consulting`.
5. Script comercial y SOW actualizados para no sobreprometer.

## Cadencia operativa
1. Daily tecnico-comercial: 15 min (09:00).
2. Corte de avance: lunes/miercoles/viernes con semaforo.
3. Demo interna: 2026-03-06.
4. Sprint review: 2026-03-13.

## Semaforo de seguimiento
1. Verde: >= 80% de items comprometidos en fecha.
2. Amarillo: 60-79%.
3. Rojo: < 60% o bloqueo en PR-A/PR-B.

## Registro de avance
### 2026-02-28
1. Se implementa gate inicial de export por `claims_without_evidence`.
2. Se agrega test API para bloqueo de export (422).
3. Se habilita tablero de sprint con owners, fechas y riesgos.
4. Verificacion local: `pytest backend/tests/test_theory_api.py -q` -> 11 tests OK.
5. Se robustece fallback de `claims/explain` para claims en formato mixto (dict/string + `evidence_id` singular).
6. Se agregan 2 tests de regresion de fallback; verificacion local: `pytest backend/tests/test_theory_api.py -q` -> 13 tests OK.
7. Se incorporan plantillas reales `b2c` y `consulting` en backend y validacion API.
8. Se alinean presets/UI de dashboard 1:1 con templates reales (B2C y Consultoria ya no usan `generic`).
9. Verificacion frontend: `npx tsc --noEmit` OK.
10. Se incorpora KPI `claim_explain_success_rate` en endpoint de SLO de pipeline.
11. Verificacion backend final: `pytest backend/tests/test_theory_api.py -q` -> 13 tests OK.
12. Se agrega motor compartido de decision ejecutiva para exportes (GO/PILOT/NO_GO + razones + plan + limites).
13. PDF/PPTX/XLSX incorporan secciones de decision framework, plan de accion y limites.
14. Verificacion de regresion: `pytest backend/tests/test_executive_framework.py backend/tests/test_export_service.py backend/tests/test_theory_api.py -q` -> 19 tests OK.
15. Se agrega redaccion automatica de PII en exportes (email, telefono, RUT/ID largo).
16. Se incorporan tests de privacidad para redaccion de PII.
17. Verificacion de regresion extendida: `pytest backend/tests/test_export_privacy.py backend/tests/test_executive_framework.py backend/tests/test_export_service.py backend/tests/test_theory_api.py -q` -> 21 tests OK.
18. Se agrega privacy gate previo a export (`EXPORT_PRIVACY_GATE_FAILED`) con remediacion estructurada.
19. UI de export muestra mensaje de remediacion cuando backend bloquea por calidad/privacidad.
20. Verificacion final: `pytest backend/tests/test_export_privacy.py backend/tests/test_executive_framework.py backend/tests/test_export_service.py backend/tests/test_theory_api.py -q` -> 23 tests OK.
21. Verificacion frontend final: `npx tsc --noEmit` -> OK.
22. Se agrega endpoint `export/readiness` para pre-check de calidad/privacidad antes de exportar.
23. TheoryViewer muestra estado "Apto para exportar" o "Export bloqueado" con motivo.
24. Verificacion de regresion consolidada: `pytest backend/tests/test_theory_api.py backend/tests/test_export_privacy.py backend/tests/test_executive_framework.py backend/tests/test_export_service.py -q` -> 25 tests OK.
25. Hardening de gate de calidad: export ahora bloquea tambien teorias sin claims trazables (`NO_CLAIMS`) ademas de claims sin evidencia.
26. Endpoint `claims/explain` incorpora `counter_evidence` (evidencia contradictoria) para rutas Neo4j y fallback de validacion.
27. TheoryViewer incorpora bloque visual de "Evidencia contradictoria" por claim para auditoria ejecutiva.
28. Privacidad by design reforzada: redaccion PII antes de indexacion semantica (Qdrant) y sincronizacion de texto de fragmentos a Neo4j en pipeline de codificacion.
29. Redaccion PII aplicada tambien a vectores de resumen de categorias y claims del pipeline teorico para reducir exposicion en busqueda semantica.
30. Verificacion backend hardening: `pytest backend/tests/test_theory_api.py backend/tests/test_export_privacy.py backend/tests/test_executive_framework.py backend/tests/test_neo4j_service_sync.py -q` -> 26 tests OK.
31. Verificacion adicional pipeline/export: `pytest backend/tests/test_export_service.py backend/tests/integration/test_theory_graph_input.py -q` -> 10 tests OK.
32. Verificacion frontend hardening: `npm run build` -> OK.
33. Se incorpora `template_policy` en gate de calidad de export por dominio (min claims, min entrevistas cubiertas, bloqueo de `warn_only` para export ejecutivo).
34. `export/readiness` y endpoint de export aplican policy por `domain_template` del proyecto y exponen `blocked_reasons` especificos de plantilla.
35. Se agregan tests de regresion para bloqueos por plantilla (`TEMPLATE_MIN_INTERVIEWS`, `TEMPLATE_WARN_ONLY_NOT_ALLOWED`).
36. Verificacion fase template policy: `pytest backend/tests/test_theory_api.py -q` -> 20 tests OK; `pytest backend/tests/test_export_service.py backend/tests/test_export_privacy.py backend/tests/test_executive_framework.py backend/tests/test_neo4j_service_sync.py backend/tests/integration/test_theory_graph_input.py -q` -> 18 tests OK; `npm run build` -> OK.
37. Se completa cobertura de `template_policy` con tests para minimos estructurales (`TEMPLATE_MIN_PROPOSITIONS`, `TEMPLATE_MIN_CONSEQUENCES`, `TEMPLATE_CONTEXT_REQUIRED`), balance de consecuencias (`TEMPLATE_CONSEQUENCE_BALANCE`) y caso exitoso estricto por plantilla.
38. Se agrega paridad de pruebas para dispatch de export multi-formato (`pptx`, `xlsx`, `png`) y error controlado para formato no soportado en `generate_theory_report`.
39. Verificacion backend actualizada: `pytest backend/tests/test_theory_api.py backend/tests/test_export_service.py -q` -> 30 tests OK.
40. Verificacion regresion complementaria + frontend: `pytest backend/tests/test_export_privacy.py backend/tests/test_executive_framework.py backend/tests/test_neo4j_service_sync.py backend/tests/integration/test_theory_graph_input.py -q` -> 15 tests OK; `npm run build` -> OK.
41. Gate de calidad extiende trazabilidad: bloquea `EVIDENCE_INDEX_MISSING` y `UNRESOLVED_EVIDENCE_REFERENCES` cuando un claim no puede auditar su evidencia referenciada.
42. Pipeline teorico persiste catalogo auditable (`network_metrics_summary.evidence_ids`) y amplia persistencia de `evidence_index` via settings (`THEORY_EVIDENCE_INDEX_PERSIST_MAX`).
43. `claim_metrics` incorpora `claim_explain_success_rate` real por corrida (no proxy) y el endpoint SLO agrega `claim_explain_metric_runs`.
44. Transcripcion fallback ahora genera segmentos sinteticos desde `full_text` cuando no llegan segmentos temporales, asegurando creacion de fragmentos para trazabilidad.
45. Se agregan pruebas para gate de evidencia no resoluble/faltante y para segmentacion de fallback de transcripcion.
46. Verificacion focalizada: `pytest backend/tests/test_theory_api.py backend/tests/test_interviews_processing.py -q` -> 28 tests OK.
47. Verificacion de regresion complementaria: `pytest backend/tests/test_export_service.py backend/tests/test_export_privacy.py backend/tests/test_executive_framework.py backend/tests/test_neo4j_service_sync.py backend/tests/integration/test_theory_graph_input.py -q` -> 22 tests OK.
48. `generated_by` deja de usar valor legacy hardcodeado y queda trazado al modelo real configurado en backend (`MODEL_REASONING_ADVANCED`/`MODEL_CHAT`).
49. Verificacion adicional de pipeline teorico + API: `pytest backend/tests/test_theory_api.py backend/tests/integration/test_theory_graph_input.py -q` -> 32 tests OK.
50. Se implementa control por entorno en settings (`APP_ENV` + `THEORY_ENV_PROFILE`) con defaults operativos Foundry para runtime teorico: `development` (off), `staging` (shadow), `production` (strict).
51. Se agrega validacion automatica de coherencia (`THEORY_CONFIG_ISSUES`) y resumen auditable de runtime (`theory_runtime_config_summary`).
52. Startup registra warning/ok de configuracion teorica y puede bloquear arranque con `THEORY_FAIL_STARTUP_ON_CONFIG_ERRORS=true`.
53. `/health/dependencies` incorpora `pipeline.theory_runtime_config` y pasa a `degraded` si la configuracion teorica tiene brechas.
54. Verificacion de cambios de entorno + health: `pytest backend/tests/test_settings_runtime_config.py backend/tests/test_main_health.py -q` -> 8 tests OK.
