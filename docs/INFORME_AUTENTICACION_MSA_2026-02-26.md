# Diagnóstico y Solución: Autenticación con Cuentas Microsoft Personales (MSA)

**Fecha:** 26-02-2026  
**Proyecto:** TheoGen  
**Alcance:** Login con cuentas `@hotmail.com`, `@outlook.com`, `@live.com` (Personal Microsoft Accounts)

---

## 1. Contexto y flujo de autenticación

TheoGen usa **Azure Entra ID (Azure AD)** con la biblioteca MSAL (`@azure/msal-react`) para autenticar usuarios. El flujo es:

```
Usuario → loginRedirect (MSAL) → Microsoft Identity → token JWT → frontend
                                                               → Authorization: Bearer <token> → backend (FastAPI)
                                                               → validación JWT (auth.py) → acceso a recursos
```

El **App Registration** en Azure (`axial-app`, ID `c6d2cf71-...`) está configurado con:
- `signInAudience: AzureADandPersonalMicrosoftAccount` → admite cuentas organizacionales **y** personales.
- `SPA redirectURIs`: incluye `https://theogen.nubeweb.cl/login/` y `http://localhost:3000/login/`.

---

## 2. Problema encontrado (AADSTS50020)

Al intentar iniciar sesión con una cuenta personal (`@hotmail.com`, `@outlook.com` o `@live.com`), el flujo fallaba con el error:

> **AADSTS50020**: User account from identity provider 'live.com' does not exist in tenant 'Directorio predeterminado'

### Causa raíz — frontend

En `frontend/.env.local` estaba configurado:

```env
NEXT_PUBLIC_AZURE_AD_TENANT_ID=3e151d68-e5ed-4878-932d-251fe1b0eaf1
```

Esto hace que MSAL construya la `authority`:

```
https://login.microsoftonline.com/3e151d68-e5ed-4878-932d-251fe1b0eaf1
```

Este endpoint solo acepta cuentas del directorio organizacional. Cuando un usuario con cuenta `@hotmail.com` intenta autenticarse, Microsoft responde que esa cuenta no existe en dicho tenant.

### Causa raíz — backend

En `backend/app/core/auth.py` la validación del token solo aceptaba tokens con `issuer` del tenant organizacional:

```python
JWKS_URL = f"https://login.microsoftonline.com/{TENANT_ID}/discovery/v2.0/keys"
ISSUER_V1 = f"https://sts.windows.net/{TENANT_ID}/"
ISSUER_V2 = f"https://login.microsoftonline.com/{TENANT_ID}/v2.0"
# ← MSA issuer no incluido
```

Los tokens de cuentas personales Microsoft son emitidos por el **tenant de consumidores** (ID fijo `9188040d-6c67-4c5b-b112-36a304b66dad`):

```
issuer: https://login.microsoftonline.com/9188040d-6c67-4c5b-b112-36a304b66dad/v2.0
```

El backend rechazaba estos tokens con `JWTError: Invalid issuer`.

---

## 3. Solución aplicada

### 3.1 Frontend — `frontend/.env.local`

Cambio de `TENANT_ID` al alias `common`, que enruta tanto cuentas organizacionales como personales:

```env
# Antes
NEXT_PUBLIC_AZURE_AD_TENANT_ID=3e151d68-e5ed-4878-932d-251fe1b0eaf1

# Después — 'common' acepta org + personal Microsoft accounts
NEXT_PUBLIC_AZURE_AD_TENANT_ID=common
```

MSAL construirá ahora:

```
authority: https://login.microsoftonline.com/common
```

### 3.2 Backend — `backend/app/core/auth.py`

Dos cambios:

**a) JWKS endpoint cambiado a `common`** — para recuperar las claves de firma de ambos tipos de tenant:

```python
# Antes
JWKS_URL = f"https://login.microsoftonline.com/{TENANT_ID}/discovery/v2.0/keys"

# Después
JWKS_URL = "https://login.microsoftonline.com/common/discovery/v2.0/keys"
```

**b) Issuer MSA añadido al listado de issuers válidos:**

```python
# Nuevo
MSA_ISSUER_V2 = "https://login.microsoftonline.com/9188040d-6c67-4c5b-b112-36a304b66dad/v2.0"

# Validación jwt.decode — antes
issuer=[ISSUER_V1, ISSUER_V2]

# Validación jwt.decode — después
issuer=[ISSUER_V1, ISSUER_V2, MSA_ISSUER_V2]
```

