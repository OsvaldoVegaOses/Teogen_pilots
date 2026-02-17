#!/usr/bin/env pwsh
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
        throw "Azure CLI no estÃ¡ instalado o no estÃ¡ en el PATH"
    }
    Write-Host "Azure CLI encontrado" -ForegroundColor Green
}
catch {
    Write-Host "Error: Azure CLI no estÃ¡ instalado o no estÃ¡ en el PATH." -ForegroundColor Red
    Write-Host "Por favor, instala Azure CLI desde: https://docs.microsoft.com/en-us/cli/azure/install-azure-cli" -ForegroundColor Yellow
    exit 1
}

# Verificar si estÃ¡ iniciada la sesiÃ³n en Azure
try {
    $account = az account show 2>$null | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0 -or $null -eq $account) {
        throw "No hay sesiÃ³n activa en Azure"
    }
    Write-Host "SesiÃ³n activa en Azure para: $($account.user.name)" -ForegroundColor Green
    Write-Host "SuscripciÃ³n: $($account.name)" -ForegroundColor Green
}
catch {
    Write-Host "Error: No hay sesiÃ³n activa en Azure." -ForegroundColor Red
    Write-Host "Por favor, inicia sesiÃ³n con: az login" -ForegroundColor Yellow
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
    Write-Host "Error: Node.js o npm no estÃ¡n instalados o no estÃ¡n en el PATH." -ForegroundColor Red
    exit 1
}

# Variables del despliegue
$resourceGroupName = "theogen-rg"
$projectName = "theogen"
$location = "East US"
$environment = "prod"

# Crear grupo de recursos si no existe
Write-Host "`nVerificando grupo de recursos..." -ForegroundColor Yellow
$rgExists = az group exists --name $resourceGroupName 2>$null

if ($rgExists -eq "false") {
    Write-Host "Creando grupo de recursos: $resourceGroupName" -ForegroundColor Yellow
    az group create --name $resourceGroupName --location $location --tags Project=TheoGen Environment=$environment
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Error al crear el grupo de recursos" -ForegroundColor Red
        exit 1
    }
    Write-Host "Grupo de recursos creado exitosamente" -ForegroundColor Green
}
else {
    Write-Host "Grupo de recursos $resourceGroupName ya existe" -ForegroundColor Green
}

# Compilar el frontend
Write-Host "`nCompilando el frontend de TheoGen..." -ForegroundColor Yellow

# Cambiar al directorio del frontend
$frontendPath = "c:\Users\osval\OneDrive - ONG Tren Ciudadano\digital skills\Teogen\frontend"
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
    
    # Construir la aplicaciÃ³n para producciÃ³n
    Write-Host "Construyendo la aplicaciÃ³n para producciÃ³n..." -ForegroundColor Yellow
    npm run build
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Error al construir la aplicaciÃ³n" -ForegroundColor Red
        exit 1
    }
    Write-Host "AplicaciÃ³n construida exitosamente" -ForegroundColor Green
}
else {
    Write-Host "Error: No se encuentra el directorio del frontend en $frontendPath" -ForegroundColor Red
    exit 1
}

# Desplegar recursos de Azure con Bicep
Write-Host "`nDesplegando recursos de Azure para el frontend..." -ForegroundColor Yellow

$bicepFile = "c:\Users\osval\OneDrive - ONG Tren Ciudadano\digital skills\Teogen\infra\modules\frontend.fixed.bicep"

if (Test-Path $bicepFile) {
    Write-Host "Usando archivo Bicep: $bicepFile" -ForegroundColor Cyan
    
    # Compilar y desplegar el archivo Bicep
    az deployment group create `
        --resource-group $resourceGroupName `
        --template-file $bicepFile `
        --parameters projectName=$projectName environment=$environment `
        --name "frontend-deployment-$(Get-Date -Format 'yyyyMMddHHmmss')"
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Error al desplegar los recursos de Azure" -ForegroundColor Red
        exit 1
    }
    Write-Host "Recursos de Azure desplegados exitosamente" -ForegroundColor Green
}
else {
    Write-Host "Error: No se encuentra el archivo Bicep en $bicepFile" -ForegroundColor Red
    exit 1
}

