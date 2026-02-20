# TheoGen — Informe Final de Despliegue en Azure

> **Fecha:** 20 de febrero de 2026  
> **Suscripción:** Patrocinio de Microsoft Azure (`0fbf8e45-6f68-43bb-acbc-36747f267122`)  
> **Autor:** Equipo TheoGen  
> **Propósito:** Servir como referencia paso a paso para futuros despliegues y evitar repetir los errores encontrados.

---

## 1. Arquitectura del Sistema

```
┌──────────────────────────────────────────────────────────────────┐
│                      USUARIOS / NAVEGADOR                       │
└───────────────────────────┬──────────────────────────────────────┘
                            │ HTTPS
                            ▼
┌──────────────────────────────────────────────────────────────────┐
│  FRONTEND — Azure Blob Storage (Static Website)                 │
│  Cuenta: theogenfrontpllrx4ji   |  RG: theogen-rg               │
│  URL: theogenfrontpllrx4ji.z13.web.core.windows.net             │
│  Tech: Next.js 16 + React 19 + MSAL React 5                    │
│  Tipo: Exportación estática (output: "export")                  │
└───────────────────────────┬──────────────────────────────────────┘
                            │ HTTPS + Bearer Token (JWT)
                            ▼
┌──────────────────────────────────────────────────────────────────┐
│  BACKEND — Azure Container Apps                                  │
│  App: theogen-backend  |  RG: theogen-rg-eastus                  │
│  FQDN: theogen-backend.gentlemoss-dcba183f.eastus                │
│         .azurecontainerapps.io                                   │
│  Tech: FastAPI + Python 3.11 + Uvicorn                           │
│  Imagen: ca39bdb671caacr.azurecr.io/theogen-backend:latest       │
└──────┬──────────┬──────────┬──────────┬──────────┬───────────────┘
       │          │          │          │          │
       ▼          ▼          ▼          ▼          ▼
   PostgreSQL   Neo4j     Qdrant    Azure      Azure
   (Azure)     (Aura)    (Cloud)   OpenAI    Speech/Storage/Redis
```

### Flujo de Autenticación

```
Navegador → MSAL loginRedirect → Azure AD (Entra ID)
         → ID Token (JWT) devuelto al /login/
         → Frontend envía Authorization: Bearer <token> al backend
         → Backend valida firma JWT contra JWKS de Azure AD
         → Extrae oid/sub del token → UUID de usuario para aislamiento de datos
```

---

## 2. Inventario de Recursos Azure

| Recurso | Nombre | Grupo de Recursos | Región |
|---------|--------|-------------------|--------|
| Container App (Backend) | `theogen-backend` | `theogen-rg-eastus` | East US |
| Managed Environment | `theogen-env` | `theogen-rg-eastus` | East US |
| Container Registry (ACR) | `ca39bdb671caacr` | `theogen-rg-eastus` | East US |
| Storage (Frontend) | `theogenfrontpllrx4ji` | `theogen-rg` | East US |
| Storage (Archivos) | `theogenstwpdxe2pvgl7o6` | `theogen-rg-eastus` | East US |
| PostgreSQL Flexible | `theogen-pg-wpdxe2pvgl7o6` | `theogen-rg-eastus` | East US |
| Redis Cache | `theogen-redis-wpdxe2pvgl7o6` | `theogen-rg-eastus` | East US |
| Azure OpenAI | `axial-resource` | — | — |
| Speech Services | — | — | West Europe |
| Entra ID App Registration | Client ID: `c6d2cf71-dcd2-4400-a8be-9eb8c16b1174` | Tenant: `3e151d68-e5ed-4878-932d-251fe1b0eaf1` | — |
| Neo4j Aura (externo) | Instancia `df99d531` | — | — |
| Qdrant Cloud (externo) | Cluster `30df124f-...` | — | GCP us-east4 |

---

## 3. Despliegue del Backend — Paso a Paso

### 3.1 Prerrequisitos

```powershell
# Azure CLI instalado y sesión activa
az login
az account set --subscription "0fbf8e45-6f68-43bb-acbc-36747f267122"

# Verificar acceso al ACR
az acr show --name ca39bdb671caacr --query loginServer -o tsv
# Esperado: ca39bdb671caacr.azurecr.io
```

### 3.2 Construir la imagen Docker en ACR

```powershell
# Desde la raíz del proyecto (NO desde backend/)
az acr build --registry ca39bdb671caacr --image theogen-backend:latest ./backend
```