---

## 4. Archivos modificados

| Archivo | Cambio |
|---|---|
| `frontend/.env.local` | `NEXT_PUBLIC_AZURE_AD_TENANT_ID` de tenant ID fijo → `common` |
| `backend/app/core/auth.py` | `JWKS_URL` a endpoint `common`; added `MSA_ISSUER_V2` en lista de issuers |

---

## 5. Despliegue

Tras los cambios se ejecutó redeploy completo:

| Componente | Acción | Resultado |
|---|---|---|
| Backend | `az acr build` → tag `20260226172921` → `az containerapp update` | `Succeeded`, 39 envs intactos |
| Frontend | `next build` (mode `output: export`) → `az storage blob upload-batch` a `$web` | 84 archivos subidos |

Commit de referencia en rama `final`:
```
fix(auth): support personal Microsoft accounts (MSA) - use common JWKS + MSA issuer
```

---

## 6. Consideraciones de seguridad

- El `audience` del JWT sigue siendo `CLIENT_ID` (el App Registration) → los tokens de otras apps son rechazados.
- El `oid` del token MSA es único por aplicación (no entre apps), suficiente para aislar datos de usuario en la base de datos.
- El tenant `9188040d-6c67-4c5b-b112-36a304b66dad` es el identificador **fijo y público** del tenant de consumidores de Microsoft, no un secreto.
- JWKS se cachea 1 hora; rotación de keys se maneja automáticamente con reintento en caso de `kid` no encontrado.

---

## 7. Cómo verificar

1. Abre [https://theogen.nubeweb.cl/login/](https://theogen.nubeweb.cl/login/).
2. Haz clic en **"Iniciar sesión con Microsoft"**.
3. Inicia sesión con una cuenta `@hotmail.com`, `@outlook.com` o `@live.com`.
4. Deberías ser redirigido al dashboard sin error AADSTS50020.

Para validar el token localmente:

```bash
# Obtén un token con MSAL y verifica el issuer:
python -c "
import base64, json
token = '<pega el JWT aquí>'
payload = token.split('.')[1] + '=='
print(json.loads(base64.b64decode(payload)))
"
# Busca el campo 'iss' — debe ser uno de los issuers aceptados
```

---

## 8. Extensión: Federación Google (completado 26-02-2026)

Tras resolver el problema MSA, se implementó login con cuentas `@gmail.com` y Google Workspace mediante **federación Google → Azure AD** (sin ningún cambio en el backend).

### Arquitectura

```
Usuario → "Continuar con Google" (MSAL domainHint: "google.com")
        → Azure AD detecta domainHint, redirige a accounts.google.com
        → Google autentica → OAuth code devuelto a Azure AD
        → Azure AD crea cuenta de invitado (oid UUID real) y emite JWT
        → mismo flujo Bearer → auth.py → validación idéntica
```

### Componentes configurados

| Componente | Detalle |
|---|---|
| GCP OAuth client | `Cliente web theogen`, proyecto `helical-analyst-301321` |
| Redirect URI registrado | `https://login.microsoftonline.com/te/3e151d68-.../oauth2/authresp` |
| Azure AD External Identities | Google registrado como proveedor social |
| Azure AD User Flow | `B2X_1_theogen_signin` — proveedores: Google + Cuenta Microsoft |
| App asociada al User Flow | `axial-app` |

### Cambios en código (commit `1bbc511`)

**`frontend/src/lib/msalConfig.ts`** — nuevo export:
```typescript
export const googleLoginRequest = {
    scopes: ["openid", "profile", "email"],
    domainHint: "google.com",
};
```

**`frontend/src/app/login/page.tsx`** — nuevo handler y botón "Continuar con Google" con logo SVG.

### Por qué el backend no cambia

El token que llega al backend es emitido por Azure AD (no por Google directamente):
- `iss`: `https://login.microsoftonline.com/3e151d68-.../v2.0` — ya aceptado
- `oid`: UUID real asignado por Azure AD al usuario invitado
- `aud`: `c6d2cf71-...` — mismo Client ID de siempre

> Guía completa de implementación: [GUIA_GOOGLE_FEDERATION_AZURE_AD.md](./GUIA_GOOGLE_FEDERATION_AZURE_AD.md)

### Pendiente de seguridad
- [ ] Rotar el Client Secret de Google en GCP Console (el original fue expuesto durante la configuración).

