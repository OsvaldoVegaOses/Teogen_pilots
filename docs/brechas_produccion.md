# brechas_produccion

Fecha de evaluacion: 2026-02-27  
Proyecto: TheoGen  
Resultado ejecutivo: `NO-GO` para produccion hasta cerrar brechas criticas.

## Actualizacion de estado (2026-02-27, posterior al primer diagnostico)

- `C-01` reforzada en backend con:
  - scoping por `user_id` para usuarios normales;
  - scoping por `tenant_id` para usuarios con rol admin de tenant (`ASSISTANT_TENANT_ADMIN_ROLES`);
  - `tenant_id` persistido en logs y leads del asistente.
  - endpoint `/assistant/authenticated/ops` restringido a admin de tenant (403 para no-admin).
  - `profile/me` expone `can_view_assistant_ops` y el dashboard oculta el panel ops sin ese permiso.
- `C-02` cerrada: modulo `storage.bicep` unificado y compilacion Bicep verificada.
- `C-03` cerrada: pipeline CI agregada en `.github/workflows/ci.yml` (frontend, backend, infra).
- Pendiente estrategico: evolucionar de scoping por usuario a RBAC multi-tenant completo (ver `docs/plan_modelo_acceso_admin_tenant.md`).

## 1) Alcance y evidencia usada

Se revisaron backend, frontend, scripts de despliegue e infraestructura (Bicep), y se ejecutaron validaciones minimas locales.

Validaciones ejecutadas:

- `frontend`: `npm run lint` (OK)
- `frontend`: `npm run build` (OK)
- `backend`: `pytest backend/tests -q` (OK, `36 passed`, `21 warnings`)

## 2) Resumen ejecutivo de brechas

Brechas criticas detectadas: 4  
Brechas altas detectadas: 8  
Brechas medias detectadas: 6

Bloqueadores principales para produccion:

1. Falta pipeline CI/CD y gates de calidad automatizados.
2. Riesgo de exposicion de datos operativos del asistente entre usuarios autenticados.
3. Drift/errores de IaC (modulo `storage.bicep` duplicado e inconsistente).
4. Desalineacion de nombres de secretos/env vars para OpenAI/Foundry entre app e IaC.

## 3) Hallazgos criticos (bloqueantes)

### C-01 Exposicion de datos operativos del asistente a usuarios autenticados (sin scoping por tenant/proyecto)

- Severidad: `Critica`
- Evidencia:
  - `backend/app/api/assistant.py:435` (`/authenticated/metrics`)
  - `backend/app/api/assistant.py:452` y `backend/app/api/assistant.py:461` (conteos globales)
  - `backend/app/api/assistant.py:472` (`/authenticated/ops`)
  - `backend/app/api/assistant.py:482` y `backend/app/api/assistant.py:485` (ultimos logs/leads globales)
- Riesgo:
  - Cualquier usuario autenticado puede ver metricas y registros globales del asistente.
  - Riesgo legal/compliance (datos personales y trazas operativas).
- Criterio de cierre:
  - Filtrado obligatorio por organizacion/tenant/proyecto y rol.
  - Endpoints de operaciones solo para rol admin/ops.
  - Pruebas de autorizacion negativas (usuario A no ve datos de B).

### C-02 IaC con conflicto estructural en `storage.bicep`

- Severidad: `Critica`
- Evidencia:
  - `infra/modules/storage.bicep:3` (`param location`)
  - `infra/modules/storage.bicep:22` (`param location` duplicado)
  - `infra/modules/storage.bicep:7` y `infra/modules/storage.bicep:25` (dos recursos de storage distintos en un mismo modulo)
- Riesgo:
  - Riesgo de fallo de compilacion/despliegue o despliegues no deterministas.
  - Bloquea IaC confiable para produccion.
- Criterio de cierre:
  - Separar en modulo unico y valido (sin parametros duplicados).
  - `az bicep build` exitoso para todos los modulos y ejemplos.
  - Pipeline de validacion IaC en PR.

### C-03 Ausencia de pipeline CI/CD formal

- Severidad: `Critica`
- Evidencia:
  - `.github/workflows` sin archivos (conteo: `0`).
- Riesgo:
  - Sin control obligatorio de lint/test/build/security en cada cambio.
  - Alto riesgo de regresiones y despliegues manuales inconsistentes.
- Criterio de cierre:
  - Pipeline minimo con jobs de:
    - `frontend`: lint + build
    - `backend`: tests + linters
    - validacion IaC (Bicep)
    - escaneo de secretos y dependencias
  - Reglas de branch protection con checks obligatorios.

