# Plan Modelo de Acceso Admin/Tenant

Fecha: 2026-02-27  
Alcance: TheoGen (Chile y El Salvador)  
Objetivo: definir y ejecutar un modelo de acceso multi-tenant alineado al negocio (B2C, sector publico, ONG, consultoras, educacion/colegios).

## 1) Principios de diseno

1. Aislamiento estricto de datos por tenant.
2. Menor privilegio por defecto.
3. Roles por segmento de negocio y por nivel territorial (SLEP/Distrito/Colegio).
4. Trazabilidad completa de acciones sensibles.
5. Modelo extensible para nuevos paises y segmentos.

## 2) Unidad de tenancy (propuesta)

Entidad principal: `tenant` (organizacion contratante).

Tipos de tenant:

- `b2c_individual`
- `colegio`
- `slep` (Chile)
- `distrito` (El Salvador)
- `ong`
- `consultora`
- `institucion_publica`

Jerarquia (cuando aplica):

- `tenant` padre: `slep` o `distrito`
- `tenant` hijo: `colegio`

Regla clave:

- Todo `project`, `interview`, `code`, `memo`, `theory`, `assistant_log`, `lead` debe llevar `tenant_id`.

## 3) Roles objetivo

### Plataforma (TheoGen)

- `platform_super_admin`: acceso total cross-tenant (solo equipo central).
- `platform_support`: soporte acotado, sin lectura de contenido sensible por defecto.

### Tenant (organizacion)

- `tenant_owner`: responsable contractual y configuracion global del tenant.
- `tenant_admin`: administracion funcional, usuarios, proyectos y politicas.
- `billing_admin`: facturacion/licencias.

### Red educativa (SLEP/Distrito)

- `network_admin`: administra colegios del territorio.
- `network_analyst`: lectura agregada inter-colegio (sin acceso indebido a datos nominales).

### Colegio

- `school_director`: vision de proyectos del colegio.
- `convivencia_lead`: gestion operativa de convivencia y seguimiento.
- `school_analyst`: analisis y reportes.
- `interviewer`: captura/transcripcion/carga.
- `viewer`: solo lectura.

### Investigacion / ONG / Consultora

- `research_lead`: dirige estudios, define equipos y exportes.
- `research_analyst`: analisis cualitativo y reportes.
- `field_interviewer`: levantamiento de entrevistas.

## 4) Matriz minima de permisos (v1)

Permisos base:

- `project:create`, `project:read`, `project:update`, `project:delete`
- `interview:upload`, `interview:read`
- `coding:run`, `coding:read`
- `theory:generate`, `theory:read`, `export:download`
- `assistant:ops:read`
- `tenant:users:manage`, `tenant:settings:manage`
- `billing:read`, `billing:manage`

Reglas:

1. `assistant:ops:read` solo dentro del `tenant_id` del usuario.
2. Roles de red (`network_*`) ven agregados del territorio, no contenido crudo por defecto.
3. Acceso cross-tenant solo para `platform_super_admin`.

## 5) Arquitectura de autorizacion (recomendada)

Modelo hibrido:

- `RBAC` para rol principal.
- `ABAC` para atributos (`tenant_id`, `country`, `tenant_type`, `school_id`, `project_scope`).

Resolucion de acceso por request:

1. Validar identidad (JWT Entra/Google).
2. Resolver membresias del usuario (`tenant_memberships`).
3. Aplicar policy engine (rol + atributos + accion + recurso).
4. Aplicar filtro de datos en query (`WHERE tenant_id = ...`).
5. Registrar `audit_log`.

## 6) Cambios de datos y backend (implementacion)

## 6.1 Nuevas tablas

- `tenants`
- `tenant_hierarchy`
- `roles`
- `permissions`
- `role_permissions`
- `tenant_memberships`
- `audit_logs`
- `invitations`

## 6.2 Migraciones de entidades existentes

Agregar `tenant_id` (no nulo) en:

- `projects` (ademas de `owner_id`)
- `interviews`, `codes`, `categories`, `memos`, `theories`
- `assistant_message_logs`, `assistant_contact_leads`

Indices recomendados:

- `(tenant_id, created_at)`
- `(tenant_id, project_id)`
- `(tenant_id, user_id)`

## 6.3 Enforcement en API

- Crear dependencias reutilizables:
  - `get_current_membership()`
  - `require_permission("...")`
  - `require_project_access(project_id, action)`
- Prohibir queries sin `tenant_id`.
- Validar ownership jerarquico para SLEP/Distrito -> Colegio.

## 7) Roadmap propuesto (6 semanas)

### Semana 1: Definicion funcional

1. Acordar taxonomia final de roles por segmento.
2. Acordar politicas de visibilidad por pais/segmento.
3. Cerrar matriz de permisos v1.

### Semana 2: Datos y migraciones

1. Crear tablas RBAC/tenant.
2. Migrar datos actuales (`owner_id -> tenant_membership` inicial).
3. Backfill de `tenant_id` en tablas historicas.

### Semana 3: Backend authorization core

1. Implementar middlewares/dependencies de autorizacion.
2. Incorporar filtros obligatorios por `tenant_id`.
3. Activar auditoria de eventos sensibles.

### Semana 4: Endpoints criticos

1. Proyectos, entrevistas, codificacion, teoria, assistant.
2. Endpoints de administracion de tenant y usuarios.
3. Pruebas de aislamiento entre tenants.

### Semana 5: UX admin y operacion

1. Consola admin tenant (usuarios, roles, invitaciones).
2. Flujos de alta para colegio/SLEP/Distrito/ONG/consultora/B2C.
3. Runbooks soporte y protocolo break-glass.

### Semana 6: Hardening y go-live

1. Pentest enfocado en IDOR/cross-tenant.
2. Pruebas de carga con aislamiento multi-tenant.
3. Checklist go-live y despliegue gradual.

## 8) Criterios de aceptacion

1. Usuario de tenant A no puede leer ni inferir datos de tenant B.
2. Cada endpoint sensible requiere permiso explicito.
3. Toda accion administrativa queda en `audit_logs`.
4. Soporte operativo sin acceso por defecto a contenido sensible.
5. Pruebas automaticas de autorizacion (positivas y negativas) en CI.

## 9) Riesgos y mitigaciones

- Riesgo: complejidad inicial de roles.
  - Mitigacion: iniciar con matriz v1 corta y extender por feature flags.
- Riesgo: migracion de datos legacy.
  - Mitigacion: backfill en fases + validaciones de integridad.
- Riesgo: friccion comercial por diferencias de segmentos.
  - Mitigacion: plantillas de tenant preconfiguradas por segmento.

## 10) Decision inmediata sugerida

Adoptar ya un baseline de 3 niveles:

1. `platform_super_admin`
2. `tenant_admin`
3. `tenant_member`

Y evolucionar en iteracion 2 hacia roles especificos de `SLEP/Distrito/Colegio/ONG/Consultora/B2C`.
