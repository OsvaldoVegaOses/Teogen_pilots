# Log Analytics Workspace — Theogen

**Workspace:** `workspace-theogenrgeastusEBUH`  
**Resource Group:** `theogen-rg-eastus`  
**Subscription:** `0fbf8e45-6f68-43bb-acbc-36747f267122`  
**Customer ID (para KQL):** se obtiene con el comando de la sección "Configuración".

Todos los recursos del proyecto envían métricas y logs a este workspace con el
diagnostic setting llamado **`theogen-diag`**, configurado el 22/02/2026.

---

## Recursos conectados

| Recurso | Tipo | Logs | Métricas |
|---------|------|------|----------|
| `theogen-redis-wpdxe2pvgl7o6` | Redis | `ConnectedClientList` | `AllMetrics` |
| `theogen-pg` | PostgreSQL Flexible Server | `allLogs` | `AllMetrics` |
| `theoGenprod` | Key Vault | `allLogs` | `AllMetrics` |
| `ca39bdb671caacr` | Azure Container Registry | `allLogs` | `AllMetrics` |
| `theogenstwpdxe2pvgl7o6` | Storage Account (backend audio) | — | `Transaction`, `Capacity` |
| `theogenstwpdxe2pvgl7o6/blobServices/default` | Blob Service (audio) | `allLogs` | `Transaction` |
| `theogenfrontwpdxe2pv` | Storage Account (frontend SPA) | — | `Transaction`, `Capacity` |
| `theogen-env` | Container App Managed Environment | `allLogs` | `AllMetrics` |
| `theogen-speech-wpdxe2pvgl7o6` | Azure Speech (Cognitive Services) | `RequestResponse`, `Audit` | `AllMetrics` |

> **Nota:** Los logs del Container App `theogen-backend` llegan a través del
> Managed Environment `theogen-env` (tablas `ContainerAppConsoleLogs` y
> `ContainerAppSystemLogs`).

---

## Tablas KQL disponibles

| Tabla | Contenido |
|-------|-----------|
| `ContainerAppConsoleLogs` | stdout/stderr del backend (FastAPI, uvicorn) |
| `ContainerAppSystemLogs` | Eventos del sistema de Container Apps (scaling, restarts) |
| `AzureDiagnostics` | Speech, Key Vault, PostgreSQL, ACR, Redis |
| `AzureMetrics` | Métricas numéricas de todos los recursos |
| `StorageBlobLogs` | Operaciones read/write/delete del blob storage |

---

## Comandos az CLI

### Obtener el Customer ID del workspace

```powershell
az monitor log-analytics workspace show `
  -g theogen-rg-eastus `
  -n workspace-theogenrgeastusEBUH `
  --query customerId -o tsv
```

### Ejecutar una consulta KQL desde la terminal

```powershell
$wsId = az monitor log-analytics workspace show `
  -g theogen-rg-eastus `
  -n workspace-theogenrgeastusEBUH `
  --query customerId -o tsv

az monitor log-analytics query `
  -w $wsId `
  --analytics-query "<QUERY_KQL>" `
  -o table
```

---

## Consultas KQL de referencia

### Container App — logs del backend (últimas 2 horas)

```kql
ContainerAppConsoleLogs
| where TimeGenerated > ago(2h)
| where ContainerAppName == "theogen-backend"
| project TimeGenerated, Stream, Log
| order by TimeGenerated desc
| take 200
```

### Container App — errores y excepciones

```kql
ContainerAppConsoleLogs
| where TimeGenerated > ago(24h)
| where ContainerAppName == "theogen-backend"
| where Log has_any ("ERROR", "Exception", "Traceback", "CRITICAL")
| project TimeGenerated, Stream, Log
| order by TimeGenerated desc
```

### Container App — pipeline de teoría (pasos y duración)

```kql
ContainerAppConsoleLogs
| where TimeGenerated > ago(24h)
| where ContainerAppName == "theogen-backend"
| where Log has "[theory]"
| project TimeGenerated, Log
| order by TimeGenerated asc
```

### Container App — eventos del sistema (reinicios, escalado)

```kql
ContainerAppSystemLogs
| where TimeGenerated > ago(24h)
| project TimeGenerated, Reason, Log, ContainerAppName
| order by TimeGenerated desc
```

---

### Speech — resumen de errores por código HTTP (últimas 24h)

```kql
AzureDiagnostics
| where TimeGenerated > ago(24h)
| where ResourceType == "ACCOUNTS"
| where Category in ("RequestResponse", "Audit")
| summarize Count = count() by ResultSignature, bin(TimeGenerated, 1h)
| order by TimeGenerated desc
```

### Speech — tasa de éxito vs error

```kql
AzureDiagnostics
| where TimeGenerated > ago(24h)
| where ResourceType == "ACCOUNTS"
| where Category == "RequestResponse"
| summarize
    Total = count(),
    Exitosos = countif(ResultSignature == "200"),
    Errores = countif(ResultSignature != "200")
