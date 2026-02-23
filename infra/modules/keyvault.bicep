@description('Bicep module para crear un Key Vault con asignaciones de rol opcionales')
param vaultName string
param location string = resourceGroup().location
param skuName string = 'standard'
param enableRbac bool = true
@description('Array de objetos { principalId: string, roleDefinitionId: string, principalType?: string }')
param roleAssignments array = []

resource kv 'Microsoft.KeyVault/vaults@2022-07-01' = {
  name: vaultName
  location: location
  properties: {
    tenantId: subscription().tenantId
    sku: {
      family: 'A'
      name: skuName
    }
    accessPolicies: []
    enableRbacAuthorization: enableRbac
    publicNetworkAccess: 'Enabled'
  }
}

// Crear role assignments (opcionales). Cada entrada debe incluir roleDefinitionId (GUID) y principalId.
// Role assignments must be created at the scope of the Key Vault resource
resource kvRoleAssignments 'Microsoft.Authorization/roleAssignments@2020-04-01-preview' = [for ra in roleAssignments: if (ra.principalId != '') {
  scope: kv
  name: guid(kv.id, ra.principalId, ra.roleDefinitionId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', ra.roleDefinitionId)
    principalId: ra.principalId
    principalType: empty(ra.principalType) ? 'ServicePrincipal' : ra.principalType
  }
}]

output vaultUri string = kv.properties.vaultUri
output keyVaultResourceId string = kv.id
