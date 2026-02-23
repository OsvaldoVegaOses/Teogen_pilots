module storageModule '../modules/storage.bicep' = {
  name: 'theogenStorage'
  params: {
    storageAccountName: 'theogenstwpdxe2pvgl7o6'
    location: 'eastus2'
    skuName: 'Standard_LRS'
    kind: 'StorageV2'
  }
}

output storagePrimaryEndpoints object = storageModule.outputs.primaryEndpoints