Esto envía la carpeta `backend/` al ACR, ejecuta el `Dockerfile` en la nube y almacena la imagen resultante. No necesita Docker instalado localmente.

**Estructura del Dockerfile (referencia):**
```dockerfile
FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends build-essential libpq-dev
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 3.3 Crear o Actualizar el Container App

**⚠️ LECCIÓN APRENDIDA:** No usar `az containerapp update` si el provisioning está atascado. Ver sección de errores.

**Creación limpia con YAML (método recomendado):**

```yaml
# containerapp_create.yaml
location: East US
type: Microsoft.App/containerApps
identity:
  type: SystemAssigned
properties:
  environmentId: /subscriptions/<SUB_ID>/resourceGroups/theogen-rg-eastus/providers/Microsoft.App/managedEnvironments/theogen-env
  configuration:
    activeRevisionsMode: Single
    ingress:
      external: true
      targetPort: 8000
      transport: Auto
      allowInsecure: false
      traffic:
      - latestRevision: true
        weight: 100
    registries:
    - server: ca39bdb671caacr.azurecr.io
      username: ca39bdb671caacr
      passwordSecretRef: acr-password
    secrets:
    - name: acr-password
      value: <PASSWORD_DEL_ACR>
  template:
    containers:
    - name: theogen-backend
      image: ca39bdb671caacr.azurecr.io/theogen-backend:latest
      resources:
        cpu: 0.5
        memory: 1Gi
      env:
      - name: AZURE_AD_TENANT_ID
        value: "3e151d68-e5ed-4878-932d-251fe1b0eaf1"
      - name: AZURE_AD_CLIENT_ID
        value: "c6d2cf71-dcd2-4400-a8be-9eb8c16b1174"
      # ... resto de variables de entorno
    scale:
      minReplicas: 1
      maxReplicas: 10
```

```powershell
# Obtener password del ACR
az acr credential show --name ca39bdb671caacr --query "passwords[0].value" -o tsv

# Crear el Container App
az containerapp create --name theogen-backend --resource-group theogen-rg-eastus --yaml containerapp_create.yaml
```

### 3.4 Verificación post-despliegue

```powershell
# 1. Estado del provisioning — DEBE ser "Succeeded"
az containerapp show --name theogen-backend --resource-group theogen-rg-eastus `
  --query "{state: properties.provisioningState, fqdn: properties.configuration.ingress.fqdn}" -o json

# 2. La raíz debe responder 200
Invoke-WebRequest -Uri "https://theogen-backend.gentlemoss-dcba183f.eastus.azurecontainerapps.io/" -UseBasicParsing | Select-Object StatusCode

# 3. /api/projects/ sin token debe responder 401 (NO 500)
try {
    Invoke-WebRequest -Uri "https://theogen-backend.gentlemoss-dcba183f.eastus.azurecontainerapps.io/api/projects/" -UseBasicParsing
} catch {
    Write-Host "StatusCode: $($_.Exception.Response.StatusCode.Value__)"
    Write-Host "Response: $($_.ErrorDetails.Message)"
}
# Esperado: 401 "Authentication required. Provide a Bearer token."
# Si da 500 "Authentication not configured on server" → las env vars NO llegaron al contenedor

# 4. Logs de arranque limpios
az containerapp logs show --name theogen-backend --resource-group theogen-rg-eastus --tail 10 --type console
```

### 3.5 Variables de entorno obligatorias del backend

| Variable | Descripción | Crítica |
|----------|-------------|---------|
| `AZURE_AD_TENANT_ID` | Tenant de Azure AD para validar JWT | Sí — sin ella da 500 |
| `AZURE_AD_CLIENT_ID` | Client ID de la app registration | Sí — sin ella da 500 |
| `NEO4J_URI` | URI de la base de datos Neo4j | Sí — sin ella no arranca |
| `NEO4J_USER` | Usuario de Neo4j (ojo: NO `NEO4J_USERNAME`) | Sí |
| `NEO4J_PASSWORD` | Password de Neo4j | Sí |
| `QDRANT_URL` | URL del cluster de Qdrant | Sí — sin ella no arranca |
| `AZURE_PG_HOST` | Hostname del PostgreSQL | Para persistencia |
| `AZURE_PG_USER` / `AZURE_PG_PASSWORD` | Credenciales PostgreSQL | Para persistencia |
| `AZURE_OPENAI_API_KEY` | Clave de Azure OpenAI | Para funciones de IA |
| `AZURE_OPENAI_ENDPOINT` | Endpoint de Azure OpenAI | Para funciones de IA |
| `AZURE_STORAGE_ACCOUNT` / `AZURE_STORAGE_KEY` | Azure Storage | Para audio/archivos |
| `FRONTEND_URL` | URL del frontend (para CORS) | Recomendada |

