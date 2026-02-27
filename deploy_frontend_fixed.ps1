#!/usr/bin/env pwsh  /// .\deploy_frontend_fixed.ps1
# Script para desplegar el frontend de TheoGen en Azure

Write-Host "===========================================" -ForegroundColor Green
Write-Host "    Despliegue del Frontend de TheoGen" -ForegroundColor Green
Write-Host "===========================================" -ForegroundColor Green

# Verificar prerequisitos
Write-Host "`nVerificando prerequisitos..." -ForegroundColor Yellow

# Verificar Azure CLI
try {
    $azVersion = az version 2>$null | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0 -or $null -eq $azVersion) {
        throw "Azure CLI no está instalado o no está en el PATH"
    }
    Write-Host "Azure CLI encontrado" -ForegroundColor Green
}
catch {
    Write-Host "Error: Azure CLI no está instalado o no está en el PATH." -ForegroundColor Red
    Write-Host "Por favor, instala Azure CLI desde: https://docs.microsoft.com/en-us/cli/azure/install-azure-cli" -ForegroundColor Yellow
    exit 1
}

# Verificar si está iniciada la sesión en Azure
try {
    $account = az account show 2>$null | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0 -or $null -eq $account) {
        throw "No hay sesión activa en Azure"
    }
    Write-Host "Sesión activa en Azure para: $($account.user.name)" -ForegroundColor Green
    Write-Host "Suscripción: $($account.name)" -ForegroundColor Green
}
catch {
    Write-Host "Error: No hay sesión activa en Azure." -ForegroundColor Red
    Write-Host "Por favor, inicia sesión con: az login" -ForegroundColor Yellow
    exit 1
}

# Verificar Node.js y npm
try {
    $nodeVersion = node --version
    $npmVersion = npm --version
    Write-Host "Node.js encontrado: $nodeVersion" -ForegroundColor Green
    Write-Host "npm encontrado: $npmVersion" -ForegroundColor Green
}
catch {
    Write-Host "Error: Node.js o npm no están instalados o no están en el PATH." -ForegroundColor Red
    exit 1
}

# Variables del despliegue
$subscriptionId = "0fbf8e45-6f68-43bb-acbc-36747f267122"
$resourceGroupName = "theogen-rg"
$preferredStorageAccount = "theogenfrontwpdxe2pv"

Write-Host "Estableciendo suscripción objetivo..." -ForegroundColor Yellow
az account set --subscription $subscriptionId
if ($LASTEXITCODE -ne 0) {
    Write-Host "Error al establecer la suscripción $subscriptionId" -ForegroundColor Red
    exit 1
}

Write-Host "Verificando grupo de recursos configurado..." -ForegroundColor Yellow
$rgExists = az group exists --name $resourceGroupName 2>$null
if ($rgExists -ne "true") {
    Write-Host "El grupo $resourceGroupName no existe. Intentando detectar RG de frontend..." -ForegroundColor Yellow
    $detectedRg = az storage account list --query "[?contains(name, 'theogenfront') && name=='$preferredStorageAccount'].resourceGroup | [0]" -o tsv
    if (-not $detectedRg) {
        $detectedRg = az storage account list --query "[?contains(name, 'theogenfront')].resourceGroup | [0]" -o tsv
    }
    if (-not $detectedRg) {
        Write-Host "Error: No fue posible detectar un grupo de recursos con storage de frontend." -ForegroundColor Red
        exit 1
    }
    $resourceGroupName = $detectedRg
    Write-Host "Usando grupo de recursos detectado: $resourceGroupName" -ForegroundColor Cyan
}

# Compilar el frontend
Write-Host "`nCompilando el frontend de TheoGen..." -ForegroundColor Yellow

