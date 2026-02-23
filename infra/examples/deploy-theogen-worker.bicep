param managedEnvironmentId string
param keyVaultId string
param redisHost string
param image string = 'ca39bdb671caacr.azurecr.io/theogen-backend:latest'

module workerApp '../modules/containerapp.bicep' = {
  name: 'theogenTheoryWorkerApp'
  params: {
    containerAppName: 'theogen-theory-worker'
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
        name: 'AZURE_REDIS_KEY'
        keyVaultSecretId: '${keyVaultId}/secrets/azure-redis-key'
      }
      {
        name: 'AZURE_OPENAI_KEY'
        keyVaultSecretId: '${keyVaultId}/secrets/azure-openai-api-key'
      }
      {
        name: 'AZURE_PG_PASSWORD'
        keyVaultSecretId: '${keyVaultId}/secrets/azure-pg-password'
      }
      {
        name: 'NEO4J_PASSWORD'
        keyVaultSecretId: '${keyVaultId}/secrets/neo4j-password'
      }
      {
        name: 'QDRANT_API_KEY'
        keyVaultSecretId: '${keyVaultId}/secrets/qdrant-api-key'
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
        identity: 'system'
      }
    ]
  }
}

output workerPrincipalId string = workerApp.outputs.principalId