> **⚠️ TRAMPA COMÚN:** `settings.py` espera `NEO4J_USER`, pero algunos scripts crean la variable como `NEO4J_USERNAME`. Si solo existe `NEO4J_USERNAME`, Pydantic no la lee y la app falla al arrancar. Asegurar que existan ambas o solo `NEO4J_USER`.

---

## 4. Despliegue del Frontend — Paso a Paso

### 4.1 Prerrequisitos

```powershell
# Node.js 18+ y npm instalados
node --version
npm --version

# Sesión Azure activa
az login
```

### 4.2 Configurar variables de entorno para el build

Next.js incorpora las variables `NEXT_PUBLIC_*` en tiempo de compilación. **No se pueden cambiar después del build**.

```powershell
# En frontend/.env.local (para desarrollo)
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api
NEXT_PUBLIC_AZURE_AD_TENANT_ID=3e151d68-e5ed-4878-932d-251fe1b0eaf1
NEXT_PUBLIC_AZURE_AD_CLIENT_ID=c6d2cf71-dcd2-4400-a8be-9eb8c16b1174

# Para producción, inyectarlas como variables de entorno del proceso
$env:NEXT_PUBLIC_API_BASE_URL = "https://theogen-backend.gentlemoss-dcba183f.eastus.azurecontainerapps.io/api"
$env:NEXT_PUBLIC_AZURE_AD_TENANT_ID = "3e151d68-e5ed-4878-932d-251fe1b0eaf1"
$env:NEXT_PUBLIC_AZURE_AD_CLIENT_ID = "c6d2cf71-dcd2-4400-a8be-9eb8c16b1174"
```

### 4.3 Compilar como sitio estático

```powershell
cd frontend
npm install     # Solo la primera vez o si cambió package.json
npm run build   # Genera carpeta out/ con el sitio estático
```

**Configuración crítica en `next.config.ts`:**
```typescript
const nextConfig: NextConfig = {
  output: "export",       // OBLIGATORIO: genera sitio estático
  trailingSlash: true,    // OBLIGATORIO: rutas terminan en / para Azure Blob
  images: {
    unoptimized: true     // OBLIGATORIO: no hay servidor para optimizar imágenes
  },
  reactStrictMode: true,
};
```

### 4.4 Subir a Azure Blob Storage

```powershell
# Obtener nombre y clave del storage account
$storageAccount = "theogenfrontpllrx4ji"
$storageKey = az storage account keys list --resource-group theogen-rg --account-name $storageAccount --query "[0].value" -o tsv

# Subir todo el contenido de out/ al contenedor $web
az storage blob upload-batch `
    --account-name $storageAccount `
    --account-key $storageKey `
    --destination '$web' `
    --source ./out `
    --overwrite true
```

### 4.5 Verificación

```powershell
# La URL del frontend
Invoke-WebRequest -Uri "https://theogenfrontpllrx4ji.z13.web.core.windows.net/" -UseBasicParsing | Select-Object StatusCode
# Esperado: 200
```

### 4.6 Script automatizado

Ejecutar `deploy_frontend_fixed.ps1` desde la raíz del proyecto realiza todos los pasos anteriores de forma automática.

---

## 5. Configuración de Autenticación (Microsoft Entra ID)

### 5.1 App Registration

1. Azure Portal → Microsoft Entra ID → Registros de aplicaciones
2. Crear o seleccionar la aplicación `theogen-app`
3. Configurar:
   - **Tipo de cuenta:** Cuentas en cualquier directorio organizacional + cuentas personales de Microsoft
   - **URI de redirección (SPA):**
     - `http://localhost:3000/login/` (desarrollo)
     - `https://theogenfrontpllrx4ji.z13.web.core.windows.net/login/` (producción)
   - **Tipo de plataforma:** SPA (Single Page Application) — NO Web
4. Anotar:
   - `Application (client) ID` → `AZURE_AD_CLIENT_ID` / `NEXT_PUBLIC_AZURE_AD_CLIENT_ID`
   - `Directory (tenant) ID` → `AZURE_AD_TENANT_ID` / `NEXT_PUBLIC_AZURE_AD_TENANT_ID`

