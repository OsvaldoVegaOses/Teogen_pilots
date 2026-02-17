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
    
    # Inform about Entra ID manual setup
    Write-Host "`n--- Microsoft Entra ID Setup ---" -ForegroundColor Yellow
    Write-Host "Manual setup required for Entra ID:"
    Write-Host "1. Register a new application in Azure Portal -> Microsoft Entra ID"
    Write-Host "2. Use 'theogen-app' as the application name"
    Write-Host "3. Add these redirect URIs:"
    Write-Host "   - http://localhost:8000/auth/callback"
    Write-Host "   - https://theogen-app.azurewebsites.net/auth/callback"
    Write-Host "4. Copy the Client ID and Tenant ID for the .env file"
    Write-Host "-------------------------------------"
    
    # Create/update .env file with deployment outputs
    $envContent = @"
# TheoGen Environment Variables

# Azure OpenAI
AZURE_OPENAI_API_KEY=
AZURE_OPENAI_ENDPOINT=$($deployment.properties.outputs.openaiEndpoint.value)
AZURE_OPENAI_API_VERSION=2024-12-01-preview

# Azure PostgreSQL
AZURE_PG_USER=theogenadmin
AZURE_PG_PASSWORD=$adminPassword
AZURE_PG_HOST=$($deployment.properties.outputs.postgresHost.value)
AZURE_PG_DATABASE=theogen

# Azure Storage
AZURE_STORAGE_ACCOUNT=$($deployment.properties.outputs.storageAccountName.value)
AZURE_STORAGE_KEY=

# Azure AD (Entra ID) - Complete manually after registering the app
AZURE_AD_TENANT_ID=
AZURE_AD_CLIENT_ID=
"@
    
    Set-Content -Path "../.env" -Value $envContent
    Write-Host "`n.env file created/updated with deployment outputs" -ForegroundColor Green
    
    Write-Host "`nIMPORTANT: Save the password and .env file securely!" -ForegroundColor Red
    Write-Host "After setting up Entra ID manually, update the .env file with Client ID and Tenant ID." -ForegroundColor Yellow
} else {
    Write-Host "Deployment failed." -ForegroundColor Red
}