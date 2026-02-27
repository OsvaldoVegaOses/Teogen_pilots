#!/usr/bin/env pwsh
# .\git_push.ps1  [-Message "tu mensaje"]  [-DryRun]
# Sube cambios de código fuente a GitHub respetando .gitignore y
# bloqueando patrones de archivos peligrosos antes de commitear.
## Con mensaje automático
.\git_push.ps1

# Con mensaje personalizado
.\git_push.ps1 -Message "feat: nueva funcionalidad X"

# Simular sin commitear
.\git_push.ps1 -DryRun

param(
    [string]$Message = "",
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ─── Paleta de colores ───────────────────────────────────────────────────────
function Info  ($t) { Write-Host $t -ForegroundColor Cyan }
function Ok    ($t) { Write-Host $t -ForegroundColor Green }
function Warn  ($t) { Write-Host $t -ForegroundColor Yellow }
function Err   ($t) { Write-Host $t -ForegroundColor Red }
function Gray  ($t) { Write-Host $t -ForegroundColor Gray }

Write-Host ""
Write-Host "================================================" -ForegroundColor Green
Write-Host "   TheoGen — Git Push Seguro                   " -ForegroundColor Green
Write-Host "================================================" -ForegroundColor Green
if ($DryRun) { Warn "  ** MODO DRY-RUN: no se hará commit ni push **" }
Write-Host ""

# ─── 1. Verificar que estamos en el repo ────────────────────────────────────
if (-not (Test-Path ".git")) {
    Err "❌ No se encontró el repositorio git en el directorio actual."
    Err "   Ejecuta el script desde la raíz del proyecto."
    exit 1
}

# ─── 2. Verificar sesión git (remote accesible) ──────────────────────────────
$remote = git remote get-url origin 2>$null
if ([string]::IsNullOrWhiteSpace($remote)) {
    Err "❌ No hay remote 'origin' configurado."
    exit 1
}
Info "Remote: $remote"

# ─── 3. Patrones de archivos que NUNCA deben subirse ─────────────────────────
# Complementan .gitignore como capa de seguridad adicional.
$blockedPatterns = @(
    # Secretos y claves
    '\.env$', '\.env\..+', '\.pem$', '\.key$', '\.pfx$', '\.p12$',
    'id_rsa', 'id_ed25519',
    # Bases de datos locales
    '\.db$', '\.sqlite$', '\.sqlite3$',
    # Logs y salidas temporales
    '\.log$', '_err\.txt$', '_log\.txt$', '_output\.txt$', 'check_out\.txt$',
    # Archivos de debug / scripts de prueba ad-hoc
    '^backend[/\\]debug_', '^backend[/\\]tmp_', '^backend[/\\]force_',
    '^backend[/\\]process_test_data', '^backend[/\\]trigger_coding',
    # Builds y artefactos
    '^frontend[/\\]out[/\\]', '^frontend[/\\]\.next[/\\]',
    # Configs de secretos de Azure
    'backend_app_config\.json$', 'resource_access\.json$',
    'spa_config\.json$', 'theogen_app_debug\.json$',
    # Archivos temporales de deploy
    'temp_fqdn\.txt$', 'smoke_out\.txt$'
)

# ─── 4. git add -A (respeta .gitignore) ─────────────────────────────────────
Info "Añadiendo cambios (respeta .gitignore)..."
git add -A
if ($LASTEXITCODE -ne 0) {
    Err "❌ Error en git add."
    exit 1
}

# ─── 5. Obtener lista de archivos en staging ─────────────────────────────────
$staged = git diff --cached --name-only
if ([string]::IsNullOrWhiteSpace($staged)) {
    Ok "✅ No hay cambios pendientes para commitear."
    exit 0
}

$stagedFiles = $staged -split "`n" | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }

# ─── 6. Escanear staging por archivos bloqueados ─────────────────────────────
$blocked = @()
foreach ($file in $stagedFiles) {
    foreach ($pattern in $blockedPatterns) {
        if ($file -match $pattern) {
            $blocked += $file
            break
        }
    }
}

