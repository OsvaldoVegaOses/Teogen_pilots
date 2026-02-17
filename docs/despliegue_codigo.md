# Códigos para Despliegue de TheoGen

## Despliegue usando Azure CLI

### 1. Prerrequisitos
Antes de comenzar, asegúrate de tener instalado:
- Azure CLI (versión 2.60.0 o superior)
- Bicep CLI (integrado con Azure CLI 2.60+)
- PowerShell 7+ o Bash

### 2. Pasos para el despliegue manual

#### Paso 1: Iniciar sesión en Azure
Debes iniciar sesión directamente en el inquilino correcto. Dado que tienes múltiples inquilinos, usa el ID del inquilino principal:

```bash
# Iniciar sesión directamente en el inquilino principal con MFA
az login --tenant 3e151d68-e5ed-4878-932d-251fe1b0eaf1

# Si necesitas usar la cuenta específica:
az login --tenant 3e151d68-e5ed-4878-932d-251fe1b0eaf1 --username osvaldo_vega@hotmail.com
```

#### Paso 2: Verificar y seleccionar la suscripción correcta
```bash
# Listar todas las suscripciones disponibles
az account list --all --output table

# Seleccionar la suscripción correcta
az account set --subscription "0fbf8e45-6f68-43bb-acbc-36747f267122"
```

#### Paso 3: Verificar la cuenta actual
```bash
# Mostrar información de la cuenta actual
az account show
```

#### Paso 4: Configuración del entorno
Dado que ya tienes los recursos de Azure OpenAI desplegados con los modelos específicos, puedes omitir el despliegue de nuevos modelos y usar los existentes:

**Modelos ya desplegados en tu recurso axial-resource:**
- gpt-5.2-chat
- Kimi-K2.5
- DeepSeek-V3.2-Speciale
- text-embedding-3-large
- model-router
- gpt-4o-transcribe-diarize

#### Paso 5: Navegar al directorio de infraestructura
```bash
cd infra/
```

#### Paso 6: Crear o asegurar el grupo de recursos (solo para otros recursos que no sean OpenAI)
```bash
az group create --name theogen-rg --location westeurope
```

#### Paso 7: Desplegar solo los recursos necesarios (excepto OpenAI que ya tienes)
Si decides desplegar solo los recursos adicionales, puedes modificar el archivo main.bicep para excluir el recurso de OpenAI o usar un archivo diferente que solo cree los otros recursos:

```bash
# Desplegar solo los recursos que no sean OpenAI
az deployment group create \
  --resource-group theogen-rg \
  --template-file main.bicep \
  --parameters projectName=theogen adminPassword="$PASSWORD"
```

#### Paso 8: Configuración post-despliegue
Después del despliegue, configura tu archivo `.env` con los valores obtenidos y los modelos existentes:

```bash
# Crear archivo .env con los valores existentes y nuevos
cat > ../.env << EOF
# TheoGen Environment Variables

# Azure OpenAI (ya existente en tu cuenta)
AZURE_OPENAI_API_KEY=<tu-clave-api-actual>
AZURE_OPENAI_ENDPOINT=https://axial-resource.cognitiveservices.azure.com/
AZURE_OPENAI_API_VERSION=2024-05-01-preview

# Modelos ya desplegados
MODEL_REASONING_ADVANCED=gpt-5.2-chat
MODEL_REASONING_FAST=gpt-4o-transcribe-diarize
MODEL_REASONING_EFFICIENT=model-router
MODEL_CHAT=gpt-4o-transcribe-diarize
MODEL_EMBEDDING=text-embedding-3-large
MODEL_TRANSCRIPTION=gpt-4o-transcribe-diarize
MODEL_ROUTER=model-router
MODEL_KIMI=Kimi-K2.5
MODEL_DEEPSEEK=DeepSeek-V3.2-Speciale

# Azure PostgreSQL
AZURE_PG_USER=theogenadmin
AZURE_PG_PASSWORD=<tu-contraseña-postgres>
AZURE_PG_HOST=<host-postgres-desde-despliegue>
AZURE_PG_DATABASE=theogen

# Azure Storage
AZURE_STORAGE_ACCOUNT=<nombre-cuenta-storage-desde-despliegue>
AZURE_STORAGE_KEY=<clave-storage>

# Azure AD (Entra ID) - Complete manually after registering the app
AZURE_AD_TENANT_ID=3e151d68-e5ed-4878-932d-251fe1b0eaf1
AZURE_AD_CLIENT_ID=<client-id-desde-registro-en-entra-id>
EOF
```