| extend TasaExito = round(100.0 * Exitosos / Total, 1)
```

### Speech — distribución de códigos de error

```kql
AzureDiagnostics
| where TimeGenerated > ago(24h)
| where ResourceType == "ACCOUNTS"
| where Category == "RequestResponse"
| where ResultSignature != "200"
| summarize Count = count() by ResultSignature
| order by Count desc
```

---

### PostgreSQL — consultas lentas (> 1 segundo)

```kql
AzureDiagnostics
| where TimeGenerated > ago(24h)
| where ResourceProvider == "MICROSOFT.DBFORPOSTGRESQL"
| where Category == "PostgreSQLLogs"
| where Message has "duration"
| extend DurationMs = extract(@"duration: ([0-9.]+) ms", 1, Message, typeof(real))
| where DurationMs > 1000
| project TimeGenerated, DurationMs, Message
| order by DurationMs desc
```

### PostgreSQL — errores de conexión

```kql
AzureDiagnostics
| where TimeGenerated > ago(24h)
| where ResourceProvider == "MICROSOFT.DBFORPOSTGRESQL"
| where Category == "PostgreSQLLogs"
| where Message has_any ("error", "fatal", "connection refused")
| project TimeGenerated, Message
| order by TimeGenerated desc
```

### PostgreSQL — métricas de CPU y conexiones activas

```kql
AzureMetrics
| where TimeGenerated > ago(24h)
| where ResourceProvider == "MICROSOFT.DBFORPOSTGRESQL"
| where MetricName in ("cpu_percent", "active_connections", "storage_percent", "memory_percent")
| summarize AvgValue = avg(Average), MaxValue = max(Maximum) by MetricName, bin(TimeGenerated, 30m)
| order by TimeGenerated desc
```

---

### Redis — clientes conectados y operaciones por segundo

```kql
AzureMetrics
| where TimeGenerated > ago(24h)
| where ResourceProvider == "MICROSOFT.CACHE"
| where MetricName in ("connectedclients", "totalcommandssecond", "cachehits", "cachemisses", "usedmemorypercentage")
| summarize AvgValue = avg(Average), MaxValue = max(Maximum) by MetricName, bin(TimeGenerated, 30m)
| order by TimeGenerated desc
```

### Redis — lista de clientes conectados

```kql
AzureDiagnostics
| where TimeGenerated > ago(6h)
| where ResourceProvider == "MICROSOFT.CACHE"
| where Category == "ConnectedClientList"
| project TimeGenerated, properties_s
| order by TimeGenerated desc
| take 50
```

---

### Key Vault — accesos a secretos

```kql
AzureDiagnostics
| where TimeGenerated > ago(24h)
| where ResourceProvider == "MICROSOFT.KEYVAULT"
| where OperationName == "SecretGet"
| project TimeGenerated, CallerIPAddress, identity_claim_appid_g, id_s, ResultType
| order by TimeGenerated desc
```

### Key Vault — operaciones fallidas

```kql
AzureDiagnostics
| where TimeGenerated > ago(24h)
| where ResourceProvider == "MICROSOFT.KEYVAULT"
| where ResultType != "Success"
| project TimeGenerated, OperationName, CallerIPAddress, ResultType, properties_s
| order by TimeGenerated desc
```

---

### ACR — imágenes pusheadas y pulleadas

```kql
AzureDiagnostics
| where TimeGenerated > ago(7d)
| where ResourceProvider == "MICROSOFT.CONTAINERREGISTRY"
| where Category == "ContainerRegistryRepositoryEvents"
| project TimeGenerated, OperationName, identity_s, repository_s, tag_s, loginServer_s
| order by TimeGenerated desc
```

---

### Storage Blob (audio) — operaciones de subida y descarga

```kql
StorageBlobLogs
| where TimeGenerated > ago(24h)
| where AccountName == "theogenstwpdxe2pvgl7o6"
| summarize Count = count() by OperationName, StatusCode, bin(TimeGenerated, 1h)
| order by TimeGenerated desc
```

### Storage Blob — errores de escritura (fallos de upload de audio)

```kql
StorageBlobLogs
| where TimeGenerated > ago(24h)
| where AccountName == "theogenstwpdxe2pvgl7o6"
| where StatusCode >= 400
| project TimeGenerated, OperationName, StatusCode, StatusText, ObjectKey, CallerIpAddress
| order by TimeGenerated desc
```

---

### Vista general — salud de todos los recursos (últimas 6h)

```kql
union
  (ContainerAppConsoleLogs
   | where TimeGenerated > ago(6h)
   | where Log has_any ("ERROR", "CRITICAL")
   | summarize Errores = count() by Recurso = "Backend (CA)"),
  (AzureDiagnostics
   | where TimeGenerated > ago(6h)
   | where ResourceProvider == "MICROSOFT.COGNITIVESERVICES"
   | where ResultSignature != "200"
   | summarize Errores = count() by Recurso = "Speech"),
  (AzureDiagnostics
   | where TimeGenerated > ago(6h)
   | where ResourceProvider == "MICROSOFT.DBFORPOSTGRESQL"
   | where Message has_any ("error", "fatal")
   | summarize Errores = count() by Recurso = "PostgreSQL"),
  (AzureDiagnostics
   | where TimeGenerated > ago(6h)
   | where ResourceProvider == "MICROSOFT.KEYVAULT"
   | where ResultType != "Success"
   | summarize Errores = count() by Recurso = "KeyVault")
