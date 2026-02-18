# Script para desplegar los recursos restantes de TheoGen (Corregido para East US)

Write-Host "=========================================" -ForegroundColor Green
Write-Host "Desplegando recursos restantes de TheoGen" -ForegroundColor Green
Write-Host "=========================================" -ForegroundColor Green

# Verificar si estamos logueados en Azure
$account = az account show --query "name" -o tsv 2>$null
if ($null -eq $account) {
    Write-Host "Por favor inicia sesión en Azure primero usando 'az login'" -ForegroundColor Red
    exit
}

Write-Host "Usando cuenta de Azure: $account" -ForegroundColor Cyan

# Asegurarse de que estamos en el directorio correcto
Set-Location -Path "infra"

# Generar contraseña segura para PostgreSQL
$adminPassword = -join ((65..90) + (97..122) + (48..57) | Get-Random -Count 16 | ForEach-Object { [char]$_ })
$adminPassword += "!" # Asegurar complejidad

# Variables del despliegue
$resourceGroupName = "theogen-rg-eastus"
$projectName = "theogen"
$location = "eastus"

# Crear grupo de recursos si no existe
Write-Host "`nVerificando grupo de recursos..." -ForegroundColor Yellow
$rgExists = az group exists --name $resourceGroupName 2>$null

if ($rgExists -eq "false") {
    Write-Host "Creando grupo de recursos: $resourceGroupName" -ForegroundColor Yellow
    az group create --name $resourceGroupName --location $location
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Error al crear el grupo de recursos" -ForegroundColor Red
        exit 1
    }
    Write-Host "Grupo de recursos creado exitosamente" -ForegroundColor Green
}
else {
    Write-Host "Grupo de recursos $resourceGroupName ya existe" -ForegroundColor Green
}

Write-Host "Desplegando recursos restantes (esto puede tomar varios minutos)..."
$deployment = az deployment group create `
    --resource-group $resourceGroupName `
    --template-file remaining_resources.bicep `
    --parameters projectName=$projectName adminPassword=$adminPassword `
    --output json | ConvertFrom-Json

if ($deployment.properties.provisioningState -eq "Succeeded") {
    Write-Host "¡Despliegue de recursos restantes completado exitosamente!" -ForegroundColor Green
    Write-Host "`n--- Configuración de Recursos ---" -ForegroundColor Yellow
    Write-Host "PostgreSQL Host: $($deployment.properties.outputs.postgresHost.value)"
    Write-Host "PostgreSQL User: theogenadmin"
    Write-Host "PostgreSQL Password: (Guardada en .env)"
    Write-Host "Redis Host: $($deployment.properties.outputs.redisHostName.value)"
    Write-Host "Storage Account: $($deployment.properties.outputs.storageAccountName.value)"
    Write-Host "Speech Endpoint: $($deployment.properties.outputs.speechEndpoint.value)"
    Write-Host "-------------------------------------"
    
    # Actualizar el archivo .env con los nuevos valores
    $envContent = Get-Content "../.env" -ErrorAction SilentlyContinue
    if ($envContent) {
        # Reemplazar valores existentes o agregar nuevos
        $envContent = $envContent -replace '^AZURE_PG_HOST=.*', "AZURE_PG_HOST=$($deployment.properties.outputs.postgresHost.value)"
        # La contraseña generada se guarda aquí
        $envContent = $envContent -replace '^AZURE_PG_PASSWORD=.*', "AZURE_PG_PASSWORD=$adminPassword"
        $envContent = $envContent -replace '^AZURE_STORAGE_ACCOUNT=.*', "AZURE_STORAGE_ACCOUNT=$($deployment.properties.outputs.storageAccountName.value)"
        $envContent = $envContent -replace '^AZURE_REDIS_HOST=.*', "AZURE_REDIS_HOST=$($deployment.properties.outputs.redisHostName.value)"
        $envContent = $envContent -replace '^AZURE_SPEECH_KEY=.*', "AZURE_SPEECH_KEY=<tu-clave-speech>"
        
        # Si alguna línea no existe, agregarla
        if ($envContent -notmatch '^AZURE_PG_HOST=') {
            $envContent += "`nAZURE_PG_HOST=$($deployment.properties.outputs.postgresHost.value)"
        }
        if ($envContent -notmatch '^AZURE_REDIS_HOST=') {
            $envContent += "`nAZURE_REDIS_HOST=$($deployment.properties.outputs.redisHostName.value)"
        }
        if ($envContent -notmatch '^AZURE_SPEECH_KEY=') {
            $envContent += "`nAZURE_SPEECH_KEY=<tu-clave-speech>"
        }
        
        Set-Content -Path "../.env" -Value $envContent
        Write-Host "`nArchivo .env actualizado con los nuevos valores" -ForegroundColor Green
    }
    else {
        # Crear un nuevo archivo .env si no existe
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
AZURE_PG_PASSWORD=$adminPassword
AZURE_PG_HOST=$($deployment.properties.outputs.postgresHost.value)
AZURE_PG_DATABASE=theogen

# Azure Storage
AZURE_STORAGE_ACCOUNT=$($deployment.properties.outputs.storageAccountName.value)
AZURE_STORAGE_KEY=<tu-clave-storage>

# Azure AD (Entra ID)
AZURE_AD_TENANT_ID=<tu-tenant-id>
AZURE_AD_CLIENT_ID=<tu-client-id>

# Otros servicios
AZURE_SPEECH_KEY=<tu-clave-speech>
AZURE_SPEECH_REGION=westeurope
AZURE_REDIS_HOST=$($deployment.properties.outputs.redisHostName.value)
AZURE_REDIS_KEY=<tu-clave-redis>

# External Managed
NEO4J_URI=<tu-uri-neo4j>
NEO4J_USER=neo4j
NEO4J_PASSWORD=<tu-password-neo4j>

QDRANT_URL=<tu-url-qdrant>
QDRANT_API_KEY=<tu-clave-qdrant>
"@
        Set-Content -Path "../.env" -Value $newEnvContent
        Write-Host "`nArchivo .env creado con los nuevos valores" -ForegroundColor Green
    }
    
    Write-Host "`n¡IMPORTANTE: Guarda la contraseña de PostgreSQL y actualiza las claves faltantes en el archivo .env!" -ForegroundColor Red
}
else {
    Write-Host "Falló el despliegue de recursos restantes." -ForegroundColor Red
}
