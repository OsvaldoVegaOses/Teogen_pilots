# Script para agregar SPA redirect URIs al App Registration
$objectId = (az ad app show --id c6d2cf71-dcd2-4400-a8be-9eb8c16b1174 --query "id" -o tsv).Trim()
Write-Host "Object ID: $objectId"

$body = @{
    spa = @{
        redirectUris = @(
            "https://theogenfrontwpdxe2pv.z13.web.core.windows.net/"
            "http://localhost:3000/"
        )
    }
} | ConvertTo-Json -Depth 3

Write-Host "Body: $body"

az rest --method PATCH --url "https://graph.microsoft.com/v1.0/applications/$objectId" --body $body
Write-Host "Done! Exit code: $LASTEXITCODE"
