@description('Modulo para crear o actualizar un Azure Container App con identidad gestionada, secretos y escalado configurable')
param containerAppName string
param location string = resourceGroup().location
param managedEnvironmentId string
param image string
param cpu string = '0.5'
param memory string = '1Gi'
@description('Array de objetos { name: string, keyVaultSecretId: string }')
param keyVaultSecrets array = []
@description('Array de objetos { name: string, value: string } para secretos inline')
param inlineSecrets array = []
@description('Array de registry credentials { server: string, username: string, passwordSecretRef: string }')
param registries array = []
@description('Array de variables de entorno planas { name: string, value: string }')
param additionalEnv array = []
@description('Comando del contenedor (opcional), por ejemplo ["python"]')
param command array = []
@description('Argumentos del contenedor (opcional), por ejemplo ["start_worker.py"]')
param args array = []
param minReplicas int = 1
param maxReplicas int = 3
@description('Reglas de escala KEDA para Container Apps')
param scaleRules array = []
param enableIngress bool = false
param ingressExternal bool = false
param targetPort int = 8000

var keyVaultSecretItems = [for s in keyVaultSecrets: {
  name: s.name
  keyVaultUrl: s.keyVaultSecretId
  identity: 'system'
}]

var inlineSecretItems = [for s in inlineSecrets: {
  name: s.name
  value: s.value
}]

var resolvedSecrets = concat(keyVaultSecretItems, inlineSecretItems)

var registryItems = [for r in registries: union(
  { server: r.server },
  contains(r, 'identity') ? { identity: r.identity } : { username: r.username, passwordSecretRef: r.passwordSecretRef }
)]

var keyVaultEnvItems = [for s in keyVaultSecrets: {
  name: s.name
  secretRef: s.name
}]

var inlineSecretEnvItems = [for s in inlineSecrets: {
  name: s.name
  secretRef: s.name
}]

var additionalEnvItems = [for e in additionalEnv: {
  name: e.name
  value: e.value
}]

var resolvedEnv = concat(keyVaultEnvItems, inlineSecretEnvItems, additionalEnvItems)

resource containerApp 'Microsoft.App/containerApps@2025-01-01' = {
  name: containerAppName
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    managedEnvironmentId: managedEnvironmentId
    configuration: {
      // Key Vault-backed secrets are resolved by the app managed identity.
      secrets: resolvedSecrets
      registries: registryItems
      ingress: enableIngress ? {
        external: ingressExternal
        targetPort: targetPort
        transport: 'auto'
      } : null
    }
    template: {
      containers: [
        {
          name: containerAppName
          image: image
          command: command
          args: args
          resources: {
            cpu: cpu
            memory: memory
          }
          env: resolvedEnv
        }
      ]
      scale: {
        minReplicas: minReplicas
        maxReplicas: maxReplicas
        rules: scaleRules
      }
    }
  }
}

output principalId string = containerApp.identity.principalId
output fqdn string = enableIngress ? containerApp.properties.configuration.ingress.fqdn : ''
