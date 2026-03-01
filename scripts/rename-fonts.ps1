$root = Split-Path $PSScriptRoot -Parent
$dir = Join-Path $root 'frontend\public\fonts'
$map = @{
  'UcC73FwrK3iLTeHuS_nVMrMxCp50SjIa1ZL7.woff2' = 'Inter-Regular.woff2'
  'UcC73FwrK3iLTeHuS_nVMrMxCp50SjIa2JL7SUc.woff2' = 'Inter-Bold.woff2'
  'tDbv2o-flEEny0FZhsfKu5WU4zr3E_BX0PnT8RD8yKwBNntkaToggR7BYRbKPxDcwg.woff2' = 'JetBrainsMono-Regular.woff2'
  'tDbv2o-flEEny0FZhsfKu5WU4zr3E_BX0PnT8RD8yKwBNntkaToggR7BYRbKPx3cwhsk.woff2' = 'JetBrainsMono-Bold.woff2'
}
foreach ($k in $map.Keys) {
  $src = Join-Path $dir $k
  if (Test-Path $src) {
    $dst = Join-Path $dir $map[$k]
    Move-Item -Path $src -Destination $dst -Force
    Write-Host "Renamed $k -> $($map[$k])"
  } else {
    Write-Host "Missing $k, skipping"
  }
}
Get-ChildItem -Path $dir -File | Select-Object Name,Length | Format-Table -AutoSize
