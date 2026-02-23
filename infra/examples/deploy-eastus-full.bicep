@description('Deploy completo: Key Vault, Log Analytics, Frontend Storage, Backend Container App en East US')
param location string = 'eastus'

// Key Vault
module kv '../modules/keyvault.bicep' = {
  name: 'kvEast'
  params: {
    vaultName: 'theogen-kv-prod-eastus'
    location: location
    skuName: 'standard'
    enableRbac: true
    roleAssignments: []
  }
}

// Log Analytics
module law '../modules/loganalytics.bicep' = {
  name: 'lawEast'
  params: {
    workspaceName: 'workspace-theogenrgeastus'
    location: location
  }
}

// Frontend storage (static site)
module storageModule '../modules/storage.bicep' = {
  name: 'frontendStorage'
  params: {
    storageAccountName: 'theogenfrontpllrx4ji'
    location: location
    skuName: 'Standard_LRS'
    kind: 'StorageV2'
  }
}

// Backend Container App (uses existing managed env)
param managedEnvironmentId string
param image string = 'ca39bdb671caacr.azurecr.io/theogen-backend:latest'

module backendApp '../modules/containerapp.bicep' = {
  name: 'theogenBackend'
  params: {
    containerAppName: 'theogen-backend'
    location: location
    managedEnvironmentId: managedEnvironmentId
    image: image
    keyVaultSecrets: [
      {
        name: 'AZURE_OPENAI_KEY'
        keyVaultSecretId: '${kv.outputs.keyVaultResourceId}/secrets/azure-openai-api-key'
      }
      {
        name: 'AZURE_PG_PASSWORD'
        keyVaultSecretId: '${kv.outputs.keyVaultResourceId}/secrets/azure-pg-password'
      }
      {
        name: 'NEO4J_PASSWORD'
        keyVaultSecretId: '${kv.outputs.keyVaultResourceId}/secrets/neo4j-password'
      }
      {
        name: 'QDRANT_API_KEY'
        keyVaultSecretId: '${kv.outputs.keyVaultResourceId}/secrets/qdrant-api-key'
      }
    ]
    registries: [
      {
        server: 'ca39bdb671caacr.azurecr.io'
        username: ''
        passwordSecretRef: ''
      }
    ]
  }
}

output keyVaultId string = kv.outputs.keyVaultResourceId
output logAnalyticsId string = law.outputs.workspaceId
output backendPrincipalId string = backendApp.outputs.principalId
output backendFqdn string = backendApp.outputs.fqdn
