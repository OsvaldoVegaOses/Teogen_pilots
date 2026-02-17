#!/usr/bin/env pwsh
# Script para iniciar el frontend de TheoGen

Write-Host "===========================================" -ForegroundColor Green
Write-Host "    Iniciar Frontend de TheoGen" -ForegroundColor Green
Write-Host "===========================================" -ForegroundColor Green

# Verificar que estemos en el directorio correcto o navegar al directorio de frontend
$frontendPath = "c:\Users\osval\OneDrive - ONG Tren Ciudadano\digital skills\Teogen\frontend"

if (Test-Path $frontendPath) {
    Write-Host "Navegando al directorio de frontend..." -ForegroundColor Yellow
    Set-Location $frontendPath
} else {
    Write-Host "Error: No se encuentra el directorio de frontend en $frontendPath" -ForegroundColor Red
    exit 1
}

# Verificar prerequisitos
Write-Host "`n🔍 Verificando prerequisitos..." -ForegroundColor Yellow

# Verificar Node.js
try {
    $nodeVersion = node --version
    Write-Host "✅ Node.js encontrado: $nodeVersion" -ForegroundColor Green
} catch {
    Write-Host "❌ Error: Node.js no está instalado o no está en el PATH." -ForegroundColor Red
    exit 1
}

# Verificar npm
try {
    $npmVersion = npm --version
    Write-Host "✅ npm encontrado: $npmVersion" -ForegroundColor Green
} catch {
    Write-Host "❌ Error: npm no está instalado o no está en el PATH." -ForegroundColor Red
    exit 1
}

# Verificar si las dependencias están instaladas
Write-Host "`n🔍 Verificando dependencias..." -ForegroundColor Yellow

if (Test-Path "node_modules") {
    Write-Host "✅ Dependencias ya instaladas" -ForegroundColor Green
} else {
    Write-Host "📦 Instalando dependencias..." -ForegroundColor Yellow
    try {
        npm install
        Write-Host "✅ Dependencias instaladas correctamente" -ForegroundColor Green
    } catch {
        Write-Host "❌ Error al instalar dependencias: $_" -ForegroundColor Red
        exit 1
    }
}

# Verificar si el archivo .env.local existe
if (Test-Path ".env.local") {
    Write-Host "✅ Archivo de configuración .env.local encontrado" -ForegroundColor Green
} else {
    Write-Host "⚠️  Advertencia: No se encontró el archivo .env.local" -ForegroundColor Yellow
    Write-Host "   Se creará un archivo de ejemplo si es necesario" -ForegroundColor Yellow
}

# Iniciar el servidor de desarrollo
Write-Host "`n🚀 Iniciando servidor de desarrollo de TheoGen..." -ForegroundColor Yellow
Write-Host "La aplicación estará disponible en http://localhost:3000" -ForegroundColor Cyan
Write-Host "Asegúrate de que el backend esté corriendo en http://localhost:8000" -ForegroundColor Cyan

# Abrir una nueva ventana de PowerShell para ejecutar el frontend
Start-Process powershell -ArgumentList "-Command", "Set-Location '$(Get-Location)'; npm run dev"

Write-Host "`n✅ Servidor de frontend iniciado en segundo plano" -ForegroundColor Green
Write-Host "La aplicación estará disponible en http://localhost:3000" -ForegroundColor Green
Write-Host "" -ForegroundColor Green
Write-Host "ℹ️  Para detener el servidor, cierra la ventana de PowerShell adicional" -ForegroundColor Cyan
Write-Host "ℹ️  o ejecuta Ctrl+C en esa ventana" -ForegroundColor Cyan

Write-Host "`n===========================================" -ForegroundColor Green
Write-Host "    Frontend de TheoGen iniciado" -ForegroundColor Green
Write-Host "===========================================" -ForegroundColor Green