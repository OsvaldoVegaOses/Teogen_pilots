 $root = Split-Path $PSScriptRoot -Parent
 $src = Join-Path $root 'frontend\frontend\public\fonts'
 $dst = Join-Path $root 'frontend\public\fonts'
New-Item -ItemType Directory -Force -Path $dst | Out-Null
Get-ChildItem -Path $src -File | ForEach-Object { Move-Item -Path $_.FullName -Destination (Join-Path $dst $_.Name) -Force }
Write-Host "Moved files to $dst"
Get-ChildItem -Path $dst -File | Select-Object Name,Length | Format-Table -AutoSize
