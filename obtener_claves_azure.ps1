# Script para obtener las claves reales de los recursos de Azure

Write-Host "===========================================" -ForegroundColor Green
Write-Host "    Obtención de Claves de Azure" -ForegroundColor Green
Write-Host "===========================================" -ForegroundColor Green

# Verificar si Azure CLI está instalado
try {
    $azVersion = az version 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "Azure CLI no está instalado"
    }
    Write-Host "✅ Azure CLI encontrado" -ForegroundColor Green
} catch {
    Write-Host "❌ Error: Azure CLI no está instalado o no está en el PATH." -ForegroundColor Red
    Write-Host "Por favor, instala Azure CLI desde: https://docs.microsoft.com/en-us/cli/azure/install-azure-cli" -ForegroundColor Yellow
    exit 1
}

# Verificar si está iniciada la sesión en Azure
try {
    $account = az account show 2>$null | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0 -or $null -eq $account) {
        throw "No hay sesión activa en Azure"
    }
    Write-Host "✅ Sesión activa en Azure para: $($account.user.name)" -ForegroundColor Green
    Write-Host "✅ Suscripción: $($account.name)" -ForegroundColor Green
} catch {
    Write-Host "❌ Error: No hay sesión activa en Azure." -ForegroundColor Red
    Write-Host "Por favor, inicia sesión con: az login" -ForegroundColor Yellow
    exit 1
}

# Nombre del grupo de recursos (ajusta según tu configuración)
$resourceGroupName = "theogen-rg"
$projectName = "theogen"

# Intentar encontrar el grupo de recursos
$rgExists = az group exists --name $resourceGroupName 2>$null
if ($rgExists -eq "false") {
    Write-Host "⚠️  Grupo de recursos '$resourceGroupName' no encontrado." -ForegroundColor Yellow
    Write-Host "Buscando grupos de recursos que contengan 'theogen'..." -ForegroundColor Yellow
    
    $rgList = az group list --query "[?contains(name, 'theogen')].name" -o tsv 2>$null
    if ($rgList) {
        $rgListArray = $rgList -split "`n"
        Write-Host "Grupos de recursos encontrados:" -ForegroundColor Cyan
        foreach ($rg in $rgListArray) {
            Write-Host "  - $rg" -ForegroundColor White
        }
        
        $resourceGroupName = Read-Host "Introduce el nombre correcto del grupo de recursos"
    } else {
        Write-Host "❌ No se encontraron grupos de recursos que contengan 'theogen'." -ForegroundColor Red
        $resourceGroupName = Read-Host "Introduce el nombre del grupo de recursos donde están tus recursos"
    }
}

Write-Host "`n🔍 Obteniendo claves de los recursos..." -ForegroundColor Yellow

# Obtener claves de Azure Storage
Write-Host "`n1. Obteniendo claves de Azure Storage..." -ForegroundColor Cyan
$storageAccountName = az storage account list --resource-group $resourceGroupName --query "[0].name" -o tsv 2>$null
if ($storageAccountName -and $storageAccountName -ne "") {
    Write-Host "   Cuenta de almacenamiento encontrada: $storageAccountName" -ForegroundColor Green
    $storageKeys = az storage account keys list --resource-group $resourceGroupName --account-name $storageAccountName | ConvertFrom-Json
    $storageKey = $storageKeys[0].value
    Write-Host "   AZURE_STORAGE_KEY=$storageKey" -ForegroundColor White
    Write-Host "   (Esta clave es muy larga, asegúrate de copiarla completa)" -ForegroundColor Yellow
} else {
    Write-Host "   ❌ No se encontró ninguna cuenta de almacenamiento en el grupo de recursos." -ForegroundColor Red
    Write-Host "   Buscando por nombre que contenga 'theogen'..." -ForegroundColor Yellow
    $storageAccounts = az storage account list --resource-group $resourceGroupName --query "[?contains(name, 'theogen')].name" -o tsv 2>$null
    if ($storageAccounts) {
        $storageAccountName = $storageAccounts.Split("`n")[0]
        Write-Host "   Cuenta de almacenamiento encontrada: $storageAccountName" -ForegroundColor Green
        $storageKeys = az storage account keys list --resource-group $resourceGroupName --account-name $storageAccountName | ConvertFrom-Json
        $storageKey = $storageKeys[0].value
        Write-Host "   AZURE_STORAGE_KEY=$storageKey" -ForegroundColor White
    } else {
        Write-Host "   ❌ No se encontraron cuentas de almacenamiento que coincidan." -ForegroundColor Red
    }
}

