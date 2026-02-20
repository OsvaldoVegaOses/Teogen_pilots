# c:\Users\osval\OneDrive - ONG Tren Ciudadano\digital skills\Teogen\deploy_backend.ps1
# Script de despliegue del Backend de TheoGen a Azure Container Apps (Producción)

Write-Host "=========================================" -ForegroundColor Green
Write-Host "Iniciando despliegue de Backend a la Nube" -ForegroundColor Green
Write-Host "=========================================" -ForegroundColor Green

# Configuración de Recursos
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

# 2. Actualizar Container App
Write-Host "`n[2/2] Actualizando Container App con la nueva imagen..." -ForegroundColor Yellow
az containerapp update --name $containerAppName --resource-group $resourceGroup --image "$($acrName).azurecr.io/$imageName"

if ($LASTEXITCODE -ne 0) {
    Write-Host "`n❌ Error al actualizar la Container App." -ForegroundColor Red
    exit 1
}

Write-Host "`n=========================================" -ForegroundColor Green
Write-Host "✅ Backend desplegado exitosamente!" -ForegroundColor Green
Write-Host "URL de la API: https://theogen-backend.gentlemoss-dcba183f.eastus.azurecontainerapps.io/api/docs" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Green