### 5.2 Flujo de autenticación en el frontend

**Archivo clave: `frontend/src/app/providers.tsx`**

```
MsalProvider (de @azure/msal-react)
└── Llama a handleRedirectPromise() INTERNAMENTE
    └── Emite eventos: LOGIN_SUCCESS, HANDLE_REDIRECT_END
        └── providers.tsx escucha estos eventos para setActiveAccount
```

> **⚠️ LECCIÓN APRENDIDA:** NUNCA llamar a `handleRedirectPromise()` manualmente cuando se usa `<MsalProvider>`. El provider ya lo hace internamente. Llamarlo dos veces genera el warning `BrowserAuthError 1e88vg` y puede causar loops de redirección.

### 5.3 Validación del token en el backend

**Archivo clave: `backend/app/core/auth.py`**

El backend valida tokens JWT contra las claves públicas de Azure AD (JWKS):

```python
TENANT_ID = settings.AZURE_AD_TENANT_ID   # Si está vacío → HTTP 500
CLIENT_ID = settings.AZURE_AD_CLIENT_ID   # Si está vacío → HTTP 500

# El token se valida con:
payload = jwt.decode(
    token, signing_key, algorithms=["RS256"],
    audience=CLIENT_ID,
    issuer=[ISSUER_V1, ISSUER_V2],  # Ambos issuers para compatibilidad v1/v2
)
```

> **⚠️ LECCIÓN APRENDIDA:** El claim `sub` de tokens de Azure AD no siempre es un UUID canónico. El código tiene un fallback con `uuid5(NAMESPACE_URL, f"theogen-user:{oid}")` para generar un UUID determinístico. Sin esto, `UUID(oid)` lanza `ValueError` y el endpoint devuelve 500.

---

## 6. Errores Encontrados y Soluciones

### 6.1 Container App atascado en "InProgress" (CRÍTICO)

**Síntoma:** `az containerapp update` se ejecuta, el `provisioningState` pasa a `InProgress` y nunca llega a `Succeeded`. Eventualmente cambia a `Failed`. Todas las operaciones subsiguientes fallan con `ContainerAppOperationInProgress`.

**Causa raíz:** Un registro ACR obsoleto (`axialacrnew.azurecr.io` con `identity: system`) estaba en la configuración del Container App. Azure intentaba validar el acceso a ese registro inexistente o inaccesible, lo que bloqueaba el despliegue.

**Solución:**
```powershell
# 1. Eliminar el container app bloqueado
az containerapp delete --name theogen-backend --resource-group theogen-rg-eastus --yes --no-wait

# 2. Esperar a que se elimine (~30 seg)
az containerapp show --name theogen-backend --resource-group theogen-rg-eastus 2>&1
# Esperado: ResourceNotFound

# 3. Recrear con YAML limpio (sin registros obsoletos)
az containerapp create --name theogen-backend --resource-group theogen-rg-eastus --yaml containerapp_create.yaml
```

**Prevención futura:**
- Al migrar de un proyecto anterior, **eliminar registros ACR** que ya no se usan
- Verificar SIEMPRE que `provisioningState` sea `Succeeded` tras cada operación
- Si se queda en `InProgress` más de 5 minutos, no insistir con más updates — eliminar y recrear

### 6.2 Backend devuelve 500 "Authentication not configured on server"

**Síntoma:** `GET /api/projects/` devuelve HTTP 500 con `{"detail":"Authentication not configured on server"}`.

**Causa raíz:** Las variables `AZURE_AD_TENANT_ID` y `AZURE_AD_CLIENT_ID` no estaban presentes en el contenedor en ejecución. Aunque estaban en el template del Container App, la revisión activa fue creada **ANTES** de que se añadieran.

**Diagnóstico:**
```python
# En auth.py, esta guarda es la que genera el 500:
if not TENANT_ID or not CLIENT_ID:
    raise HTTPException(status_code=500, detail="Authentication not configured on server")
```

**Solución:** Asegurar que las variables estén en el YAML de creación ANTES de crear la revisión. Verificar con:
```powershell
az containerapp show --name theogen-backend --resource-group theogen-rg-eastus `
  --query "properties.template.containers[0].env[?name=='AZURE_AD_TENANT_ID']" -o json