| order by Errores desc
```

---

## Ejemplo completo — ejecutar desde Azure Cloud Shell o PowerShell local

```powershell
# 1. Obtener workspace ID
$wsId = az monitor log-analytics workspace show `
  -g theogen-rg-eastus `
  -n workspace-theogenrgeastusEBUH `
  --query customerId -o tsv

# 2. Consultar logs del backend (últimas 2h)
$query = @"
ContainerAppConsoleLogs
| where TimeGenerated > ago(2h)
| where ContainerAppName == 'theogen-backend'
| where Log has_any ('ERROR','[theory]','WARN')
| project TimeGenerated, Log
| order by TimeGenerated desc
| take 100
"@

az monitor log-analytics query -w $wsId --analytics-query $query -o table

# 3. Consultar tasa de éxito de Speech (últimas 24h)
$speechQuery = @"
AzureDiagnostics
| where TimeGenerated > ago(24h)
| where ResourceProvider == 'MICROSOFT.COGNITIVESERVICES'
| summarize Total=count(), OK=countif(ResultSignature=='200'), Err=countif(ResultSignature!='200')
| extend Tasa = round(100.0 * OK / Total, 1)
"@

az monitor log-analytics query -w $wsId --analytics-query $speechQuery -o table
```

---

## Abrir en Azure Portal

```
https://portal.azure.com/#resource/subscriptions/0fbf8e45-6f68-43bb-acbc-36747f267122/resourceGroups/theogen-rg-eastus/providers/Microsoft.OperationalInsights/workspaces/workspace-theogenrgeastusEBUH/logs
```

En el portal puedes pegar directamente cualquier bloque KQL de este documento en la sección **Logs** del workspace.
