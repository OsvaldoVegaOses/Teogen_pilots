#!/usr/bin/env pwsh
# Script para completar la implementación de TheoGen

Write-Host "===========================================" -ForegroundColor Green
Write-Host "    Completar Implementacion de TheoGen" -ForegroundColor Green
Write-Host "===========================================" -ForegroundColor Green

# Funcion para verificar si un comando existe
function Test-Command {
    param($cmd)
    $exists = $null -ne (Get-Command $cmd -ErrorAction SilentlyContinue)
    return $exists
}

# Verificar prerequisitos
Write-Host ""
Write-Host "Verificando prerequisitos..." -ForegroundColor Yellow

$prereqs = @()
$prereqs += @{name="Python"; exists=(Test-Command python); cmd="python --version"}
$prereqs += @{name="Pip"; exists=(Test-Command pip); cmd="pip --version"}
$prereqs += @{name="Node.js"; exists=(Test-Command node); cmd="node --version"}
$prereqs += @{name="npm"; exists=(Test-Command npm); cmd="npm --version"}
$prereqs += @{name="Azure CLI"; exists=(Test-Command az); cmd="az version"}

foreach ($prereq in $prereqs) {
    if ($prereq.exists) {
        $version = Invoke-Expression $prereq.cmd 2>$null
        Write-Host "[OK] $($prereq.name): $version" -ForegroundColor Green
    } else {
        Write-Host "[ERROR] $($prereq.name): No encontrado" -ForegroundColor Red
    }
}

# Verificar si hay sesion activa en Azure
try {
    $account = az account show 2>$null | ConvertFrom-Json
    if ($LASTEXITCODE -eq 0 -and $null -ne $account) {
        Write-Host "[OK] Sesion activa en Azure para: $($account.user.name)" -ForegroundColor Green
    } else {
        Write-Host "[WARN] No hay sesion activa en Azure, inicia sesion con: az login" -ForegroundColor Yellow
    }
} catch {
    Write-Host "[WARN] No hay sesion activa en Azure, inicia sesion con: az login" -ForegroundColor Yellow
}

# Verificar existencia de archivos criticos
Write-Host ""
Write-Host "Verificando archivos criticos..." -ForegroundColor Yellow

$importantFiles = @(
    @{path=".env"; name="Archivo de configuracion"},
    @{path="backend\requirements.txt"; name="Requerimientos del backend"},
    @{path="frontend\package.json"; name="Configuracion del frontend"},
    @{path="backend\app\main.py"; name="Archivo principal del backend"}
)

foreach ($file in $importantFiles) {
    if (Test-Path $file.path) {
        Write-Host "[OK] $($file.name): Encontrado" -ForegroundColor Green
    } else {
        Write-Host "[ERROR] $($file.name): No encontrado en $($file.path)" -ForegroundColor Red
    }
}

# Verificar la configuracion del archivo .env
Write-Host ""
Write-Host "Analizando configuracion (.env)..." -ForegroundColor Yellow

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
            Write-Host "[PENDIENTE] Valor pendiente: $placeholder" -ForegroundColor Yellow
            $missingValues++
        }
    }
    
    if ($missingValues -eq 0) {
        Write-Host "[OK] Configuracion completa detectada" -ForegroundColor Green
    } else {
        Write-Host "[WARN] Hay $missingValues valores que necesitan ser actualizados" -ForegroundColor Yellow
        Write-Host "Ejecuta: python actualizar_env.py para actualizar los valores" -ForegroundColor Cyan
    }
} else {
    Write-Host "[ERROR] Archivo .env no encontrado" -ForegroundColor Red
}

# Opciones de accion
Write-Host ""
Write-Host "Opciones para continuar:" -ForegroundColor Green
Write-Host "1. Obtener claves reales de Azure y actualizar .env" -ForegroundColor White
Write-Host "2. Verificar recursos de Azure" -ForegroundColor White
Write-Host "3. Instalar dependencias e iniciar TheoGen" -ForegroundColor White
Write-Host "4. Ejecutar verificacion completa" -ForegroundColor White
Write-Host "5. Salir" -ForegroundColor White

$opcion = Read-Host ""
Write-Host "Selecciona una opcion (1-5): $opcion"

switch ($opcion) {
    "1" {
        Write-Host ""
        Write-Host "Ejecutando script para obtener claves de Azure..." -ForegroundColor Cyan
        .\obtener_claves_azure.ps1
    }
    "2" {
        Write-Host ""
        Write-Host "Ejecutando verificacion de recursos..." -ForegroundColor Cyan
        python verificar_recursos.py
    }
    "3" {
        Write-Host ""
        Write-Host "Ejecutando script para iniciar TheoGen..." -ForegroundColor Cyan
        .\iniciar_theogen.ps1
    }
    "4" {
        Write-Host ""
        Write-Host "Ejecutando verificacion completa..." -ForegroundColor Cyan
        Write-Host "Primero actualizando configuracion..." -ForegroundColor Yellow
        python actualizar_env.py
        
        Write-Host ""
        Write-Host "Verificando recursos..." -ForegroundColor Yellow
        python verificar_recursos.py
        
        Write-Host ""
        Write-Host "Iniciando TheoGen..." -ForegroundColor Yellow
        .\iniciar_theogen.ps1
    }
    "5" {
        Write-Host ""
        Write-Host "Saliendo del script de implementacion..." -ForegroundColor Green
        exit 0
    }
    default {
        Write-Host ""
        Write-Host "[ERROR] Opcion invalida. Por favor selecciona una opcion del 1 al 5." -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "===========================================" -ForegroundColor Green
Write-Host "    Fin del script de implementacion" -ForegroundColor Green
Write-Host "===========================================" -ForegroundColor Green