# Obtener claves de Redis
Write-Host "`n2. Obteniendo claves de Azure Redis..." -ForegroundColor Cyan
$redisName = az redis list --resource-group $resourceGroupName --query "[0].name" -o tsv 2>$null
if ($redisName -and $redisName -ne "") {
    Write-Host "   Instancia Redis encontrada: $redisName" -ForegroundColor Green
    $redisKey = az redis list-keys --resource-group $resourceGroupName --name $redisName | ConvertFrom-Json
    $primaryKey = $redisKey.primaryKey
    Write-Host "   AZURE_REDIS_KEY=$primaryKey" -ForegroundColor White
    Write-Host "   (Esta clave es muy larga, asegúrate de copiarla completa)" -ForegroundColor Yellow
} else {
    Write-Host "   ❌ No se encontró ninguna instancia de Redis en el grupo de recursos." -ForegroundColor Red
    Write-Host "   Buscando por nombre que contenga 'theogen'..." -ForegroundColor Yellow
    $redisInstances = az redis list --resource-group $resourceGroupName --query "[?contains(name, 'theogen')].name" -o tsv 2>$null
    if ($redisInstances) {
        $redisName = $redisInstances.Split("`n")[0]
        Write-Host "   Instancia Redis encontrada: $redisName" -ForegroundColor Green
        $redisKey = az redis list-keys --resource-group $resourceGroupName --name $redisName | ConvertFrom-Json
        $primaryKey = $redisKey.primaryKey
        Write-Host "   AZURE_REDIS_KEY=$primaryKey" -ForegroundColor White
    } else {
        Write-Host "   ❌ No se encontraron instancias de Redis que coincidan." -ForegroundColor Red
    }
}

# Obtener clave de Cognitive Services (Speech)
Write-Host "`n3. Obteniendo claves de Azure Cognitive Services..." -ForegroundColor Cyan
$cogServicesName = az cognitiveservices account list --resource-group $resourceGroupName --query "[0].name" -o tsv 2>$null
if ($cogServicesName -and $cogServicesName -ne "") {
    Write-Host "   Servicio cognitivo encontrado: $cogServicesName" -ForegroundColor Green
    $cogKeys = az cognitiveservices account keys regenerate --resource-group $resourceGroupName --name $cogServicesName --key-name key1 | ConvertFrom-Json
    $speechKey = $cogKeys.key1
    Write-Host "   AZURE_SPEECH_KEY=$speechKey" -ForegroundColor White
    Write-Host "   (Esta clave es muy larga, asegúrate de copiarla completa)" -ForegroundColor Yellow
} else {
    Write-Host "   ❌ No se encontró ninguna cuenta de Cognitive Services en el grupo de recursos." -ForegroundColor Red
    Write-Host "   Buscando por nombre que contenga 'theogen' o 'axial'..." -ForegroundColor Yellow
    $cogServicesAll = az cognitiveservices account list --resource-group $resourceGroupName --query "[*]" -o json 2>$null | ConvertFrom-Json
    $cogServicesMatch = $cogServicesAll | Where-Object { $_.name -like "*theogen*" -or $_.name -like "*axial*" }
    if ($cogServicesMatch.Count -gt 0) {
        $cogServicesName = $cogServicesMatch[0].name
        Write-Host "   Servicio cognitivo encontrado: $cogServicesName" -ForegroundColor Green
        $cogKeys = az cognitiveservices account keys regenerate --resource-group $resourceGroupName --name $cogServicesName --key-name key1 | ConvertFrom-Json
        $speechKey = $cogKeys.key1
        Write-Host "   AZURE_SPEECH_KEY=$speechKey" -ForegroundColor White
    } else {
        Write-Host "   ❌ No se encontraron cuentas de Cognitive Services que coincidan." -ForegroundColor Red
    }
}