### 3. Despliegue usando GitHub Actions

Crea un archivo `.github/workflows/deploy.yml`:

```yaml
name: Deploy TheoGen Infrastructure

on:
  push:
    branches: [ main ]
  pull_request:
    branches: [ main ]

jobs:
  deploy:
    runs-on: ubuntu-latest
    
    permissions:
      id-token: write
      contents: read
    
    steps:
    - uses: actions/checkout@v4
    
    - name: Setup .NET (for Bicep)
      uses: actions/setup-dotnet@v4
      with:
        dotnet-version: '6.0.x'
    
    - name: Install Azure CLI
      run: |
        curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash
    
    - name: Azure Login
      uses: azure/login@v2
      with:
        creds: ${{ secrets.AZURE_CREDENTIALS }}
    
    - name: Set Subscription
      run: |
        az account set --subscription ${{ secrets.AZURE_SUBSCRIPTION_ID }}
    
    - name: Create Resource Group
      run: |
        az group create --name theogen-rg --location westeurope
    
    - name: Generate Password
      run: |
        PASSWORD=$(openssl rand -base64 32 | tr -d "=+/" | cut -c1-16)
        echo "GENERATED_PASSWORD=${PASSWORD}!" >> $GITHUB_ENV
    
    - name: Deploy Bicep Template (excluding OpenAI if already exists)
      run: |
        az deployment group create \
          --resource-group theogen-rg \
          --template-file infra/main.bicep \
          --parameters projectName=theogen adminPassword="${{ env.GENERATED_PASSWORD }}"
    
    - name: Output Deployment Values
      run: |
        # Get deployment outputs
        POSTGRES_HOST=$(az deployment group show --resource-group theogen-rg --name <deployment-name> --query properties.outputs.postgresHost.value -o tsv)
        STORAGE_ACCOUNT=$(az deployment group show --resource-group theogen-rg --name <deployment-name> --query properties.outputs.storageAccountName.value -o tsv)
        
        echo "PostgreSQL Host: $POSTGRES_HOST"
        echo "Storage Account: $STORAGE_ACCOUNT"
```

### 4. Configuración de Secrets en GitHub

Para usar GitHub Actions, necesitas configurar los siguientes secrets en la configuración de tu repositorio:

- `AZURE_CREDENTIALS`: Credenciales de Azure en formato JSON
- `AZURE_SUBSCRIPTION_ID`: 0fbf8e45-6f68-43bb-acbc-36747f267122

Para generar `AZURE_CREDENTIALS`, ejecuta:
```bash
az ad sp create-for-rbac --name "theogen-deploy-sp" --role Contributor --scopes /subscriptions/0fbf8e45-6f68-43bb-acbc-36747f267122 --sdk-auth
```

### 5. Alternativa: Despliegue con PowerShell

Si prefieres usar PowerShell en lugar de Bash:

```powershell
# Conectar a Azure directamente al inquilino correcto
Connect-AzAccount -TenantId "3e151d68-e5ed-4878-932d-251fe1b0eaf1"
Set-AzContext -SubscriptionId "0fbf8e45-6f68-43bb-acbc-36747f267122"

# Crear grupo de recursos
New-AzResourceGroup -Name theogen-rg -Location westeurope

# Generar contraseña
$Password = -join ((65..90) + (97..122) + (48..57) | Get-Random -Count 16 | ForEach-Object {[char]$_})
$Password += "!"

# Desplegar infraestructura (excluyendo OpenAI si ya existe)
New-AzResourceGroupDeployment `
  -ResourceGroupName theogen-rg `
  -TemplateFile ".\main.bicep" `
  -projectName "theogen" `
  -adminPassword $Password
```