### C-04 Desalineacion de variables/secretos entre app e infraestructura

- Severidad: `Critica`
- Evidencia:
  - App espera `AZURE_OPENAI_API_KEY` en `backend/app/core/settings.py:30`
  - `.env.example` usa `AZURE_OPENAI_API_KEY` en `.env.example:4`
  - IaC examples inyectan `AZURE_OPENAI_KEY` en:
    - `infra/examples/deploy-eastus-full.bicep:53`
    - `infra/examples/deploy-eastus-full.bicep:113`
    - `infra/examples/deploy-theogen-backend.bicep:19`
- Riesgo:
  - El backend puede iniciar sin clave esperada o con configuracion inconsistente.
  - Incidentes de runtime y fallos de integracion en produccion.
- Criterio de cierre:
  - Estandarizar nombre unico de secreto/env var en app + IaC + scripts.
  - Smoke test de arranque con validacion explicita de variables requeridas.

## 4) Hallazgos altos

### H-01 CORS amplio y permisivo para dominios estaticos

- Evidencia:
  - `backend/app/main.py:88` (`allow_origin_regex=r"https://.*\.z13\.web\.core\.windows\.net"`)
  - `backend/app/main.py:90` y `backend/app/main.py:91` (`allow_methods=["*"]`, `allow_headers=["*"]`)
- Riesgo:
  - Aumento de superficie de ataque y origenes no deseados.
- Accion:
  - Lista explicita de origenes por ambiente; eliminar regex comodin en prod.

### H-02 Tokens de autenticacion en `localStorage`

- Evidencia:
  - `frontend/src/lib/msalConfig.ts:18` (`cacheLocation: "localStorage"`)
  - `frontend/src/lib/googleAuth.ts:29` y `frontend/src/lib/googleAuth.ts:39`
- Riesgo:
  - Exposicion de tokens ante XSS.
- Accion:
  - Migrar a cookies `HttpOnly` + `Secure` + `SameSite` o estrategia BFF.

### H-03 Endpoint API con fallback a `localhost` en build/runtime

- Evidencia:
  - `frontend/src/lib/api.ts:6` (fallback `http://localhost:8000/api`)
- Riesgo:
  - Configuracion incorrecta en produccion por variable faltante.
- Accion:
  - Fallar build si no existe `NEXT_PUBLIC_API_BASE_URL` en entorno productivo.

### H-04 Key Vault con acceso de red publico habilitado

- Evidencia:
  - `infra/modules/keyvault.bicep:20` (`publicNetworkAccess: 'Enabled'`)
- Riesgo:
  - Mayor exposicion de plano de datos, aun con RBAC.
- Accion:
  - Restringir a private endpoints o reglas de red estrictas.

### H-05 Despliegues manuales con valores hardcodeados por ambiente

- Evidencia:
  - `deploy_frontend_fixed.ps1:105` a `deploy_frontend_fixed.ps1:108` (URL/API IDs hardcodeadas)
  - `deploy_backend.ps1:10` a `deploy_backend.ps1:13` (nombres de recursos hardcodeados)
- Riesgo:
  - Error humano, drift entre ambientes y baja repetibilidad.
- Accion:
  - Parametrizar todo con variables de entorno/Key Vault y usar pipeline declarativo.

### H-06 Contenedor backend sin usuario no-root y sin `HEALTHCHECK` en Dockerfile

- Evidencia:
  - `backend/Dockerfile` sin instruccion `USER`
  - `backend/Dockerfile` sin instruccion `HEALTHCHECK`
- Riesgo:
  - Menor postura de seguridad y observabilidad de estado del contenedor.
- Accion:
  - Crear usuario no privilegiado + healthcheck interno.

### H-07 Container Apps sin probes declaradas en IaC

- Evidencia:
  - `infra/modules/containerapp.bicep` define recursos y escalado, pero no `probes`.
- Riesgo:
  - Deteccion tardia de instancias degradadas y recuperacion menos confiable.
- Accion:
  - Configurar `startup`, `liveness` y `readiness` probes.

### H-08 Dependencias backend sin version pinneada

- Evidencia:
  - `backend/requirements.txt` sin versiones fijas (ej. `fastapi`, `sqlalchemy[asyncio]`, etc.).
- Riesgo:
  - Builds no reproducibles y regresiones por cambios de terceros.
- Accion:
  - Pinnear versiones (`==`) y mantener lock/actualizacion controlada.

