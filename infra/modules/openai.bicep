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

// GPT-5.2 Deployment
resource gpt52 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: openai
  name: 'gpt-5.2'
  sku: {
    name: 'Standard'
    capacity: 20
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-5.2'
      version: '2025-02-01'
    }
  }
}

// Claude 3.5 Sonnet Deployment
resource claude 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: openai
  name: 'claude-3-5-sonnet'
  sku: {
    name: 'Standard'
    capacity: 20
  }
  properties: {
    model: {
      format: 'Anthropic'
      name: 'claude-3-5-sonnet-20241022'
      version: '20241022'
    }
  }
}

// o3-mini Deployment
resource o3mini 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: openai
  name: 'o3-mini'
  sku: {
    name: 'Standard'
    capacity: 30
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'o3-mini'
      version: '2025-01-31'
    }
  }
}

// text-embedding-3-large
resource embedding 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
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
