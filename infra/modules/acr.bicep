@description('Módulo Bicep para crear Azure Container Registry')
param registryName string
param location string = resourceGroup().location
param sku string = 'Standard'
param adminUserEnabled bool = false

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: registryName
  location: location
  properties: {
    adminUserEnabled: adminUserEnabled
  }
  sku: {
    name: sku
  }
}

output loginServer string = acr.properties.loginServer
output registryResourceId string = acr.id
