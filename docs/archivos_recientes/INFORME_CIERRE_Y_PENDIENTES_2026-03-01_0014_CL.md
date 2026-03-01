# Informe de Cierre y Pendientes - TheoGen

Fecha y hora de corte (Chile): 01-03-2026 00:14 hrs
Estado general: En progreso controlado (cierre tecnico parcial + pendientes criticos definidos)

## 1) Resumen ejecutivo

1. Se cerraron correcciones tecnicas clave reportadas por usuarios:
   - bloqueo perceptible de teorizacion en 25%,
   - polling pesado de entrevistas,
   - perdida de seguimiento al navegar,
   - errores de decodificacion UTF-8 en perfil de sesion.
2. Se implemento baseline de RBAC multi-tenant (Fase 1) en backend, con migracion de `tenant_id` en `projects` y enforcement en endpoints criticos.
3. Se dejaron fuentes open-source self-hosted (Inter y JetBrains Mono) y limpieza de archivos hash no usados.
4. Aun queda pendiente una simplificacion UX fuerte del dashboard para flujo de usuario nuevo.

## 2) Cierre ejecutado

### 2.1 Correcciones funcionales y de estabilidad

1. Teorizacion:
   - Timeout por entrevista en auto-codificacion.
   - Heartbeat de progreso durante etapa `auto_code` para evitar congelamiento visual en 25%.
   - Mejor manejo de error en polling y reanudacion de seguimiento.
2. Entrevistas:
   - Endpoint listado responde payload liviano (sin transcripcion completa).
   - Polling periodico de estado con persistencia local para continuidad.
   - Mensajeria de procesamiento en segundo plano.
3. Codificacion/UTF-8:
   - Decodificacion robusta de payload JWT con `TextDecoder("utf-8")`.

### 2.2 RBAC multi-tenant (Fase 1) - Backend

1. Se agrego `tenant_id` en `projects` (modelo + schema + migracion Alembic).
2. Se implemento condicion de scope compartida por proyecto:
   - `platform_super_admin` -> acceso cross-tenant,
   - `tenant_admin` -> acceso por tenant,
   - usuario normal -> acceso por owner.
3. Enforcement aplicado en APIs principales:
   - projects, interviews, codes, memos, search, theory.
4. Compatibilidad legacy preservada:
   - fallback owner-scope para datos previos y cuentas sin `tid`.

### 2.3 Frontend tipografias self-hosted

1. Se confirmo uso de Inter y JetBrains Mono locales.
2. Se limpiaron archivos hash de fuentes no referenciados.
3. `globals.css` quedo con `@font-face` y `unicode-range` (latin/latin-ext), con pesos 400/700.

## 3) Validaciones realizadas

1. Backend (regresion focalizada RBAC + teoria/export/interviews/sync):
   - `58 passed`.
2. Frontend:
   - `npx tsc --noEmit` OK.
3. Build frontend:
   - compilacion de codigo OK,
   - ejecucion global en entorno local con error `EPERM` (limitacion de entorno), no atribuible a fuente remota.

## 4) Pendientes abiertos y priorizacion

## P0 (critico)

1. `C-04` Alineacion completa de contrato de configuracion/secrets entre app, IaC y pipelines.
2. `C-01-F2` RBAC multi-tenant integral (Fase 2+):
   - tablas de membresias/roles/permisos por tenant,
   - auditoria de eventos sensibles,
   - pruebas negativas inter-tenant por endpoint.

## P1 (alto)

1. Simplificacion UX del dashboard (reduccion de ruido y flujo guiado para usuario nuevo).
2. Migracion de autenticacion fuera de `localStorage` a cookies `HttpOnly`/BFF.
3. Key Vault hardening de red (`publicNetworkAccess`).
4. Pinning estricto de dependencias backend.

## P2 (medio)

1. Cierre de warnings tecnicos:
   - `utcnow` deprecated,
   - `Config` legacy de Pydantic,
   - warning de conexion insegura Qdrant.
2. Mejora de health/readiness y observabilidad operativa.

## 5) Riesgos vigentes

1. Riesgo de experiencia inicial: alto ruido UI puede impactar adopcion.
2. Riesgo de seguridad: mientras no se cierre `C-04` y RBAC completo, no corresponde declarar cierre total de hardening.
3. Riesgo operativo: falta watchdog global de tareas largas de teoria mas alla de timeouts parciales.

## 6) Recomendacion inmediata (siguiente bloque)

1. Ejecutar mini-sprint UX de onboarding en dashboard:
   - flujo lineal de 3 pasos (Subir -> Esperar transcripcion -> Generar teoria),
   - ocultar paneles avanzados por defecto,
   - estado unico visible de progreso.
2. Abrir Fase 2 RBAC con esquema de membresias por tenant y auditoria.
3. Preparar cierre de `C-04` sin intervenir `.env` local, mediante contrato declarativo y validaciones CI.

---

Documento de corte operativo: 01-03-2026 00:14 hrs (Chile).
