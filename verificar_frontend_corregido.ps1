#!/usr/bin/env pwsh
# Script para verificar la configuracion del frontend de TheoGen

Write-Host "===========================================" -ForegroundColor Green
Write-Host "    Verificar Configuracion Frontend" -ForegroundColor Green
Write-Host "===========================================" -ForegroundColor Green

# Ruta del frontend
$frontendPath = "c:\Users\osval\OneDrive - ONG Tren Ciudadano\digital skills\Teogen\frontend"

# Verificar que el directorio existe
if (!(Test-Path $frontendPath)) {
    Write-Host "ERROR: No se encuentra el directorio de frontend en $frontendPath" -ForegroundColor Red
    exit 1
}

Write-Host "OK Directorio de frontend encontrado" -ForegroundColor Green

# Navegar al directorio de frontend
Set-Location $frontendPath

# Verificar archivos importantes
Write-Host ""
Write-Host "Verificando archivos importantes..." -ForegroundColor Yellow

$importantFiles = @(
    "package.json",
    "next.config.ts",
    "tsconfig.json",
    ".env.local",
    "src/app/page.tsx",
    "src/app/layout.tsx",
    "src/components/InterviewUpload.tsx",
    "src/components/CodeExplorer.tsx",
    "src/components/MemoManager.tsx"
)

foreach ($file in $importantFiles) {
    if (Test-Path $file) {
        Write-Host "OK $file - Encontrado" -ForegroundColor Green
    } else {
        Write-Host "ERROR $file - No encontrado" -ForegroundColor Red
    }
}

# Verificar dependencias
Write-Host ""
Write-Host "Verificando dependencias..." -ForegroundColor Yellow

if (Test-Path "node_modules") {
    Write-Host "OK node_modules - Encontrado (dependencias instaladas)" -ForegroundColor Green
} else {
    Write-Host "ADVERTENCIA node_modules - No encontrado (ejecuta npm install)" -ForegroundColor Yellow
}

# Verificar package.json
Write-Host ""
Write-Host "Analizando package.json..." -ForegroundColor Yellow
if (Test-Path "package.json") {
    try {
        $packageJson = Get-Content "package.json" -Raw | ConvertFrom-Json
        Write-Host "OK Version de Next.js: $($packageJson.dependencies.next)" -ForegroundColor Green
        Write-Host "OK Version de React: $($packageJson.dependencies.react)" -ForegroundColor Green
        Write-Host "OK Version de React DOM: $($packageJson.dependencies.'react-dom')" -ForegroundColor Green
    } catch {
        Write-Host "ERROR Error al leer package.json" -ForegroundColor Red
    }
}

# Verificar archivo .env.local
Write-Host ""
Write-Host "Verificando archivo de configuracion .env.local..." -ForegroundColor Yellow
if (Test-Path ".env.local") {
    Write-Host "OK .env.local - Encontrado" -ForegroundColor Green
    $envContent = Get-Content ".env.local"
    foreach ($line in $envContent) {
        if ($line.Trim() -and !$line.StartsWith("#")) {
            Write-Host "   linea: $line" -ForegroundColor Cyan
        }
    }
} else {
    Write-Host "ERROR .env.local - No encontrado" -ForegroundColor Red
    Write-Host "   Creando archivo de ejemplo..." -ForegroundColor Yellow
    @"
# Variables de entorno para el frontend de TheoGen

# URL del backend de TheoGen
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api

# Configuracion de Azure AD (Entra ID) para autenticacion
NEXT_PUBLIC_AZURE_AD_TENANT_ID=3e151d68-e5ed-4878-932d-251fe1b0eaf1
NEXT_PUBLIC_AZURE_AD_CLIENT_ID=c6d2cf71-dcd2-4400-a8be-9eb8c16b1174

# Otras configuraciones si son necesarias
NEXT_PUBLIC_APP_NAME=TheoGen
NEXT_PUBLIC_VERSION=1.0.0
"@ | Out-File -FilePath ".env.local" -Encoding UTF8
    Write-Host "OK .env.local - Creado con valores predeterminados" -ForegroundColor Green
}

# Verificar estructura de directorios
Write-Host ""
Write-Host "Verificando estructura de directorios..." -ForegroundColor Yellow

$expectedDirs = @(
    "src/app",
    "src/components",
    "public"
)

foreach ($dir in $expectedDirs) {
    if (Test-Path $dir) {
        Write-Host "OK $dir - Encontrado" -ForegroundColor Green
    } else {
        Write-Host "ERROR $dir - No encontrado" -ForegroundColor Red
    }
}

# Verificar si hay un servidor backend corriendo
Write-Host ""
Write-Host "Verificando conectividad con backend..." -ForegroundColor Yellow
try {
    $response = Invoke-RestMethod -Uri "http://localhost:8000/health" -Method Get -TimeoutSec 5
    Write-Host "OK Backend disponible en http://localhost:8000" -ForegroundColor Green
} catch {
    Write-Host "ADVERTENCIA Backend no disponible en http://localhost:8000" -ForegroundColor Yellow
    Write-Host "   Asegurate de que el backend de TheoGen este iniciado" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "===========================================" -ForegroundColor Green
Write-Host "    Verificacion completada" -ForegroundColor Green
Write-Host "===========================================" -ForegroundColor Green

Write-Host ""
Write-Host "Para iniciar el frontend:" -ForegroundColor Cyan
Write-Host "   1. Asegurate de que el backend este corriendo en http://localhost:8000" -ForegroundColor White
Write-Host "   2. Ejecuta 'npm run dev' desde el directorio frontend" -ForegroundColor White
Write-Host "   3. Accede a http://localhost:3000 para usar TheoGen" -ForegroundColor White