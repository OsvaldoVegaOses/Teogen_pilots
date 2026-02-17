// infra/modules/openai.bicep
param location string
param accountName string

resource openai 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: accountName
  location: location
  kind: 'OpenAI'
  sku: {
    name: 'S0'
  }
  properties: {
    publicNetworkAccess: 'Enabled'
    customSubDomainName: accountName
  }
}

// GPT-4o Deployment
resource gpt4o 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: openai
  name: 'gpt-4o'
  sku: {
    name: 'Standard'
    capacity: 20
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-4o'
      version: '2024-08-06'
    }
  }
}

// GPT-35-Turbo Deployment
resource gpt35turbo 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: openai
  name: 'gpt-35-turbo'
  sku: {
    name: 'Standard'
    capacity: 20
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-35-turbo'
      version: '0613'
    }
  }
}

// text-embedding-3-large
resource embeddingLarge 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: openai
  name: 'text-embedding-3-large'
  sku: {
    name: 'Standard'
    capacity: 50
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'text-embedding-3-large'
      version: '1'
    }
  }
}

output endpoint string = openai.properties.endpoint
output id string = openai.id