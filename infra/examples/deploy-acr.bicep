module acrModule '../modules/acr.bicep' = {
  name: 'theogenAcr'
  params: {
    registryName: 'ca39bdb671caacr'
    location: 'eastus2'
    sku: 'Standard'
    adminUserEnabled: false
  }
}

output acrLoginServer string = acrModule.outputs.loginServer
