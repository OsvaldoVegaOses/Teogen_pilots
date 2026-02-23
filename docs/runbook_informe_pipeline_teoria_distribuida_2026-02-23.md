# Runbook e Informe Tecnico - Pipeline de Teoria Distribuida (Celery + Redis)
# Backend
az deployment group create --resource-group theogen-rg-eastus `
  --template-file infra/examples/deploy-theogen-backend.bicep `
  --parameters managedEnvironmentId="<env-id>" keyVaultId="<kv-id>" redisHost="<redis-host>"

# Worker
az deployment group create --resource-group theogen-rg-eastus `
  --template-file infra/examples/deploy-theogen-worker.bicep `
  --parameters managedEnvironmentId="<env-id>" keyVaultId="<kv-id>" redisHost="<redis-host>"

Fecha de emision: 2026-02-23 02:29:21 -03:00
Proyecto: TheoGen

## 1. Objetivo

Documentar de forma integral los cambios realizados para maximizar rendimiento, robustez y escalabilidad del pipeline de codificacion y generacion de teoria, manteniendo compatibilidad con el contrato API existente (202 + polling).

## 2. Alcance de la implementacion

### 2.1 Backend - Robustez y rendimiento

- Parser JSON robusto para respuestas LLM con caracteres de control y ruido:
  - ackend/app/core/json_utils.py
- Uso de parser robusto en motores:
  - ackend/app/engines/coding_engine.py
  - ackend/app/engines/theory_engine.py
- Optimizacion de codificacion por entrevista:
  - Cache de codigos normalizada en memoria (case-insensitive)
  - Concurrencia configurable por fragmento (CODING_FRAGMENT_CONCURRENCY)
  - Inserciones idempotentes en tabla puente con ON CONFLICT DO NOTHING
  - Batch embeddings + batch upsert Qdrant + batch sync Neo4j
- Sincronizacion de taxonomia en Neo4j por lotes (UNWIND):
  - ackend/app/services/neo4j_service.py (atch_sync_taxonomy)

### 2.2 Backend - Orquestacion de tareas de teoria

- Reestructuracion de estado de tarea con campos observables:
  - status, step, progress, error_code, 
ext_poll_seconds, execution_mode
- Control de concurrencia por proyecto con lock distribuido en Redis:
  - evita ejecuciones duplicadas simultaneas por project_id
- Validacion estricta de multitenencia en endpoint de estado:
  - 	ask_id debe pertenecer a project_id y owner_id
- Recuperacion de lock huerfano (stale lock) para evitar bloqueos falsos.

### 2.3 Ejecucion distribuida (cluster-grade)

- Modo opcional de ejecucion por Celery + Redis (THEORY_USE_CELERY=true):
  - ackend/app/tasks/celery_app.py
  - ackend/app/tasks/theory_tasks.py
  - ackend/start_worker.py
- Encolado desde API con fallback automatico a modo local cuando Celery no aplica.

### 2.4 Configuracion runtime

Se agregaron parametros configurables en ackend/app/core/settings.py:

- DB pool:
  - DB_POOL_SIZE, DB_MAX_OVERFLOW, DB_POOL_TIMEOUT, DB_POOL_RECYCLE
- Redis/Celery:
  - AZURE_REDIS_HOST, AZURE_REDIS_KEY, REDIS_SSL_PORT
  - THEORY_USE_CELERY, CELERY_BROKER_URL, CELERY_RESULT_BACKEND
- Concurrencia pipeline:
  - CODING_FRAGMENT_CONCURRENCY
  - THEORY_INTERVIEW_CONCURRENCY
  - THEORY_STATUS_POLL_HINT_SECONDS
  - THEORY_TASK_LOCK_TTL_SECONDS

### 2.5 Frontend

- Polling adaptativo con backoff para reducir carga:
  - rontend/src/app/dashboard/page.tsx
- Uso de 
ext_poll_seconds y visualizacion de step.

### 2.6 Infraestructura (Bicep)

- Modulo Container App extendido para produccion:
  - infra/modules/containerapp.bicep
  - soporte de command, rgs, dditionalEnv, scaleRules, minReplicas, maxReplicas, ingress opcional
  - soporte de secretos Key Vault e inline
- Deploy backend actualizado para modo Celery:
  - infra/examples/deploy-theogen-backend.bicep
- Nuevo deploy de worker dedicado:
  - infra/examples/deploy-theogen-worker.bicep
- Deploy completo East US actualizado para backend + worker:
  - infra/examples/deploy-eastus-full.bicep

## 3. Runbook operativo

### 3.1 Variables base (VALORES REALES — listo para ejecutar)

```powershell
$RG            = "theogen-rg-eastus"
$LOCATION      = "eastus"
$ENV_ID        = "/subscriptions/0fbf8e45-6f68-43bb-acbc-36747f267122/resourceGroups/theogen-rg-eastus/providers/Microsoft.App/managedEnvironments/theogen-env"
$KV_ID         = "/subscriptions/0fbf8e45-6f68-43bb-acbc-36747f267122/resourceGroups/theogen-rg-eastus/providers/Microsoft.KeyVault/vaults/theoGenprod"
$IMAGE         = "ca39bdb671caacr.azurecr.io/theogen-backend:latest"
$REDIS_HOST    = "theogen-redis-wpdxe2pvgl7o6.redis.cache.windows.net"
```