## 5) Hallazgos medios

### M-01 Sin telemetria APM centralizada detectada

- Evidencia:
  - Busqueda de `appinsights/opentelemetry/sentry/prometheus` sin hallazgos en `backend`, `frontend`, `infra`.
- Riesgo:
  - Dificulta detectar y diagnosticar incidentes en produccion.
- Accion:
  - Instrumentar API y frontend con trazas, metricas, logs correlacionados.

### M-02 Endpoint `/health` demasiado basico

- Evidencia:
  - `backend/app/main.py:110` a `backend/app/main.py:112` retorna solo `{"status":"healthy"}`.
- Riesgo:
  - Puede reportar saludable aunque dependencias criticas fallen.
- Accion:
  - Unificar liveness/readiness y usar `/health/dependencies` para readiness.

### M-03 Inicializacion de esquema assistant en runtime con `create_all`

- Evidencia:
  - `backend/app/assistant_database.py:86`
- Riesgo:
  - Cambios de esquema fuera de control de migraciones versionadas.
- Accion:
  - Migrar assistant DB a Alembic y eliminar `create_all` en runtime.

### M-04 Frontend sin suite de tests automatizados

- Evidencia:
  - `frontend/package.json` solo incluye `dev/build/start/lint`.
- Riesgo:
  - Menor capacidad para detectar regresiones funcionales de UI.
- Accion:
  - Incorporar al menos pruebas unitarias de componentes criticos y smoke e2e.

### M-05 CDN permite HTTP

- Evidencia:
  - `infra/modules/frontend.bicep:66` (`isHttpAllowed: true`)
- Riesgo:
  - Riesgo de trafico no cifrado/redirect mal gestionado.
- Accion:
  - Forzar HTTPS (`isHttpAllowed: false`) y politicas de seguridad.

### M-06 Warnings tecnicos que deben cerrarse antes de escalamiento

- Evidencia de ejecucion de tests:
  - `qdrant_service`: warning por API key sobre conexion insegura.
  - Multiples warnings de Pydantic v2 (`class-based config` deprecada).
- Riesgo:
  - Deuda tecnica que puede derivar en fallos en upgrades.
- Accion:
  - Forzar TLS correcto para Qdrant y migrar esquemas a `ConfigDict`.

## 6) Estado actual de calidad tecnica (positivo)

- Frontend compila en modo produccion.
- Lint frontend en verde.
- Backend tests en verde (`32 passed`).
- Existen tests para endpoint de health dependencies (`backend/tests/test_main_health.py`).

Esto reduce riesgo base, pero no compensa las brechas de seguridad, operacion e infraestructura listadas arriba.

## 7) Plan de cierre recomendado (30 dias)

### Fase 1 (0-7 dias) - bloqueo de salida

1. Corregir C-01 (scoping y RBAC de endpoints ops/metrics).
2. Corregir C-02 (refactor de `storage.bicep` y validacion IaC).
3. Corregir C-04 (normalizacion de secretos/env vars OpenAI/Foundry).
4. Crear pipeline CI minimo (C-03) con checks obligatorios.

### Fase 2 (8-15 dias) - seguridad y hardening

1. Endurecer CORS (H-01).
2. Sacar tokens de `localStorage` (H-02).
3. Bloquear Key Vault publico y forzar red privada (H-04).
4. Eliminar fallback productivo a localhost (H-03).
5. Forzar HTTPS en CDN (M-05).

### Fase 3 (16-30 dias) - confiabilidad operativa

1. Probes y healthchecks (H-06, H-07, M-02).
2. Telemetria APM y alertas (M-01).
3. Migraciones formales para assistant DB (M-03).
4. Pinned dependencies + politica de actualizaciones (H-08).
5. Tests frontend basicos (M-04).

## 8) Criterio Go/No-Go propuesto

Para declarar `GO` a produccion:

1. Cerrar 100% de brechas criticas (C-01 a C-04).
2. Cerrar al menos 75% de brechas altas.
3. Pipeline CI/CD activo con branch protection.
4. Despliegue reproducible sin hardcode de ambiente.
5. Evidencia de smoke test post-deploy y monitoreo activo.

## 9) Conclusiones

El software muestra buen avance funcional (build y tests en verde), pero todavia no cumple un umbral seguro y operable de produccion por brechas criticas en seguridad de datos, automatizacion de entrega e infraestructura declarativa.

Recomendacion final: mantener estado `NO-GO` hasta cerrar C-01, C-02, C-03 y C-04.
