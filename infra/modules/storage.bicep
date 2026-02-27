@description('Module to deploy a single Azure Storage account used by TheoGen.')
param location string = resourceGroup().location

@description('Preferred storage account name.')
param storageAccountName string = ''

@description('Backward-compatible alias for storageAccountName.')
param accountName string = ''

@description('Storage SKU name.')
param skuName string = 'Standard_LRS'

@description('Storage account kind.')
param kind string = 'StorageV2'

@description('Enable static website on blob service.')
param enableStaticWebsite bool = false

@description('Blob containers to create.')
param blobContainerNames array = [
  'theogen-audio'
  'theogen-documents'
  'theogen-exports'
  'theogen-backups'
]

var effectiveStorageAccountName = !empty(storageAccountName) ? storageAccountName : accountName

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: effectiveStorageAccountName
  location: location
  sku: {
    name: skuName
  }
  kind: kind
  properties: {
    accessTier: 'Hot'
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    networkAcls: {
      bypass: 'AzureServices'
      defaultAction: 'Allow'
    }
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storage
  name: 'default'
  properties: {
    staticWebsite: {
      enabled: enableStaticWebsite
      indexDocument: 'index.html'
      errorDocument404Path: '404.html'
    }
  }
}

resource blobContainers 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = [
  for containerName in blobContainerNames: {
    parent: blobService
    name: containerName
    properties: {
      publicAccess: 'None'
    }
  }
]

output name string = storage.name
output id string = storage.id
output storageAccountId string = storage.id
output primaryEndpoints object = storage.properties.primaryEndpoints
