#!/usr/bin/env pwsh
# Script para iniciar TheoGen con todos los recursos configurados

Write-Host "===========================================" -ForegroundColor Green
Write-Host "    Inicialización de TheoGen" -ForegroundColor Green
Write-Host "===========================================" -ForegroundColor Green

# Verificar que el archivo .env exista
if (-not (Test-Path ".env")) {
    Write-Host "Error: El archivo .env no existe en el directorio actual." -ForegroundColor Red
    exit 1
}

Write-Host "`n1. Configurando variables de entorno..." -ForegroundColor Yellow
$env:PYTHONPATH = "$(Get-Location)"

# Verificar que Python esté instalado
try {
    $pythonVersion = python --version
    Write-Host "Python encontrado: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "Error: Python no está instalado o no está en el PATH." -ForegroundColor Red
    exit 1
}

# Verificar que pip esté instalado
try {
    $pipVersion = pip --version
    Write-Host "Pip encontrado: $pipVersion" -ForegroundColor Green
} catch {
    Write-Host "Error: Pip no está instalado o no está en el PATH." -ForegroundColor Red
    exit 1
}

Write-Host "`n2. Instalando dependencias del backend..." -ForegroundColor Yellow
Set-Location backend
try {
    pip install -r requirements.txt
    Write-Host "Dependencias instaladas correctamente." -ForegroundColor Green
} catch {
    Write-Host "Error al instalar dependencias: $_" -ForegroundColor Red
    Set-Location ..
    exit 1
}

Write-Host "`n3. Inicializando base de datos..." -ForegroundColor Yellow
try {
    python init_db.py
    Write-Host "Base de datos inicializada correctamente." -ForegroundColor Green
} catch {
    Write-Host "Error al inicializar la base de datos: $_" -ForegroundColor Red
    Set-Location ..
    exit 1
}

Write-Host "`n4. Verificando configuración de entorno..." -ForegroundColor Yellow

# Cargar variables de entorno
$envVars = Get-Content .env | Where-Object {$_.Trim() -ne "" -and !$_.StartsWith("#")}
foreach ($var in $envVars) {
    if ($var -match "^(.*?)=(.*)$") {
        $name = $matches[1]
        $value = $matches[2].Trim('"')
        
        # Verificar si es una clave sensible
        if ($name -like "*KEY*" -or $name -like "*PASSWORD*" -or $name -like "*SECRET*") {
            # Solo verificar si la clave está presente, no mostrar su valor
            if ($value -ne "<tu-clave-storage>" -and $value -ne "<tu-clave-speech>" -and $value -ne "<tu-clave-redis>" -and $value -ne "<tu-client-id>") {
                Write-Host "✓ $name configurado" -ForegroundColor Green
            } else {
                Write-Host "! $name necesita ser configurado" -ForegroundColor Yellow
            }
        } else {
            Write-Host "✓ $name = $value" -ForegroundColor Cyan
        }
    }
}

Write-Host "`n5. Iniciando backend TheoGen..." -ForegroundColor Yellow
Write-Host "Abriendo una nueva ventana para ejecutar el backend..." -ForegroundColor Green

# Abrir una nueva ventana de PowerShell para ejecutar el backend
Start-Process powershell -ArgumentList "-Command", "Set-Location '$(Get-Location)'; uvicorn app.main:app --reload --port 8000"

Write-Host "`n6. Instrucciones para el frontend:" -ForegroundColor Yellow
Write-Host "Por favor, en una nueva terminal, ejecute los siguientes comandos:" -ForegroundColor White
Write-Host "  cd frontend" -ForegroundColor White
Write-Host "  npm install" -ForegroundColor White
Write-Host "  npm run dev" -ForegroundColor White
Write-Host "" -ForegroundColor White
Write-Host "La aplicación frontend estará disponible en http://localhost:3000" -ForegroundColor Green
Write-Host "La API backend estará disponible en http://localhost:8000" -ForegroundColor Green

Write-Host "`n===========================================" -ForegroundColor Green
Write-Host "    TheoGen iniciado correctamente!" -ForegroundColor Green
Write-Host "===========================================" -ForegroundColor Green