### 6. Registro Manual de Entra ID

Después del despliegue, registra manualmente la aplicación en Microsoft Entra ID:

1. Ve al portal de Azure
2. Navega a "Microsoft Entra ID" > "Registros de aplicaciones"
3. Selecciona "Nuevo registro"
4. Ingresa:
   - Nombre: `theogen-app`
   - Tipos de cuentas admitidas: Cuentas en cualquier directorio organizacional y cuentas personales de Microsoft
   - URI de redirección: 
     - `http://localhost:8000/auth/callback`
     - `https://theogen-app.azurewebsites.net/auth/callback`
5. Copia el ID de aplicación (Client ID) y el ID de directorio (Tenant ID)
6. Actualiza tu archivo `.env` con estos valores

### 7. Solución de problemas comunes

#### Problema: No se encuentran suscripciones
- Asegúrate de tener permisos de acceso a una suscripción de Azure
- Puedes crear una suscripción gratuita o solicitar acceso a una existente

#### Problema: Autenticación multifactor requerida (AADSTS50076)
- Usa `az login --tenant 3e151d68-e5ed-4878-932d-251fe1b0eaf1` para iniciar sesión directamente en el inquilino específico
- Completa el proceso de MFA cuando se te solicite en el navegador
- Si usas PowerShell: `Connect-AzAccount -TenantId "3e151d68-e5ed-4878-932d-251fe1b0eaf1"`

#### Problema: Token expirado en inquilino "Nubeweb" (AADSTS700082)
- Este inquilino no es necesario para tu suscripción activa
- Solo enfócate en el inquilino principal: 3e151d68-e5ed-4878-932d-251fe1b0eaf1
- Si necesitas limpiar credenciales: `az logout` y luego vuelve a iniciar sesión

#### Problema: Múltiples inquilinos
- Siempre especifica explícitamente el inquilino que deseas usar
- Tu suscripción activa está en el inquilino: 3e151d68-e5ed-4878-932d-251fe1b0eaf1
- El inquilino "Nubeweb" (562c5018-0099-4347-afa1-20f01f3d6b54) no es necesario para este despliegue

#### Problema: Ya tienes recursos de Azure OpenAI desplegados
- No es necesario desplegar nuevos modelos de OpenAI si ya tienes los recursos con los modelos necesarios
- Simplemente usa los endpoints existentes en tu configuración
- Asegúrate de tener la clave de API correcta para acceder a los modelos existentes

#### Problema: Token expirado
- Vuelve a iniciar sesión con `az login --tenant 3e151d68-e5ed-4878-932d-251fe1b0eaf1`
- Si usas scripts automatizados, considera renovar las credenciales de entidad de servicio

### 8. Información de tu suscripción

Tu suscripción actual es:
- Nombre: Patrocinio de Microsoft Azure
- ID: 0fbf8e45-6f68-43bb-acbc-36747f267122
- Directorio: Directorio predeterminado (osvaldovegahotmail.onmicrosoft.com)
- ID de Directorio: 3e151d68-e5ed-4878-932d-251fe1b0eaf1
- Estado: Activo
- Tipo: Patrocinio de Azure

Importante: El inquilino "Nubeweb" (562c5018-0099-4347-afa1-20f01f3d6b54) tiene un token expirado y no debe usarse para este despliegue. Solo trabaja con el inquilino principal.

Además, ya tienes desplegados los siguientes modelos en tu recurso axial-resource:
- gpt-5.2-chat
- Kimi-K2.5
- DeepSeek-V3.2-Speciale
- text-embedding-3-large
- model-router
- gpt-4o-transcribe-diarize

Estos modelos pueden ser utilizados directamente en la aplicación TheoGen sin necesidad de desplegar nuevos recursos de Azure OpenAI.

Estos códigos te permitirán desplegar la infraestructura de TheoGen tanto manualmente como mediante integración continua con GitHub Actions.