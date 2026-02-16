// infra/modules/foundry.bicep
param location string
param hubName string

resource hub 'Microsoft.MachineLearningServices/workspaces@2024-10-01' = {
  name: hubName
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    friendlyName: 'TheoGen Foundry Hub'
    description: 'Microsoft Foundry hub for TheoGen theory generation'
    hbiWorkspace: false
    v1LegacyMode: false
  }
  sku: {
    name: 'Basic'
    tier: 'Basic'
  }
}

output id string = hub.id