# Obtener informaciÃ³n del almacenamiento
Write-Host "`nObteniendo informaciÃ³n del almacenamiento..." -ForegroundColor Yellow

$storageAccountName = az storage account list --resource-group $resourceGroupName --query "[?contains(name, 'theogenfront')].name" -o tsv
if ($storageAccountName) {
    Write-Host "Cuenta de almacenamiento encontrada: $storageAccountName" -ForegroundColor Green
    
    # Obtener la clave de la cuenta de almacenamiento
    $storageKey = az storage account keys list --resource-group $resourceGroupName --account-name $storageAccountName --query "[0].value" -o tsv
    if (!$storageKey) {
        Write-Host "Error al obtener la clave de la cuenta de almacenamiento" -ForegroundColor Red
        exit 1
    }

    # Habilitar hosting de sitio estático (crea el contenedor $web si no existe)
    Write-Host "Habilitando hosting de sitio estático..." -ForegroundColor Yellow
    az storage blob service-properties update `
        --account-name $storageAccountName `
        --static-website `
        --404-document 404.html `
        --index-document index.html
    
    # Subir los archivos compilados al almacenamiento
    Write-Host "Subiendo archivos del frontend al almacenamiento estÃ¡tico..." -ForegroundColor Yellow
    
    $distPath = "$frontendPath\out"
    if (Test-Path $distPath) {
        # Usar az storage blob upload-batch para subir archivos eficientemente
        Write-Host "Iniciando carga masiva con upload-batch..." -ForegroundColor Cyan
        
        az storage blob upload-batch `
            --account-name $storageAccountName `
            --account-key $storageKey `
            --destination '$web' `
            --source $distPath `
            --overwrite
            
        if ($LASTEXITCODE -ne 0) {
            Write-Host "Error al subir archivos con batch." -ForegroundColor Red
            exit 1
        }
        Write-Host "Archivos del frontend subidos exitosamente" -ForegroundColor Green
    }
    else {
        Write-Host "Error: No se encuentra el directorio de salida 'out' en el frontend" -ForegroundColor Red
        Write-Host "   AsegÃºrate de que la compilaciÃ³n de Next.js haya generado el directorio 'out'" -ForegroundColor Yellow
        exit 1
    }
    
    # Mostrar URL del frontend
    $frontendUrl = az storage account show --name $storageAccountName --resource-group $resourceGroupName --query "primaryEndpoints.web" -o tsv
    Write-Host "`nÂ¡Frontend desplegado exitosamente!" -ForegroundColor Green
    Write-Host "URL del frontend: $frontendUrl" -ForegroundColor Cyan
    
    # Si hay CDN, tambiÃ©n mostrar esa URL
    $cdnEndpoint = az cdn endpoint list --profile-name "${projectName}-cdn-$environment" --resource-group $resourceGroupName --query "[0].hostName" -o tsv 2>$null
    if ($cdnEndpoint) {
        Write-Host "URL del CDN: https://$cdnEndpoint" -ForegroundColor Cyan
    }
}
else {
    Write-Host "Error: No se encontrÃ³ la cuenta de almacenamiento del frontend" -ForegroundColor Red
    exit 1
}

Write-Host "`n===========================================" -ForegroundColor Green
Write-Host "    Despliegue del Frontend Completado" -ForegroundColor Green
Write-Host "===========================================" -ForegroundColor Green
Write-Host "El frontend de TheoGen estÃ¡ ahora disponible en Azure." -ForegroundColor Green
Write-Host "Recuerda actualizar la configuraciÃ³n para apuntar al backend correcto." -ForegroundColor Yellow
