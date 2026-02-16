# infra/deploy.ps1
param(
    [string]$resourceGroupName = "theogen-rg",
    [string]$location = "westeurope",
    [string]$projectName = "theogen"
)

# Check if logged in to Azure
$account = az account show --query "name" -o tsv
if ($null -eq $account) {
    Write-Host "Please login to Azure first using 'az login'" -ForegroundColor Red
    exit
}

Write-Host "Using Azure Account: $account" -ForegroundColor Cyan

# Create Resource Group if not exists
Write-Host "Ensuring Resource Group '$resourceGroupName' exists in '$location'..."
az group create --name $resourceGroupName --location $location

# Generate a random password for Postgres if not provided (for first deploy)
$adminPassword = -join ((65..90) + (97..122) + (48..57) | Get-Random -Count 16 | ForEach-Object {[char]$_})
$adminPassword += "!" # Ensure it meets complexity

Write-Host "Deploying infrastructure (this may take several minutes)..."
$deployment = az deployment group create `
    --resource-group $resourceGroupName `
    --template-file main.bicep `
    --parameters projectName=$projectName adminPassword=$adminPassword `
    --output json | ConvertFrom-Json

if ($deployment.properties.provisioningState -eq "Succeeded") {
    Write-Host "Deployment Succeeded!" -ForegroundColor Green
    Write-Host "`n--- Azure Resources Configuration ---" -ForegroundColor Yellow
    Write-Host "OpenAI Endpoint: $($deployment.properties.outputs.openaiEndpoint.value)"
    Write-Host "Postgres Host: $($deployment.properties.outputs.postgresHost.value)"
    Write-Host "Postgres User: theogenadmin"
    Write-Host "Postgres Password: $adminPassword (SAVE THIS!)"
    Write-Host "Storage Account: $($deployment.properties.outputs.storageAccountName.value)"
    Write-Host "-------------------------------------"
} else {
    Write-Host "Deployment failed." -ForegroundColor Red
}
