// infra/basic_resources.bicep
// Despliegue de recursos básicos para TheoGen (sin PostgreSQL para evitar problemas de cuota)

targetScope = 'resourceGroup'

param projectName string = 'theogen'

var uniqueSuffix = uniqueString(resourceGroup().id)

// Azure Cache for Redis
resource redisCache 'Microsoft.Cache/redis@2024-03-01' = {
  name: '${projectName}-redis-${uniqueSuffix}'
  location: 'eastus'
  properties: {
    sku: {
      name: 'Standard'
      family: 'C'
      capacity: 2
    }
    enableNonSslPort: false
    minimumTlsVersion: '1.2'
    // Versión válida de Redis
    redisVersion: '6'
  }
}

// Cuenta de almacenamiento
resource storageAccount 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: '${projectName}st${uniqueSuffix}'
  location: 'eastus'
  kind: 'StorageV2'
  sku: {
    name: 'Standard_LRS'
  }
  properties: {
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    networkAcls: {
      bypass: 'AzureServices'
      defaultAction: 'Allow'
    }
  }
}

// Blob service para la cuenta de almacenamiento (necesario para los contenedores)
resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storageAccount
  name: 'default'
  properties: {
    cors: {
      corsRules: []
    }
  }
}

// Contenedor para audio
resource audioContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: 'theogen-audio'
  properties: {
    publicAccess: 'None'
  }
}

// Contenedor para documentos
resource docsContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: 'theogen-documents'
  properties: {
    publicAccess: 'None'
  }
}

// Contenedor para exportaciones
resource exportsContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: 'theogen-exports'
  properties: {
    publicAccess: 'None'
  }
}

// Servicio de Speech
resource speechService 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: '${projectName}-speech-${uniqueSuffix}'
  location: 'eastus'
  kind: 'SpeechServices'
  sku: {
    name: 'S0'
  }
}

// Outputs
output redisHostName string = redisCache.properties.hostName
output storageAccountName string = storageAccount.name
output speechEndpoint string = speechService.properties.endpoint