```

Y confirmar que el contenedor realmente las ve:
```powershell
# Un endpoint sin auth debe dar 401, no 500
# 401 = auth configurada pero sin token
# 500 = variables de entorno faltantes
```

### 6.3 Warning MSAL `BrowserAuthError 1e88vg`

**Síntoma:** Consola del navegador muestra `Warning: 1e88vg` repetidamente al cargar la app.

**Causa raíz:** `providers.tsx` llamaba a `instance.handleRedirectPromise()` manualmente, pero `<MsalProvider>` ya lo hace internamente. Doble llamada = warning.

**Solución:** Eliminar la llamada manual y usar callbacks de eventos:
```typescript
// ❌ INCORRECTO — no hacer esto dentro de MsalProvider
await instance.handleRedirectPromise();

// ✅ CORRECTO — escuchar eventos del provider
const callbackId = instance.addEventCallback((event) => {
    if (event.eventType === EventType.LOGIN_SUCCESS) {
        instance.setActiveAccount(event.payload.account);
    }
    if (event.eventType === EventType.HANDLE_REDIRECT_END) {
        // Restaurar cuenta activa desde caché
        const accounts = instance.getAllAccounts();
        if (accounts.length > 0 && !instance.getActiveAccount()) {
            instance.setActiveAccount(accounts[0]);
        }
    }
});
```

### 6.4 NEO4J_USER vs NEO4J_USERNAME

**Síntoma:** El backend no arranca: `Missing required settings: NEO4J_USER`.

**Causa raíz:** `settings.py` define `NEO4J_USER: str`, pero el Container App tenía la variable como `NEO4J_USERNAME`. Pydantic Settings mapea variables de entorno por **nombre exacto**.

**Solución:** Agregar AMBAS variables al Container App, o renombrar a `NEO4J_USER`:
```yaml
- name: NEO4J_USER      # Requerida por settings.py
  value: neo4j
- name: NEO4J_USERNAME   # Usada por algunos scripts/servicios externos
  value: neo4j
```

### 6.5 Links rotos en el frontend (404 en /demo, /terms, /privacy)

**Síntoma:** Al hacer clic en enlaces de la landing page o login, el navegador navega a rutas que no existen.

**Causa raíz:** Los componentes tenían links a páginas que nunca se crearon (`/demo`, `/terms`, `/privacy`).

**Solución:** Cambiar a anchors o secciones existentes:
```tsx
// page.tsx — Landing
href="/demo"     →  href="#features"

