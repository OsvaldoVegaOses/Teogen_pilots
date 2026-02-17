#!/usr/bin/env pwsh
# Script para iniciar tanto el backend como el frontend de TheoGen

Write-Host "===========================================" -ForegroundColor Green
Write-Host "    Iniciar TheoGen Completo" -ForegroundColor Green
Write-Host "===========================================" -ForegroundColor Green

# Ruta de los directorios
$frontendPath = "c:\Users\osval\OneDrive - ONG Tren Ciudadano\digital skills\Teogen\frontend"
$backendPath = "c:\Users\osval\OneDrive - ONG Tren Ciudadano\digital skills\Teogen\backend"

# Verificar que los directorios existen
if (!(Test-Path $frontendPath)) {
    Write-Host "Error: No se encuentra el directorio de frontend en $frontendPath" -ForegroundColor Red
    exit 1
}

if (!(Test-Path $backendPath)) {
    Write-Host "Error: No se encuentra el directorio de backend en $backendPath" -ForegroundColor Red
    exit 1
}

Write-Host "`n🚀 Iniciando TheoGen Backend (puerto 8000)..." -ForegroundColor Yellow
# Iniciar el backend en una nueva ventana
Start-Process powershell -ArgumentList "-Command", "Set-Location '$backendPath'; C:\Users\osval\anaconda3\envs\myproject\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000"

Start-Sleep -Seconds 5

Write-Host "`n🚀 Iniciando TheoGen Frontend (puerto 3000)..." -ForegroundColor Yellow
# Iniciar el frontend en otra nueva ventana
Start-Process powershell -ArgumentList "-Command", "Set-Location '$frontendPath'; npm run dev"

Write-Host "`n✅ TheoGen completo iniciado!" -ForegroundColor Green
Write-Host "Backend disponible en: http://localhost:8000" -ForegroundColor Cyan
Write-Host "Frontend disponible en: http://localhost:3000" -ForegroundColor Cyan
Write-Host "" -ForegroundColor Green
Write-Host "ℹ️  Para detener las aplicaciones, cierra las ventanas de PowerShell adicionales" -ForegroundColor Cyan
Write-Host "ℹ️  o ejecuta Ctrl+C en cada ventana" -ForegroundColor Cyan

Write-Host "`n===========================================" -ForegroundColor Green
Write-Host "    TheoGen completo iniciado" -ForegroundColor Green
Write-Host "===========================================" -ForegroundColor Green