# Obtener información de PostgreSQL
Write-Host "`n4. Obteniendo información de PostgreSQL..." -ForegroundColor Cyan
$pgServerName = az postgres flexible-server list --resource-group $resourceGroupName --query "[0].name" -o tsv 2>$null
if ($pgServerName -and $pgServerName -ne "") {
    Write-Host "   Servidor PostgreSQL encontrado: $pgServerName" -ForegroundColor Green
    $pgInfo = az postgres flexible-server show --resource-group $resourceGroupName --name $pgServerName | ConvertFrom-Json
    Write-Host "   AZURE_PG_HOST=$($pgInfo.fullyQualifiedDomainName)" -ForegroundColor White
    Write-Host "   AZURE_PG_USER=$($pgInfo.administratorLogin)" -ForegroundColor White
    # La contraseña no se puede recuperar, solo verificar si el servidor existe
    Write-Host "   (La contraseña debe ser la misma que usaste durante la creación)" -ForegroundColor Yellow
} else {
    Write-Host "   ❌ No se encontró ningún servidor PostgreSQL Flexible en el grupo de recursos." -ForegroundColor Red
    Write-Host "   Buscando servidores PostgreSQL que contengan 'theogen'..." -ForegroundColor Yellow
    $pgServers = az postgres flexible-server list --resource-group $resourceGroupName --query "[?contains(name, 'theogen')].name" -o tsv 2>$null
    if ($pgServers) {
        $pgServerName = $pgServers.Split("`n")[0]
        Write-Host "   Servidor PostgreSQL encontrado: $pgServerName" -ForegroundColor Green
        $pgInfo = az postgres flexible-server show --resource-group $resourceGroupName --name $pgServerName | ConvertFrom-Json
        Write-Host "   AZURE_PG_HOST=$($pgInfo.fullyQualifiedDomainName)" -ForegroundColor White
        Write-Host "   AZURE_PG_USER=$($pgInfo.administratorLogin)" -ForegroundColor White
        Write-Host "   (La contraseña debe ser la misma que usaste durante la creación)" -ForegroundColor Yellow
    } else {
        Write-Host "   ❌ No se encontraron servidores PostgreSQL que coincidan." -ForegroundColor Red
    }
}

Write-Host "`n===========================================" -ForegroundColor Green
Write-Host "    Instrucciones para actualizar .env" -ForegroundColor Green
Write-Host "===========================================" -ForegroundColor Green
Write-Host ""
Write-Host "1. Abre el archivo .env en la raíz del proyecto" -ForegroundColor White
Write-Host "2. Reemplaza los valores provisionales con los obtenidos arriba:" -ForegroundColor White
Write-Host "   - AZURE_STORAGE_KEY con la clave de almacenamiento obtenida" -ForegroundColor White
Write-Host "   - AZURE_REDIS_KEY con la clave de Redis obtenida" -ForegroundColor White
Write-Host "   - AZURE_SPEECH_KEY con la clave de Cognitive Services obtenida" -ForegroundColor White
Write-Host ""
Write-Host "3. Para AZURE_AD_CLIENT_ID necesitas:" -ForegroundColor White
Write-Host "   - Ir a Azure Portal > Microsoft Entra ID > Registros de aplicaciones" -ForegroundColor White
Write-Host "   - Crear o encontrar una aplicación registrada para TheoGen" -ForegroundColor White
Write-Host "   - Copiar el Application (client) ID" -ForegroundColor White
Write-Host ""
Write-Host "4. Guarda el archivo .env actualizado" -ForegroundColor White
Write-Host ""
Write-Host "✅ ¡Listo! Ahora puedes ejecutar TheoGen con los valores reales." -ForegroundColor Green