// login/page.tsx
href="/terms"    →  href="/#"
href="/privacy"  →  href="/#"
```

### 6.6 Variables NEXT_PUBLIC_* no disponibles en producción

**Síntoma:** El frontend en Azure no se conecta al backend o no tiene las credenciales de Azure AD.

**Causa raíz:** Next.js solo incorpora variables `NEXT_PUBLIC_*` durante `npm run build`. Si las variables no estaban definidas al compilar, el build estático las bake como strings vacíos.

**Solución:** Inyectar las variables de entorno ANTES del build:
```powershell
$env:NEXT_PUBLIC_API_BASE_URL = "https://theogen-backend.gentlemoss-dcba183f.eastus.azurecontainerapps.io/api"
$env:NEXT_PUBLIC_AZURE_AD_TENANT_ID = "3e151d68-e5ed-4878-932d-251fe1b0eaf1"
$env:NEXT_PUBLIC_AZURE_AD_CLIENT_ID = "c6d2cf71-dcd2-4400-a8be-9eb8c16b1174"
npm run build
```

---

## 7. Scripts de Operación

| Script | Función | Cuándo usar |
|--------|---------|-------------|
| `deploy_backend.ps1` | Build en ACR + update Container App | Cambios en el backend |
| `deploy_frontend_fixed.ps1` | Build Next.js + upload a Blob Storage | Cambios en el frontend |
| `iniciar_todo.ps1` | Arranca backend + frontend localmente | Desarrollo diario |
| `actualizar_env.py` | Sincroniza claves Azure al `.env` local | Tras rotación de claves |
| `obtener_claves_azure.ps1` | Obtiene claves desde Azure | Tras rotación o re-creación |

---

## 8. Lista de Verificación Pre-Despliegue

### Backend
- [ ] `az login` activo con la suscripción correcta
- [ ] `az acr build` exitoso (verificar que termina sin error)
- [ ] YAML del Container App contiene TODAS las env vars (especialmente `AZURE_AD_TENANT_ID`, `AZURE_AD_CLIENT_ID`, `NEO4J_USER`)
- [ ] YAML del Container App tiene `minReplicas: 1` (evita cold starts)
- [ ] YAML solo tiene registros ACR que existen y son accesibles
- [ ] Tras create/update, `provisioningState` = `Succeeded`
- [ ] `GET /` devuelve 200
- [ ] `GET /api/projects/` sin token devuelve 401 (NO 500)
- [ ] Logs limpios: no hay errores de variables faltantes

### Frontend
- [ ] Variables `NEXT_PUBLIC_*` inyectadas en el entorno antes de `npm run build`
- [ ] `npm run build` genera carpeta `out/` sin errores
- [ ] `az storage blob upload-batch` sube todos los archivos a `$web`
- [ ] La URL principal responde 200
- [ ] Login con Microsoft funciona sin errores en consola
- [ ] Tras login, el dashboard carga datos del backend

### Entra ID
- [ ] URI de redirección tipo SPA (no Web) configurada para producción Y desarrollo
- [ ] Permisos `openid`, `profile`, `email` habilitados
- [ ] El `client_id` y `tenant_id` coinciden entre frontend y backend

---

## 9. URLs de Producción

| Componente | URL |
|-----------|-----|
| Frontend (App) | https://theogenfrontpllrx4ji.z13.web.core.windows.net/ |
| Backend (API Docs) | https://theogen-backend.gentlemoss-dcba183f.eastus.azurecontainerapps.io/docs |
| Backend (API base) | https://theogen-backend.gentlemoss-dcba183f.eastus.azurecontainerapps.io/api |
| Health Check | https://theogen-backend.gentlemoss-dcba183f.eastus.azurecontainerapps.io/health |

---

## 10. Comandos de Diagnóstico Rápido

```powershell
# Estado del Container App
az containerapp show --name theogen-backend --resource-group theogen-rg-eastus `
  --query "{state:properties.provisioningState, rev:properties.latestRevisionName, running:properties.runningStatus}" -o json

# Logs en tiempo real
az containerapp logs show --name theogen-backend --resource-group theogen-rg-eastus --tail 20 --type console

# Logs del sistema (errores de plataforma)
az containerapp logs show --name theogen-backend --resource-group theogen-rg-eastus --tail 20 --type system

# Revisiones activas
az containerapp revision list --name theogen-backend --resource-group theogen-rg-eastus `
  --query "[].{name:name, active:properties.active, replicas:properties.replicas, state:properties.runningState}" -o table

# Variables de entorno del contenedor
az containerapp show --name theogen-backend --resource-group theogen-rg-eastus `
  --query "properties.template.containers[0].env[].name" -o tsv

# Probar salud del backend
Invoke-WebRequest -Uri "https://theogen-backend.gentlemoss-dcba183f.eastus.azurecontainerapps.io/health" -UseBasicParsing
```

---

## 11. Lecciones Aprendidas (Resumen Ejecutivo)

| # | Lección | Impacto | Prevención |
|---|---------|---------|------------|
| 1 | Registros ACR obsoletos en Container App causan provisioning infinito | **Bloqueante** — no se puede actualizar ni crear revisiones | Limpiar registros ACR no usados; verificar `provisioningState` post-operación |
| 2 | Variables de entorno en el template no se aplican si la revisión falló | **Bloqueante** — backend devuelve 500 | Verificar con endpoint de prueba (401 vs 500); recrear si es necesario |
| 3 | `handleRedirectPromise()` duplicado con `MsalProvider` | Moderado — warnings en consola y posibles loops | Usar patrón de event callbacks, nunca llamar manualmente |
| 4 | `NEXT_PUBLIC_*` se bake en tiempo de build | **Bloqueante** — frontend no se conecta al backend | Inyectar vars ANTES de `npm run build` |
| 5 | `NEO4J_USER` vs `NEO4J_USERNAME` — Pydantic es exacto | **Bloqueante** — backend no arranca | Verificar nombres exactos en `settings.py` |
| 6 | UUID no canónico en claim `sub` de Azure AD | Medio — genera 500 al crear proyectos | Usar fallback `uuid5()` para claims no-UUID |
| 7 | Container App con `minReplicas: null` escala a 0 | Medio — cold starts de 30+ segundos | Establecer `minReplicas: 1` en producción |

---

*Documento generado el 20 de febrero de 2026. Mantener actualizado con cada cambio significativo en la infraestructura.*