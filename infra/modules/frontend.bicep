// Módulo Bicep para recursos de frontend de TheoGen

param location string = resourceGroup().location
param projectName string
param environment string = 'prod'
param principalId string = ''

// Nombre único para la cuenta de almacenamiento estático
var storageAccountName = toLower('${projectName}front${uniqueString(resourceGroup().id)}')

// Recurso de Storage Account para hospedar el sitio web estático
resource storageAccount 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name: storageAccountName
  location: location
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    staticWebsite: {
      enabled: true
      indexDocument: 'index.html'
      error404Document: '404.html'
    }
  }
}

// Obtener la URL del sitio web estático
output frontendUrl string = storageAccount.properties.primaryEndpoints.web
output storageAccountId string = storageAccount.id

// Si se proporciona un principalId, asignar roles para CI/CD
resource roleAssignment 'Microsoft.Authorization/roleAssignments@2020-10-01' = if(!empty(principalId)) {
  scope: storageAccount
  name: guid(resourceGroup().id, principalId, 'StorageBlobDataContributor')
  properties: {
    roleDefinitionId: '/subscriptions/${subscription().subscriptionId}/providers/Microsoft.Authorization/roleDefinitions/ba92f5b4-2d11-453d-a403-e96b0029c9fe' // Storage Blob Data Contributor
    principalId: principalId
    principalType: 'ServicePrincipal'
  }
}

// Crear un contenedor de CDN si se va a usar para mejor rendimiento
resource cdnProfile 'Microsoft.Cdn/profiles@2021-06-01' = {
  name: '${projectName}-cdn-${environment}'
  location: 'Global'
  sku: {
    name: 'Standard_Microsoft'
  }
}

resource cdnEndpoint 'Microsoft.Cdn/profiles/endpoints@2021-06-01' = {
  name: '${projectName}-endpoint'
  location: 'Global'
  parent: cdnProfile
  properties: {
    origins: [
      {
        name: 'origin-storage'
        hostName: '${storageAccountName}.z13.web.core.windows.net'
        httpPort: 80
        httpsPort: 443
      }
    ]
    originHostHeader: '${storageAccountName}.z13.web.core.windows.net'
    isHttpAllowed: true
    isHttpsAllowed: true
    queryStringCachingBehavior: 'IgnoreQueryString'
    contentTypesToCompress: [
      'text/plain'
      'text/html'
      'text/css'
      'application/json'
      'application/javascript'
      'text/javascript'
      'application/xml'
      'text/xml'
      'image/svg+xml'
    ]
    isCompressionEnabled: true
  }
}

output cdnEndpointUrl string = 'https://${cdnEndpoint.properties.hostName}'
