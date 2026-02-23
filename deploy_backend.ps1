# .\deploy_backend.ps1
# Script de despliegue del Backend de TheoGen a Azure Container Apps (Producción)

Write-Host "=========================================" -ForegroundColor Green
Write-Host "Iniciando despliegue de Backend a la Nube" -ForegroundColor Green
Write-Host "=========================================" -ForegroundColor Green

# Configuración de Recursos
$subscriptionId = "0fbf8e45-6f68-43bb-acbc-36747f267122"
$resourceGroup = "theogen-rg-eastus"
$containerAppName = "theogen-backend"
$acrName = "ca39bdb671caacr"
$imageName = "theogen-backend:latest"

# Verificar inicio de sesión en Azure
Write-Host "`nVerificando sesión en Azure..." -ForegroundColor Yellow
$account = az account show --query "name" -o tsv 2>$null
if ($null -eq $account) {
    Write-Host "❌ Error: No hay sesión activa en Azure. Por favor ejecuta 'az login' primero." -ForegroundColor Red
    exit 1
}
Write-Host "Conectado como: $account" -ForegroundColor Cyan

# Fijar suscripción objetivo
Write-Host "Estableciendo suscripción objetivo..." -ForegroundColor Yellow
az account set --subscription $subscriptionId
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Error al seleccionar la suscripción $subscriptionId." -ForegroundColor Red
    exit 1
}

# Verificar acceso al ACR
Write-Host "Verificando acceso al ACR..." -ForegroundColor Yellow
$loginServer = az acr show --name $acrName --query "loginServer" -o tsv 2>$null
if ([string]::IsNullOrWhiteSpace($loginServer)) {
    Write-Host "❌ Error: No se pudo verificar el ACR $acrName." -ForegroundColor Red
    exit 1
}
Write-Host "ACR detectado: $loginServer" -ForegroundColor Cyan

# 1. Construir imagen en ACR
# El comando se ejecuta desde la raíz del proyecto para incluir el contexto de la carpeta backend
Write-Host "`n[1/2] Construyendo imagen en Azure Container Registry (ACR)..." -ForegroundColor Yellow
Write-Host "Esto puede tardar unos minutos dependiendo del tamaño de las dependencias." -ForegroundColor Gray

az acr build --registry $acrName --image $imageName ./backend

if ($LASTEXITCODE -ne 0) {
    Write-Host "`n❌ Error al construir la imagen en ACR." -ForegroundColor Red
    exit 1
}
Write-Host "✅ Imagen construida y almacenada en $acrName.azurecr.io/$imageName" -ForegroundColor Green

# 2. Forzar nueva revisión con suffix único (evita que ACA ignore el mismo tag :latest)
$revisionSuffix = "deploy-$(Get-Date -Format 'yyMMdd-HHmm')"
Write-Host "`n[2/2] Creando nueva revisión: $revisionSuffix ..." -ForegroundColor Yellow

az containerapp update `
    --name $containerAppName `
    --resource-group $resourceGroup `
    --image "$($acrName).azurecr.io/$imageName" `
    --revision-suffix $revisionSuffix `
    --output none 2>&1 | Out-Null

# az containerapp update devuelve exit code 1 por warnings de progreso en stderr aunque haya éxito.
# Verificamos directamente el estado de la revisión.
Start-Sleep -Seconds 5
$latestRevision = az containerapp show --name $containerAppName --resource-group $resourceGroup `
    --query "properties.latestRevisionName" -o tsv 2>$null
$provisioningState = az containerapp show --name $containerAppName --resource-group $resourceGroup `
    --query "properties.provisioningState" -o tsv 2>$null
$fqdn = az containerapp show --name $containerAppName --resource-group $resourceGroup `
    --query "properties.configuration.ingress.fqdn" -o tsv 2>$null

Write-Host "Revisión activa: $latestRevision" -ForegroundColor Cyan
Write-Host "Estado provisioning: $provisioningState" -ForegroundColor Cyan

if ($provisioningState -ne "Succeeded") {
    Write-Host "`n⚠️ Estado actual: $provisioningState — el deploy puede estar en curso." -ForegroundColor Yellow
    Write-Host "Ejecuta para verificar:" -ForegroundColor Gray
    Write-Host "  az containerapp show -n $containerAppName -g $resourceGroup --query properties.provisioningState -o tsv" -ForegroundColor Gray
    Write-Host "Si queda atascado en InProgress:" -ForegroundColor Yellow
    Write-Host "  1) az containerapp delete --name $containerAppName --resource-group $resourceGroup --yes --no-wait" -ForegroundColor Gray
    Write-Host "  2) az containerapp create --name $containerAppName --resource-group $resourceGroup --yaml containerapp_create.yaml" -ForegroundColor Gray
    exit 1
}

Write-Host "`n=========================================" -ForegroundColor Green
Write-Host "✅ Backend desplegado exitosamente!" -ForegroundColor Green
Write-Host "Revisión: $latestRevision" -ForegroundColor Cyan
Write-Host "URL de la API: https://$fqdn/api/docs" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Green

Write-Host "`nPara ver logs en vivo:" -ForegroundColor Gray
Write-Host "  az containerapp logs show -g $resourceGroup -n $containerAppName --follow --tail 50" -ForegroundColor Gray