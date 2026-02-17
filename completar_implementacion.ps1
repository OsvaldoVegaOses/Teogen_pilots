#!/usr/bin/env pwsh
# Script para completar la implementación de TheoGen

Write-Host "===========================================" -ForegroundColor Green
Write-Host "    Completar Implementación de TheoGen" -ForegroundColor Green
Write-Host "===========================================" -ForegroundColor Green

# Función para verificar si un comando existe
function Test-Command {
    param($cmd)
    $exists = $null -ne (Get-Command $cmd -ErrorAction SilentlyContinue)
    return $exists
}

# Verificar prerequisitos
Write-Host "`n🔍 Verificando prerequisitos..." -ForegroundColor Yellow

$prereqs = @()
$prereqs += @{name="Python"; exists=(Test-Command python); cmd="python --version"}
$prereqs += @{name="Pip"; exists=(Test-Command pip); cmd="pip --version"}
$prereqs += @{name="Node.js"; exists=(Test-Command node); cmd="node --version"}
$prereqs += @{name="npm"; exists=(Test-Command npm); cmd="npm --version"}
$prereqs += @{name="Azure CLI"; exists=(Test-Command az); cmd="az version"}

foreach ($prereq in $prereqs) {
    if ($prereq.exists) {
        $version = Invoke-Expression $prereq.cmd 2>$null
        Write-Host "✅ $($prereq.name): $version" -ForegroundColor Green
    } else {
        Write-Host "❌ $($prereq.name): No encontrado" -ForegroundColor Red
    }
}

# Verificar si hay sesión activa en Azure
try {
    $account = az account show 2>$null | ConvertFrom-Json
    if ($LASTEXITCODE -eq 0 -and $null -ne $account) {
        Write-Host "✅ Sesión activa en Azure para: $($account.user.name)" -ForegroundColor Green
    } else {
        Write-Host "⚠️  No hay sesión activa en Azure, inicia sesión con: az login" -ForegroundColor Yellow
    }
} catch {
    Write-Host "⚠️  No hay sesión activa en Azure, inicia sesión con: az login" -ForegroundColor Yellow
}

# Verificar existencia de archivos críticos
Write-Host "`n📁 Verificando archivos críticos..." -ForegroundColor Yellow

$importantFiles = @(
    @{path=".env"; name="Archivo de configuración"},
    @{path="backend\requirements.txt"; name="Requerimientos del backend"},
    @{path="frontend\package.json"; name="Configuración del frontend"},
    @{path="backend\app\main.py"; name="Archivo principal del backend"}
)

foreach ($file in $importantFiles) {
    if (Test-Path $file.path) {
        Write-Host "✅ $($file.name): Encontrado" -ForegroundColor Green
    } else {
        Write-Host "❌ $($file.name): No encontrado en $($file.path)" -ForegroundColor Red
    }
}

# Verificar la configuración del archivo .env
Write-Host "`n⚙️  Analizando configuración (.env)..." -ForegroundColor Yellow

if (Test-Path ".env") {
    $envContent = Get-Content .env
    $placeholders = @(
        "AZURE_STORAGE_KEY=<tu-clave-storage>",
        "AZURE_AD_CLIENT_ID=<tu-client-id>",
        "AZURE_SPEECH_KEY=<tu-clave-speech>",
        "AZURE_REDIS_KEY=<tu-clave-redis>"
    )
    
    $missingValues = 0
    foreach ($placeholder in $placeholders) {
        if ($envContent -match [regex]::Escape($placeholder)) {
            Write-Host "⚠️  Valor pendiente: $placeholder" -ForegroundColor Yellow
            $missingValues++
        }
    }
    
    if ($missingValues -eq 0) {
        Write-Host "✅ Configuración completa detectada" -ForegroundColor Green
    } else {
        Write-Host "⚠️  Hay $missingValues valores que necesitan ser actualizados" -ForegroundColor Yellow
        Write-Host "💡 Ejecuta: python actualizar_env.py para actualizar los valores" -ForegroundColor Cyan
    }
} else {
    Write-Host "❌ Archivo .env no encontrado" -ForegroundColor Red
}

# Opciones de acción
Write-Host "`n🎯 Opciones para continuar:" -ForegroundColor Green
Write-Host "1. Obtener claves reales de Azure y actualizar .env" -ForegroundColor White
Write-Host "2. Verificar recursos de Azure" -ForegroundColor White
Write-Host "3. Instalar dependencias e iniciar TheoGen" -ForegroundColor White
Write-Host "4. Ejecutar verificación completa" -ForegroundColor White
Write-Host "5. Salir" -ForegroundColor White

$opcion = Read-Host "`nSelecciona una opción (1-5)"

switch ($opcion) {
    "1" {
        Write-Host "`n🔑 Ejecutando script para obtener claves de Azure..." -ForegroundColor Cyan
        .\obtener_claves_azure.ps1
    }
    "2" {
        Write-Host "`n🔍 Ejecutando verificación de recursos..." -ForegroundColor Cyan
        python verificar_recursos.py
    }
    "3" {
        Write-Host "`n🚀 Ejecutando script para iniciar TheoGen..." -ForegroundColor Cyan
        .\iniciar_theogen.ps1
    }
    "4" {
        Write-Host "`n🔍 Ejecutando verificación completa..." -ForegroundColor Cyan
        Write-Host "Primero actualizando configuración..." -ForegroundColor Yellow
        python actualizar_env.py
        
        Write-Host "`nVerificando recursos..." -ForegroundColor Yellow
        python verificar_recursos.py
        
        Write-Host "`nIniciando TheoGen..." -ForegroundColor Yellow
        .\iniciar_theogen.ps1
    }
    "5" {
        Write-Host "`n👋 Saliendo del script de implementación..." -ForegroundColor Green
        exit 0
    }
    default {
        Write-Host "`n❌ Opción inválida. Por favor selecciona una opción del 1 al 5." -ForegroundColor Red
    }
}

Write-Host "`n===========================================" -ForegroundColor Green
Write-Host "    Fin del script de implementación" -ForegroundColor Green
Write-Host "===========================================" -ForegroundColor Green