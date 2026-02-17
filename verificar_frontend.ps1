#!/usr/bin/env pwsh
# Script para verificar la configuración del frontend de TheoGen

Write-Host "===========================================" -ForegroundColor Green
Write-Host "    Verificar Configuración Frontend" -ForegroundColor Green
Write-Host "===========================================" -ForegroundColor Green

# Ruta del frontend
$frontendPath = "c:\Users\osval\OneDrive - ONG Tren Ciudadano\digital skills\Teogen\frontend"

# Verificar que el directorio existe
if (!(Test-Path $frontendPath)) {
    Write-Host "❌ Error: No se encuentra el directorio de frontend en $frontendPath" -ForegroundColor Red
    exit 1
}

Write-Host "✅ Directorio de frontend encontrado" -ForegroundColor Green

# Navegar al directorio de frontend
Set-Location $frontendPath

# Verificar archivos importantes
Write-Host "`n🔍 Verificando archivos importantes..." -ForegroundColor Yellow

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
        Write-Host "✅ $file - Encontrado" -ForegroundColor Green
    } else {
        Write-Host "❌ $file - No encontrado" -ForegroundColor Red
    }
}

# Verificar dependencias
Write-Host "`n🔍 Verificando dependencias..." -ForegroundColor Yellow

if (Test-Path "node_modules") {
    Write-Host "✅ node_modules - Encontrado (dependencias instaladas)" -ForegroundColor Green
} else {
    Write-Host "⚠️  node_modules - No encontrado (ejecuta npm install)" -ForegroundColor Yellow
}

# Verificar package.json
Write-Host "`n🔍 Analizando package.json..." -ForegroundColor Yellow
if (Test-Path "package.json") {
    try {
        $packageJson = Get-Content "package.json" -Raw | ConvertFrom-Json
        Write-Host "✅ Versión de Next.js: $($packageJson.dependencies.next)" -ForegroundColor Green
        Write-Host "✅ Versión de React: $($packageJson.dependencies.react)" -ForegroundColor Green
        Write-Host "✅ Versión de React DOM: $($packageJson.dependencies.'react-dom')" -ForegroundColor Green
    } catch {
        Write-Host "❌ Error al leer package.json" -ForegroundColor Red
    }
}

# Verificar archivo .env.local
Write-Host "`n🔍 Verificando archivo de configuración .env.local..." -ForegroundColor Yellow
if (Test-Path ".env.local") {
    Write-Host "✅ .env.local - Encontrado" -ForegroundColor Green
    $envContent = Get-Content ".env.local"
    foreach ($line in $envContent) {
        if ($line.Trim() -and !$line.StartsWith("#")) {
            Write-Host "   ├── $line" -ForegroundColor Cyan
        }
    }
} else {
    Write-Host "❌ .env.local - No encontrado" -ForegroundColor Red
    Write-Host "   ├── Creando archivo de ejemplo..." -ForegroundColor Yellow
    @"
# Variables de entorno para el frontend de TheoGen

# URL del backend de TheoGen
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api

# Configuración de Azure AD (Entra ID) para autenticación
NEXT_PUBLIC_AZURE_AD_TENANT_ID=3e151d68-e5ed-4878-932d-251fe1b0eaf1
NEXT_PUBLIC_AZURE_AD_CLIENT_ID=c6d2cf71-dcd2-4400-a8be-9eb8c16b1174

# Otras configuraciones si son necesarias
NEXT_PUBLIC_APP_NAME=TheoGen
NEXT_PUBLIC_VERSION=1.0.0
"@ | Out-File -FilePath ".env.local" -Encoding UTF8
    Write-Host "✅ .env.local - Creado con valores predeterminados" -ForegroundColor Green
}

# Verificar estructura de directorios
Write-Host "`n🔍 Verificando estructura de directorios..." -ForegroundColor Yellow

$expectedDirs = @(
    "src/app",
    "src/components",
    "public"
)

foreach ($dir in $expectedDirs) {
    if (Test-Path $dir) {
        Write-Host "✅ $dir - Encontrado" -ForegroundColor Green
    } else {
        Write-Host "❌ $dir - No encontrado" -ForegroundColor Red
    }
}

# Verificar si hay un servidor backend corriendo
Write-Host "`n🔍 Verificando conectividad con backend..." -ForegroundColor Yellow
try {
    $response = Invoke-RestMethod -Uri "http://localhost:8000/health" -Method Get -TimeoutSec 5
    Write-Host "✅ Backend disponible en http://localhost:8000" -ForegroundColor Green
} catch {
    Write-Host "⚠️  Backend no disponible en http://localhost:8000" -ForegroundColor Yellow
    Write-Host "   ├── Asegúrate de que el backend de TheoGen esté iniciado" -ForegroundColor Yellow
}

Write-Host "`n===========================================" -ForegroundColor Green
Write-Host "    Verificación completada" -ForegroundColor Green
Write-Host "===========================================" -ForegroundColor Green

Write-Host "`n💡 Para iniciar el frontend:" -ForegroundColor Cyan
Write-Host "   1. Asegúrate de que el backend esté corriendo en http://localhost:8000" -ForegroundColor White
Write-Host "   2. Ejecuta 'npm run dev' desde el directorio frontend" -ForegroundColor White
Write-Host "   3. Accede a http://localhost:3000 para usar TheoGen" -ForegroundColor White