param managedEnvironmentId string
param keyVaultId string
param image string = 'ca39bdb671caacr.azurecr.io/theogen-backend:latest'

module backendApp '../modules/containerapp.bicep' = {
  name: 'theogenBackendApp'
  params: {
    containerAppName: 'theogen-backend'
    managedEnvironmentId: managedEnvironmentId
    image: image
    keyVaultSecrets: [
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
    registries: [
      {
        server: 'ca39bdb671caacr.azurecr.io'
        username: ''
        passwordSecretRef: ''
      }
    ]
  }
}

output backendPrincipalId string = backendApp.outputs.principalId
output backendFqdn string = backendApp.outputs.fqdn
