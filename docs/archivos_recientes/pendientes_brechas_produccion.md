# pendientes_brechas_produccion

Fecha de actualizacion: 2026-02-27  
Estado general: `NO-GO` (pendientes criticos y altos abiertos)

**Resumen de avance:**
- Todos los P1 de hardening no dependientes de variables/configuración han sido implementados y están en main (CORS, Docker USER/HEALTHCHECK, probes, limpieza scripts, localhost fallback).
- Solo quedan pendientes P1 que requieren cambios en autenticación (cookies/BFF), Key Vault y pinning de dependencias.
- Los bloqueos principales siguen siendo C-04 (alineación de configuración/secrets) y RBAC multi-tenant.

## 1) Estado por brecha critica

### C-01 Exposicion de datos ops del asistente

Estado: `En progreso (RBAC fase 1 aplicada), pendiente cierre estructural`  
Avance ya implementado:

- Scoping por `user_id` para usuarios normales.
- Scoping por `tenant_id` para tenant-admin.
- `/assistant/authenticated/ops` devuelve `403` para no-admin.
- `profile/me` expone `can_view_assistant_ops` y el dashboard oculta el panel ops a no autorizados.
- Baseline RBAC multi-tenant en endpoints de negocio con `project_scope_condition` (platform_super_admin / tenant_admin / owner).
- `projects.tenant_id` con migracion de backfill para aislamiento por tenant en capa de proyecto.

Pendiente para cierre total:

- Migrar a RBAC multi-tenant completo en toda la plataforma (no solo asistente), con membresias/roles por tenant en DB.
- Extender enforcement a todos los endpoints de negocio.

### C-02 IaC storage inconsistente

Estado: `Cerrada`

### C-03 Ausencia de CI/CD

Estado: `Cerrada`

### C-04 Desalineacion variables/secretos app vs IaC

Estado: `Abierta (Critica)`  
Observacion operativa:

- Queda pendiente por decision actual de no intervenir `.env` o configuraciones similares en esta fase.

## 2) Pendientes vigentes priorizados

## P0 (Critico)

1. `C-04` Alinear contrato de configuracion/secrets entre backend, IaC y scripts.
2. `C-01-F2` Implementar RBAC multi-tenant integral (modelo de datos + enforcement global).

## P1 (Alto)

1. Endurecer CORS por ambiente (quitar regex abierto en prod). **COMPLETADO**
2. Migrar autenticacion fuera de `localStorage` (cookies `HttpOnly`/BFF). **PENDIENTE**
3. Eliminar fallback `localhost` en frontend productivo. **COMPLETADO**
4. Restringir red de Key Vault (`publicNetworkAccess`). **PENDIENTE**
5. Eliminar hardcodes de scripts de despliegue. **COMPLETADO**
6. Agregar `USER` no-root y `HEALTHCHECK` en imagen backend. **COMPLETADO**
7. Declarar probes de Container Apps (startup/readiness/liveness). **COMPLETADO**
8. Pinning estricto de dependencias backend. **PENDIENTE**

## P2 (Medio)

1. Instrumentacion APM y alertas operativas centralizadas.
2. Health model (liveness/readiness) mas robusto.
3. Formalizar migraciones assistant DB (evitar patching runtime).
4. Agregar tests automatizados frontend.
5. Forzar HTTPS en CDN (deshabilitar HTTP).
6. Cerrar warnings tecnicos (utcnow, Pydantic config, warning Qdrant).

## 3) Bloqueos y restricciones actuales

1. Restriccion vigente: no modificar `.env` ni archivos similares de configuracion/secrets.
2. Implicancia: `C-04` no puede cerrarse completamente hasta levantar o acotar esa restriccion.

## 4) Plan corto recomendado (siguiente iteracion)

1. Cerrar `C-01-F2` con sprint tecnico de RBAC multi-tenant (segun `docs/plan_modelo_acceso_admin_tenant.md`).
2. Ejecutar hardening P1 no dependiente de variables (`CORS`, `ops scripts`, `Docker`, `probes`, `localhost fallback`).
3. Preparar propuesta de cierre `C-04` sin editar `.env` local: contrato de nombres, mapeo y validaciones CI. (no tocar)

## 5) Criterio de salida a produccion

Para pasar a `GO`:

1. `C-04` cerrada.
2. `C-01-F2` cerrada.
3. Al menos 75% de P1 cerradas.
4. Evidencia de pruebas en CI y smoke post-deploy.
