// infra/remaining_resources.bicep
// Despliegue de recursos restantes para TheoGen

targetScope = 'resourceGroup'

param projectName string = 'theogen'
param adminUsername string = 'theogenadmin'
@secure()
param adminPassword string

var uniqueSuffix = uniqueString(resourceGroup().id)

// PostgreSQL Flexible Server
resource postgresServer 'Microsoft.DBforPostgreSQL/flexibleServers@2023-12-01-preview' = {
  name: '${projectName}-pg-${uniqueSuffix}'
  // Cambiamos a una ubicación que esté disponible para esta suscripción
  location: 'eastus'
  sku: {
    name: 'Standard_B1ms'
    tier: 'Burstable'
  }
  properties: {
    administratorLogin: adminUsername
    administratorLoginPassword: adminPassword
    version: '16'
    storage: {
      storageSizeGB: 32
    }
    backup: {
      backupRetentionDays: 7
      geoRedundantBackup: 'Enabled'
    }
    network: {
      publicNetworkAccess: 'Disabled'  // Acceso privado
    }
  }
}

// Crear la base de datos en el servidor PostgreSQL
resource postgresDatabase 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2023-12-01-preview' = {
  parent: postgresServer
  name: 'theogen'
}

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
}

// Contenedor para audio
resource audioContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: 'theogen-audio'
}

// Contenedor para documentos
resource docsContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: 'theogen-documents'
}

// Contenedor para exportaciones
resource exportsContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: 'theogen-exports'
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
output postgresHost string = postgresServer.properties.fullyQualifiedDomainName
output redisHostName string = redisCache.properties.hostName
output storageAccountName string = storageAccount.name
output speechEndpoint string = speechService.properties.endpoint