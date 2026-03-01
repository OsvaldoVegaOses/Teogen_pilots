$dest = ".\frontend\public\fonts"
New-Item -ItemType Directory -Force -Path $dest | Out-Null
$cssUrl = "https://fonts.googleapis.com/css2?family=Inter:wght@100;400;700&family=JetBrains+Mono:wght@400;700&display=swap"
$ua = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
$css = (Invoke-WebRequest -Uri $cssUrl -Headers @{ 'User-Agent' = $ua } -UseBasicParsing).Content
Write-Host "--- CSS preview ---"
Write-Host $css
$matches = [regex]::Matches($css, "https://[^)']+\.(woff2|ttf)")
Write-Host "Found matches:" $matches.Count
foreach ($m in $matches) {
  $url = $m.Value
  $file = Split-Path $url -Leaf
  $out = Join-Path $dest $file
  Write-Host "Downloading $url -> $out"
  Invoke-WebRequest $url -OutFile $out -UseBasicParsing
}
