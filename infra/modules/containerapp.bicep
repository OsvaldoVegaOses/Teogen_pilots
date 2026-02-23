@description('Módulo para crear o actualizar un Azure Container App con identidad gestionada y referencias a secretos en Key Vault')
param containerAppName string
param location string = resourceGroup().location
param managedEnvironmentId string
param image string
param cpu string = '0.5'
param memory string = '1Gi'
@description('Array de objetos { name: string, keyVaultSecretId: string }')
param keyVaultSecrets array = []
@description('Array de registry credentials { server: string, username: string, password: string }')
param registries array = []

resource containerApp 'Microsoft.App/containerApps@2025-01-01' = {
  name: containerAppName
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    managedEnvironmentId: managedEnvironmentId
    configuration: {
      // Declare secret names; values will be set after deployment from Key Vault
      secrets: [for s in keyVaultSecrets: {
        name: s.name
      }]
      registries: [for r in registries: {
        server: r.server
        username: r.username
        passwordSecretRef: r.passwordSecretRef
      }]
    }
    template: {
      containers: [
        {
          name: containerAppName
          image: image
          resources: {
            cpu: cpu
            memory: memory
          }
          env: [for s in keyVaultSecrets: {
            name: s.name
            secretRef: s.name
          }]
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 3
      }
    }
  }
}

output principalId string = containerApp.identity.principalId
output fqdn string = containerApp.properties.configuration.ingress.fqdn
