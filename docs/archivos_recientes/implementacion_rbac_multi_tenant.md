# Implementacion RBAC Multi-Tenant (Fase 1)

Fecha: 2026-03-01
Estado: En progreso (baseline tecnico aplicado)

## Objetivo de esta fase

Cerrar el primer tramo de `C-01-F2` con enforcement multi-tenant en backend sin romper compatibilidad con el modelo legacy por `owner_id`.

## Cambios implementados

1. Baseline de roles en configuracion:
   - `PLATFORM_SUPER_ADMIN_ROLES`
   - `TENANT_ADMIN_ROLES`
2. Scope efectivo por usuario:
   - `CurrentUser.effective_tenant_id`
   - fallback `user:<user_uuid>` cuando no existe `tid` en token.
3. Helpers de autorizacion compartidos:
   - `project_scope_condition(user)`
   - `verify_project_access(project_id, user, db)`
   - `resolve_project_tenant_id(user)`
4. `projects` ahora persiste `tenant_id` y lo expone en schema de respuesta.
5. Migracion Alembic:
   - agrega `projects.tenant_id`
   - backfill de datos legacy
   - indice por tenant y tenant+created_at
6. Enforcement aplicado a endpoints de negocio:
   - `projects`, `interviews`, `codes`, `memos`, `search`, `theory`
7. Ajuste de compatibilidad en teoria:
   - `claims/explain` consulta Neo4j con `project.owner_id` real para soportar tenant admin sobre proyectos no propios.
8. Pruebas:
   - nuevas pruebas de scope (`test_project_access_scope.py`)
   - regresion backend ejecutada en endpoints criticos.

## Regla de acceso aplicada (Fase 1)

1. `platform_super_admin`: acceso cross-tenant.
2. `tenant_admin` con `tenant_id`: acceso a proyectos del tenant.
3. Resto de usuarios: acceso por `owner_id`.
4. Compatibilidad legacy:
   - tenant admin puede seguir viendo proyectos legacy propios con `tenant_id IS NULL`.

## Resultados de validacion

- Suite focalizada: 58 tests OK.
- Bloque de teoria/export/interviews/sync sin regresiones en pruebas.

## Pendiente para cierre completo de C-01-F2

1. Modelo completo de membresias y permisos por tenant:
   - `tenants`, `roles`, `permissions`, `tenant_memberships`, `audit_logs`, etc.
2. Agregar `tenant_id` en entidades hijas (ademas de scoping por join con project).
3. Endpoints de administracion de tenant/usuarios/invitaciones.
4. Auditoria de acciones sensibles en API.
5. Pruebas negativas de aislamiento inter-tenant por cada endpoint critico en CI.
