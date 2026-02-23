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
param redisHost string
param image string = 'ca39bdb671caacr.azurecr.io/theogen-backend:latest'

module backendApp '../modules/containerapp.bicep' = {
  name: 'theogenBackend'
  params: {
    containerAppName: 'theogen-backend'
    location: location
    managedEnvironmentId: managedEnvironmentId
    image: image
    enableIngress: true
    ingressExternal: true
    targetPort: 8000
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
        name: 'AZURE_REDIS_KEY'
        keyVaultSecretId: '${kv.outputs.keyVaultResourceId}/secrets/azure-redis-key'
      }
      {
        name: 'QDRANT_API_KEY'
        keyVaultSecretId: '${kv.outputs.keyVaultResourceId}/secrets/qdrant-api-key'
      }
    ]
    additionalEnv: [
      {
        name: 'AZURE_REDIS_HOST'
        value: redisHost
      }
      {
        name: 'THEORY_USE_CELERY'
        value: 'true'
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

// Worker Container App (Celery)
module theoryWorker '../modules/containerapp.bicep' = {
  name: 'theogenTheoryWorker'
  params: {
    containerAppName: 'theogen-theory-worker'
    location: location
    managedEnvironmentId: managedEnvironmentId
    image: image
    command: [
      'python'
    ]
    args: [
      'start_worker.py'
    ]
    cpu: '1.0'
    memory: '2Gi'
    minReplicas: 1
    maxReplicas: 10
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
        name: 'AZURE_REDIS_KEY'
        keyVaultSecretId: '${kv.outputs.keyVaultResourceId}/secrets/azure-redis-key'
      }
      {
        name: 'QDRANT_API_KEY'
        keyVaultSecretId: '${kv.outputs.keyVaultResourceId}/secrets/qdrant-api-key'
      }
    ]
    additionalEnv: [
      {
        name: 'AZURE_REDIS_HOST'
        value: redisHost
      }
      {
        name: 'THEORY_USE_CELERY'
        value: 'true'
      }
    ]
    scaleRules: [
      {
        name: 'celery-queue-depth'
        custom: {
          type: 'redis'
          metadata: {
            address: '${redisHost}:6380'
            listName: 'celery'
            listLength: '5'
            enableTLS: 'true'
          }
          auth: [
            {
              secretRef: 'AZURE_REDIS_KEY'
              triggerParameter: 'password'
            }
          ]
        }
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
output workerPrincipalId string = theoryWorker.outputs.principalId
