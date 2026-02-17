# Script para actualizar el archivo .env con los valores de los recursos desplegados

Write-Host "Obteniendo valores de los recursos desplegados..." -ForegroundColor Yellow

# Obtener el nombre de la cuenta de almacenamiento
$storageAccount = az resource list --resource-group theogen-rg-eastus --resource-type Microsoft.Storage/storageAccounts --query "[0].name" -o tsv
Write-Host "Cuenta de almacenamiento: $storageAccount" -ForegroundColor Green

# Obtener el host de Redis
$redisResource = az resource list --resource-group theogen-rg-eastus --resource-type Microsoft.Cache/redis --query "[0].name" -o tsv
$redisHostName = az redis show --name $redisResource --resource-group theogen-rg-eastus --query "hostName" -o tsv
Write-Host "Redis Host: $redisHostName" -ForegroundColor Green

# Obtener el endpoint del servicio de Speech
$speechResource = az resource list --resource-group theogen-rg-eastus --resource-type Microsoft.CognitiveServices/accounts --query "[0].name" -o tsv
$speechEndpoint = az cognitiveservices account show --name $speechResource --resource-group theogen-rg-eastus --query "properties.endpoint" -o tsv
Write-Host "Speech Endpoint: $speechEndpoint" -ForegroundColor Green

# Intentar obtener el host de PostgreSQL (puede que aún no esté disponible)
$postgresResource = az resource list --resource-group theogen-rg-eastus --resource-type Microsoft.DBforPostgreSQL/flexibleServers --query "[0].name" -o tsv

if ($postgresResource) {
    $postgresHost = az postgres server show --name $postgresResource --resource-group theogen-rg-eastus --query "fullyQualifiedDomainName" -o tsv
    Write-Host "PostgreSQL Host: $postgresHost" -ForegroundColor Green
}
else {
    Write-Host "PostgreSQL aún no está disponible, intentando obtener detalles del despliegue..." -ForegroundColor Yellow
    $deploymentOperations = az deployment operation group list --resource-group theogen-rg-eastus --name remaining_resources --query "[?properties.targetResource.resourceType=='Microsoft.DBforPostgreSQL/flexibleServers'].properties.targetResource.resourceName" -o tsv
    if ($deploymentOperations) {
        Write-Host "Nombre del servidor PostgreSQL: $deploymentOperations" -ForegroundColor Green
        $postgresHost = "$deploymentOperations.postgres.database.azure.com"
        Write-Host "Host estimado de PostgreSQL: $postgresHost" -ForegroundColor Yellow
    }
    else {
        Write-Host "No se pudo obtener información del PostgreSQL aún" -ForegroundColor Red
        $postgresHost = "<postgresql-no-disponible-actualmente>"
    }
}

# Actualizar el archivo .env con los valores obtenidos
$envContent = Get-Content ".env" -ErrorAction SilentlyContinue
if ($envContent) {
    # Reemplazar valores existentes
    $envContent = $envContent -replace '^AZURE_PG_HOST=.*', "AZURE_PG_HOST=$postgresHost"
    $envContent = $envContent -replace '^AZURE_STORAGE_ACCOUNT=.*', "AZURE_STORAGE_ACCOUNT=$storageAccount"
    $envContent = $envContent -replace '^AZURE_REDIS_HOST=.*', "AZURE_REDIS_HOST=$redisHostName"
    $envContent = $envContent -replace '^AZURE_SPEECH_KEY=.*', "AZURE_SPEECH_KEY=<tu-clave-speech>"
    
    Set-Content -Path ".env" -Value $envContent
    Write-Host "Archivo .env actualizado con los valores disponibles" -ForegroundColor Green
}
else {
    # Crear un archivo .env con los valores obtenidos
    $newEnvContent = @"
# TheoGen Environment Variables

# Azure OpenAI (ya existente en tu cuenta)
AZURE_OPENAI_API_KEY=$env:AZURE_OPENAI_API_KEY
AZURE_OPENAI_ENDPOINT=https://axial-resource.cognitiveservices.azure.com/
AZURE_OPENAI_API_VERSION=2024-05-01-preview

# Modelos ya desplegados
MODEL_REASONING_ADVANCED=DeepSeek-V3.2-Speciale
MODEL_REASONING_FAST=model-router
MODEL_REASONING_EFFICIENT=model-router
MODEL_CHAT=
MODEL_EMBEDDING=text-embedding-3-large
MODEL_TRANSCRIPTION=gpt-4o-transcribe-diarize
MODEL_ROUTER=model-router
MODEL_KIMI=Kimi-K2.5
MODEL_DEEPSEEK=DeepSeek-V3.2-Speciale

# Azure PostgreSQL
AZURE_PG_USER=theogenadmin
AZURE_PG_PASSWORD=TempPass123!
AZURE_PG_HOST=$postgresHost
AZURE_PG_DATABASE=theogen

# Azure Storage
AZURE_STORAGE_ACCOUNT=$storageAccount
AZURE_STORAGE_KEY=<tu-clave-storage>

# Azure AD (Entra ID)
AZURE_AD_TENANT_ID=3e151d68-e5ed-4878-932d-251fe1b0eaf1
AZURE_AD_CLIENT_ID=<tu-client-id>

# Otros servicios
AZURE_SPEECH_KEY=<tu-clave-speech>
AZURE_SPEECH_REGION=westeurope
AZURE_REDIS_HOST=$redisHostName
AZURE_REDIS_KEY=<tu-clave-redis>

# External Managed
NEO4J_URI=<tu-uri-neo4j>
NEO4J_USER=neo4j
NEO4J_PASSWORD=<tu-password-neo4j>

QDRANT_URL=<tu-url-qdrant>
QDRANT_API_KEY=<tu-clave-qdrant>
"@
    Set-Content -Path ".env" -Value $newEnvContent
    Write-Host "Archivo .env creado con los valores obtenidos" -ForegroundColor Green
}

Write-Host "`nRecursos desplegados hasta ahora:" -ForegroundColor Cyan
Write-Host "- Cuenta de almacenamiento: $storageAccount"
Write-Host "- Redis: $redisHostName"
Write-Host "- Speech: $speechEndpoint"
Write-Host "- PostgreSQL: $postgresHost (puede estar aún aprovisionándose)"

Write-Host "`nNOTA: El despliegue puede seguir en curso. Verifica el estado con:" -ForegroundColor Yellow
Write-Host "az deployment group show --resource-group theogen-rg-eastus --name remaining_resources"