if ($blocked.Count -gt 0) {
    Err ""
    Err "❌ BLOQUEADO: los siguientes archivos NO deben subirse a GitHub:"
    foreach ($f in $blocked) { Err "   - $f" }
    Err ""
    Err "Opciones:"
    Err "  1) Agrégalos a .gitignore y ejecuta: git rm --cached <archivo>"
    Err "  2) O remuévelos del staging manualmente: git restore --staged <archivo>"
    git restore --staged .   # Deshace el add para no dejar staging sucio
    exit 1
}

# ─── 7. Mostrar resumen de cambios ───────────────────────────────────────────
$statusLines = @(git diff --cached --name-status)
$added    = @($statusLines | Where-Object { $_ -match '^A\s' }).Count
$modified = @($statusLines | Where-Object { $_ -match '^M\s' }).Count
$deleted  = @($statusLines | Where-Object { $_ -match '^D\s' }).Count

Info ""
Info "Archivos en staging ($($stagedFiles.Count) total):"
foreach ($line in $statusLines) {
    if ($line -match '^([AMD])\s+(.+)$') {
        switch ($Matches[1]) {
            "A" { Ok   "  + $($Matches[2])" }
            "M" { Warn "  ~ $($Matches[2])" }
            "D" { Err  "  - $($Matches[2])" }
        }
    }
}
Write-Host ""

# ─── 8. Construir mensaje de commit ──────────────────────────────────────────
if ([string]::IsNullOrWhiteSpace($Message)) {
    # Auto-generar basado en qué cambió
    $backendChanged  = @($stagedFiles | Where-Object { $_ -match '^backend/' }).Count
    $frontendChanged = @($stagedFiles | Where-Object { $_ -match '^frontend/' }).Count
    $infraChanged    = @($stagedFiles | Where-Object { $_ -match '^infra/' }).Count
    $docsChanged     = @($stagedFiles | Where-Object { $_ -match '^docs/' }).Count
    $scriptsChanged  = @($stagedFiles | Where-Object { $_ -match '\.ps1$|\.py$' -and $_ -notmatch '^backend/|^frontend/' }).Count

    $parts = @()
    if ($backendChanged  -gt 0) { $parts += "backend($backendChanged)" }
    if ($frontendChanged -gt 0) { $parts += "frontend($frontendChanged)" }
    if ($infraChanged    -gt 0) { $parts += "infra($infraChanged)" }
    if ($docsChanged     -gt 0) { $parts += "docs($docsChanged)" }
    if ($scriptsChanged  -gt 0) { $parts += "scripts($scriptsChanged)" }

    $scope = if ($parts.Count -gt 0) { $parts -join ", " } else { "misc" }
    $date  = Get-Date -Format "yyyy-MM-dd HH:mm"
    $Message = "chore: actualización $scope [$date]"
}

Info "Mensaje de commit: $Message"
Write-Host ""

# ─── 9. Commit ───────────────────────────────────────────────────────────────
if ($DryRun) {
    Warn "DRY-RUN: se habría commiteado con: $Message"
} else {
    git commit -m $Message
    if ($LASTEXITCODE -ne 0) {
        Err "❌ Error al crear el commit."
        exit 1
    }
    Ok "✅ Commit creado."
}

# ─── 10. Push ────────────────────────────────────────────────────────────────
if ($DryRun) {
    Warn "DRY-RUN: se habría ejecutado git push."
} else {
    Info "Subiendo cambios a GitHub..."
    git push
    if ($LASTEXITCODE -ne 0) {
        Err "❌ Error en git push."
        Err "   Si el remote tiene cambios nuevos, ejecuta primero: git pull --rebase"
        exit 1
    }
    $branch = git rev-parse --abbrev-ref HEAD
    $sha    = git rev-parse --short HEAD
    Write-Host ""
    Write-Host "================================================" -ForegroundColor Green
    Ok "✅ Cambios subidos a GitHub exitosamente."
    Info "   Branch : $branch"
    Info "   Commit : $sha"
    Info "   Remote : $remote"
    Write-Host "================================================" -ForegroundColor Green
}