### 3.2 Secretos requeridos en Key Vault

- zure-openai-api-key
- zure-pg-password
- 
eo4j-password
- qdrant-api-key
- zure-redis-key

Ejemplo:

`powershell
az keyvault secret set --vault-name <keyvault-name> --name azure-redis-key --value "<redis-primary-key>"
`

### 3.3 Despliegue backend

> **Nota:** Los templates Bicep ya usan `identity: 'system'` para ACR — no requieren username/password.
> Antes del primer deploy del backend, asegurarse de que la identidad tenga `acrPull` en el ACR:
> ```powershell
> $BACKEND_PID = az containerapp show -g $RG -n theogen-backend --query identity.principalId -o tsv
> $ACR_ID = az acr show -g $RG -n ca39bdb671caacr --query id -o tsv
> az role assignment create --assignee $BACKEND_PID --role "AcrPull" --scope $ACR_ID
> ```

```powershell
az deployment group create `
  --resource-group $RG `
  --template-file infra/examples/deploy-theogen-backend.bicep `
  --parameters managedEnvironmentId=$ENV_ID keyVaultId=$KV_ID image=$IMAGE redisHost=$REDIS_HOST
```

### 3.4 Despliegue worker

> El worker usa la misma imagen que el backend.
> Asignar `acrPull` a su identidad tras el primer deploy:
> ```powershell
> $WORKER_PID = az containerapp show -g $RG -n theogen-theory-worker --query identity.principalId -o tsv
> az role assignment create --assignee $WORKER_PID --role "AcrPull" --scope $ACR_ID
> ```

```powershell
az deployment group create `
  --resource-group $RG `
  --template-file infra/examples/deploy-theogen-worker.bicep `
  --parameters managedEnvironmentId=$ENV_ID keyVaultId=$KV_ID image=$IMAGE redisHost=$REDIS_HOST
```

### 3.5 Permisos Key Vault para identidades gestionadas

```powershell
$BACKEND_PID = az containerapp show -g $RG -n theogen-backend --query identity.principalId -o tsv
$WORKER_PID  = az containerapp show -g $RG -n theogen-theory-worker --query identity.principalId -o tsv
$KV_SECRETS_USER_ROLE = "4633458b-17de-408a-b874-0445c86b69e6" # Key Vault Secrets User

az role assignment create --assignee-object-id $BACKEND_PID --role $KV_SECRETS_USER_ROLE --scope $KV_ID
az role assignment create --assignee-object-id $WORKER_PID  --role $KV_SECRETS_USER_ROLE --scope $KV_ID
```

### 3.6 Verificaciones post-deploy

```powershell
az containerapp show -g $RG -n theogen-backend --query "properties.template.containers[0].env"
az containerapp show -g $RG -n theogen-theory-worker --query "properties.template.scale"
az containerapp logs show -g $RG -n theogen-theory-worker --tail 200
```

### 3.7 Smoke test funcional

1. Ejecutar POST /api/projects/{project_id}/generate-theory.
2. Verificar respuesta 202 con 	ask_id y execution_mode.
3. Consultar GET /api/projects/{project_id}/generate-theory/status/{task_id}.
4. Validar transicion de step/progress hasta completed o ailed con error_code.

### 3.8 Rollback

```powershell
# fallback a modo local (sin worker)
az containerapp update -g $RG -n theogen-backend --set-env-vars THEORY_USE_CELERY=false

# detener worker
az containerapp update -g $RG -n theogen-theory-worker --min-replicas 0 --max-replicas 0
```

## 4. Validacion tecnica ejecutada

- Compilacion Python (py_compile) de archivos backend modificados: OK.
- Build frontend (
ext build): OK.
- Nota: validacion z bicep build no se pudo ejecutar en este entorno por permisos locales de Azure CLI (C:\Users\osval\.azure\az.sess).

## 5. Riesgos y controles

- Riesgo: lock huerfano en Redis.
  - Control: limpieza y reintento encolado cuando no existe payload de task.
- Riesgo: salida LLM no-JSON valida.
  - Control: parser tolerante + saneamiento de control chars.
- Riesgo: sobrecarga por polling masivo.
  - Control: 
ext_poll_seconds + backoff adaptativo frontend.
- Riesgo: doble ejecucion por proyecto.
  - Control: lock distribuido por project_id.

## 6. Archivos modificados/agregados

### Agregados

- ackend/app/core/json_utils.py
- ackend/app/tasks/celery_app.py
- ackend/app/tasks/theory_tasks.py
- ackend/start_worker.py
- infra/examples/deploy-theogen-worker.bicep

### Modificados

- ackend/app/api/theory.py
- ackend/app/core/settings.py
- ackend/app/database.py
- ackend/app/engines/coding_engine.py
- ackend/app/engines/theory_engine.py
- ackend/app/services/neo4j_service.py
- rontend/src/app/dashboard/page.tsx
- infra/modules/containerapp.bicep
- infra/examples/deploy-theogen-backend.bicep
- infra/examples/deploy-eastus-full.bicep
- README.md

## 7. Estado final

- Pipeline de teoria preparado para ejecucion distribuida con worker dedicado.
- Contrato API compatible con clientes actuales.
- Mejoras de rendimiento y robustez aplicadas en codificacion, teorizacion, sincronizacion Neo4j y polling frontend.