# Cambiar al directorio del frontend
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$frontendPath = Join-Path $scriptRoot "frontend"
if (Test-Path $frontendPath) {
    Set-Location $frontendPath
    Write-Host "Navegando al directorio: $frontendPath" -ForegroundColor Cyan
    
    # Verificar si hay node_modules, sino instalar dependencias
    if (!(Test-Path "node_modules")) {
        Write-Host "Instalando dependencias del frontend..." -ForegroundColor Yellow
        npm install
        if ($LASTEXITCODE -ne 0) {
            Write-Host "Error al instalar dependencias del frontend" -ForegroundColor Red
            exit 1
        }
        Write-Host "Dependencias instaladas" -ForegroundColor Green
    }
    
    # Construir la aplicación para producción
    Write-Host "Construyendo la aplicación para producción..." -ForegroundColor Yellow
    # Inyectar variables de entorno para que Next.js las incluya en el build estático
    Write-Host "Inyectando variables de entorno para el build..." -ForegroundColor Cyan
    $env:NEXT_PUBLIC_API_BASE_URL = "https://theogen-backend.gentlemoss-dcba183f.eastus.azurecontainerapps.io/api"
    $env:NEXT_PUBLIC_AZURE_AD_TENANT_ID = "3e151d68-e5ed-4878-932d-251fe1b0eaf1"
    $env:NEXT_PUBLIC_AZURE_AD_CLIENT_ID = "c6d2cf71-dcd2-4400-a8be-9eb8c16b1174"
    $env:NEXT_PUBLIC_GOOGLE_CLIENT_ID = "791433802772-l7sul60hr03kq7i2u7m32bd6jrn8lalo.apps.googleusercontent.com"
    
    npm run build
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Error al construir la aplicación" -ForegroundColor Red
        exit 1
    }
    Write-Host "Aplicación construida exitosamente" -ForegroundColor Green
}
else {
    Write-Host "Error: No se encuentra el directorio del frontend en $frontendPath" -ForegroundColor Red
    exit 1
}

# Obtener información del almacenamiento
Write-Host "`nObteniendo información del almacenamiento..." -ForegroundColor Yellow

$storageAccountName = az storage account show --resource-group $resourceGroupName --name $preferredStorageAccount --query name -o tsv 2>$null
if (-not $storageAccountName) {
    Write-Host "No se encontró la cuenta preferida '$preferredStorageAccount'. Buscando alternativa por prefijo..." -ForegroundColor Yellow
    $storageAccountName = az storage account list --resource-group $resourceGroupName --query "[?contains(name, 'theogenfront')].name | [0]" -o tsv
}

if ($storageAccountName) {
    Write-Host "Cuenta de almacenamiento encontrada: $storageAccountName" -ForegroundColor Green
    
    # Obtener la clave de la cuenta de almacenamiento
    $storageKey = az storage account keys list --resource-group $resourceGroupName --account-name $storageAccountName --query "[0].value" -o tsv
    if (!$storageKey) {
        Write-Host "Error al obtener la clave de la cuenta de almacenamiento" -ForegroundColor Red
        exit 1
    }
    
    # Subir los archivos compilados al almacenamiento
    Write-Host "Subiendo archivos del frontend al almacenamiento estático..." -ForegroundColor Yellow
    
    $distPath = "$frontendPath\out"
    if (Test-Path $distPath) {
        # Limpiar archivos obsoletos del contenedor antes de subir (evita stale files)
        Write-Host "Limpiando archivos obsoletos en el contenedor `$web..." -ForegroundColor Yellow
        az storage blob delete-batch `
            --account-name $storageAccountName `
            --account-key $storageKey `
            --source '$web' `
            --output none 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Write-Host "Advertencia: no se pudo limpiar el contenedor `$web (puede estar vacío)." -ForegroundColor Yellow
        } else {
            Write-Host "Contenedor `$web limpiado correctamente." -ForegroundColor Green
        }

        # Usar az storage blob upload-batch para subir todo el directorio de una vez
        # Es mucho más rápido y maneja las rutas relativas correctamente
        az storage blob upload-batch `
            --account-name $storageAccountName `
            --account-key $storageKey `
            --destination '$web' `
            --source $distPath `
            --overwrite true
        
        if ($LASTEXITCODE -ne 0) {
            Write-Host "Error al subir los archivos del frontend" -ForegroundColor Red
            exit 1
        }
        Write-Host "Archivos del frontend subidos exitosamente" -ForegroundColor Green
    }
    else {
        Write-Host "Error: No se encuentra el directorio de salida 'out' en el frontend" -ForegroundColor Red
        Write-Host "   Asegúrate de que la compilación de Next.js haya generado el directorio 'out'" -ForegroundColor Yellow
        exit 1
    }
    
    # Mostrar URL del frontend
    $frontendUrl = az storage account show --name $storageAccountName --resource-group $resourceGroupName --query "primaryEndpoints.web" -o tsv
    Write-Host "`n¡Frontend desplegado exitosamente!" -ForegroundColor Green
    Write-Host "URL del frontend: $frontendUrl" -ForegroundColor Cyan
    
}
else {
    Write-Host "Error: No se encontró la cuenta de almacenamiento del frontend" -ForegroundColor Red
    exit 1
}

Write-Host "`n===========================================" -ForegroundColor Green
Write-Host "    Despliegue del Frontend Completado" -ForegroundColor Green
Write-Host "===========================================" -ForegroundColor Green
Write-Host "El frontend de TheoGen está ahora disponible en Azure." -ForegroundColor Green
Write-Host "Recuerda actualizar la configuración para apuntar al backend correcto." -ForegroundColor Yellow
