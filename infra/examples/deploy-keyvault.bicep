module keyvaultModule '../modules/keyvault.bicep' = {
  name: 'theogenKeyVault'
  params: {
    vaultName: 'theogen-kv-prod'
    location: 'eastus2'
    skuName: 'standard'
    enableRbac: true
    roleAssignments: []
  }
}

output vaultUri string = keyvaultModule.outputs.vaultUri
