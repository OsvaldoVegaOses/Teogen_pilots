# Script de despliegue para TheoGen
# Este script configura la aplicación TheoGen con los recursos existentes

Write-Host "=========================================" -ForegroundColor Green
Write-Host "Iniciando despliegue de TheoGen" -ForegroundColor Green
Write-Host "=========================================" -ForegroundColor Green

# Verificar prerequisitos
Write-Host "`nVerificando prerequisitos..." -ForegroundColor Yellow

# Verificar Python
try {
    $pythonVersion = python --version
    Write-Host "Python encontrado: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "Error: Python no encontrado. Por favor instala Python." -ForegroundColor Red
    exit 1
}

# Verificar pip
try {
    $pipVersion = pip --version
    Write-Host "Pip encontrado: $pipVersion" -ForegroundColor Green
} catch {
    Write-Host "Error: Pip no encontrado." -ForegroundColor Red
    exit 1
}

# Navegar al directorio backend
Set-Location -Path "backend"

# Instalar dependencias
Write-Host "`nInstalando dependencias de Python..." -ForegroundColor Yellow
pip install -r requirements.txt

# Verificar si el archivo .env existe
if (-not (Test-Path "../.env")) {
    Write-Host "Advertencia: El archivo .env no existe. Se creará uno de ejemplo." -ForegroundColor Yellow
    Copy-Item ".env.example" "../.env" -Force
    Write-Host "Por favor, actualiza el archivo .env con tus credenciales reales." -ForegroundColor Red
}

# Inicializar la base de datos
Write-Host "`nInicializando base de datos..." -ForegroundColor Yellow
python init_db.py

# Iniciar la aplicación
Write-Host "`nLa configuración básica está completa." -ForegroundColor Green
Write-Host "Para iniciar la aplicación, ejecuta: python start_app.py" -ForegroundColor Green
Write-Host "O desde el directorio backend: uvicorn app.main:app --reload" -ForegroundColor Green

Write-Host "`n=========================================" -ForegroundColor Green
Write-Host "Despliegue de TheoGen completado" -ForegroundColor Green
Write-Host "=========================================" -ForegroundColor Green