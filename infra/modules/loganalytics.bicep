@description('Modulo para crear un Log Analytics Workspace')
param workspaceName string
param location string = resourceGroup().location

resource law 'Microsoft.OperationalInsights/workspaces@2021-06-01' = {
  name: workspaceName
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

output workspaceId string = law.id
output workspaceCustomerId string = law.properties.customerId
