# Guía: Integración Google Login (evolución: federation → Google Identity Services directo)

**Fecha:** 26-02-2026  
**Estado:** ✅ COMPLETADO — desplegado en producción (commit `45f726e`, rama `final`)  
**Objetivo:** Permitir login con `@gmail.com` / Google Workspace en TheoGen.  
**Arquitectura final:** Google Identity Services directo → `id_token` como Bearer → backend valida contra JWKS de Google.

---

## Historial de decisiones

### Enfoque inicial: Federación Google → Azure AD B2B (descartado)

El plan original era federar Google como proveedor externo en Azure AD External Identities, de modo que Azure AD emitiría el JWT final — sin cambios en backend. Se completaron las 5 fases (GCP client, Azure External Identities, User Flow, frontend `domainHint`).

**Problema:** `domainHint: "google.com"` y luego `domainHint: "gmail.com"` con autoridad específica del tenant no lograron evitar que Azure AD mostrara su propio selector de login antes de redirigir a Google. La experiencia resultante siempre pasaba por la pantalla de Microsoft. Conclusión: Azure AD B2B External Identities no garantiza skip del picker de Microsoft para IdPs externos sin Azure AD B2C (servicio separado de pago).

### Enfoque adoptado: Google Identity Services directo

Google Identity Services emite directamente un `id_token` JWT firmado. El frontend lo almacena en `localStorage` y lo envía como `Bearer`. El backend valida la firma contra el JWKS de Google (`googleapis.com/oauth2/v3/certs`), usando `GOOGLE_CLIENT_ID` como audience. El user identifier es `sub` (21 dígitos) → `UUIDv5(sub)` como `owner_id` (fallback ya existente en `auth.py`).

---

## Flujo final implementado

```
Usuario hace clic en botón "Continue with Google"
        ↓
GoogleLogin (@react-oauth/google) abre popup de Google nativo
        ↓
Google autentica → emite id_token JWT (iss: accounts.google.com)
        ↓
Frontend: setGoogleToken(credential) → localStorage
        ↓
router.replace("/dashboard/")
        ↓
api.ts getAccessToken() → detecta Google token en localStorage → retorna
        ↓
Peticiones API: Authorization: Bearer <google_id_token>
        ↓
auth.py: peek iss → "accounts.google.com" → Google path
        ↓
Fetch JWKS de googleapis.com/oauth2/v3/certs → valida firma + audience + issuer
        ↓
CurrentUser(oid=sub, email=...) → user_uuid = UUIDv5(sub)
```

---

## Fase 1 — Google Cloud Console ✅ COMPLETADO

**Proyecto GCP:** `helical-analyst-301321`  
**Cliente OAuth creado:** `Cliente web theogen`  
**Client ID:** `791433802772-l7sul60hr03kq7i2u7m32bd6jrn8lalo.apps.googleusercontent.com`

**URIs de redirección autorizados** (para flujo Azure AD B2B — conservados):
```
https://login.microsoftonline.com/te/3e151d68-e5ed-4878-932d-251fe1b0eaf1/oauth2/authresp
```

**Authorized JavaScript origins** (requeridos para Google Identity Services directo — agregados el 26-02-2026):
```
https://theogen.nubeweb.cl
http://localhost:3000
```

> ⚠️ **Pendiente de seguridad:** Rotar el Client Secret en GCP Console (crear nuevo, eliminar el expuesto). GCP → APIs y Servicios → Credenciales → editar cliente → Agregar secreto.

### Pasos ejecutados
1. Proyecto GCP existente (`helical-analyst-301321`) reutilizado.
2. Tipo de aplicación: **Aplicación web** (no App de escritorio).
3. Nombre: `Cliente web theogen`.
4. URI de redireccionamiento autorizado: callback fijo de Azure AD.
5. Pantalla de consentimiento: tipo **Externo**, estado **En producción**.

### 1.3 Configurar pantalla de consentimiento OAuth

1. **APIs y Servicios** → **Pantalla de consentimiento de OAuth**.
2. Tipo de usuario: **Externo** (para @gmail.com; si solo usas Google Workspace propio, elige Interno).
3. Rellena: nombre de app = `TheoGen`, email de soporte, logo (opcional).
4. Alcances: no es necesario agregar scopes específicos (Azure AD pedirá solo `openid email profile`).
5. Publica la app (estado: **En producción**) para que usuarios externos puedan autenticarse sin restricción.

---

## Fase 2 — Azure AD: Registrar Google como proveedor de identidad ✅ COMPLETADO

**Proveedor:** Google — estado **Configurado** en Microsoft Entra ID → External Identities → All identity providers.

### Pasos ejecutados
1. Portal Azure → **Microsoft Entra ID** → **External Identities** → **All identity providers** → **+ Google**.
2. Client ID y Client Secret del paso anterior ingresados.
3. Guardado. Estado resultante: `Google — Configurado`.

---

## Fase 3 — Habilitar acceso de autoservicio ✅ COMPLETADO

**Configuración aplicada** en External Identities → Configuración de colaboración externa:

| Parámetro | Valor configurado |
|---|---|
| Acceso de usuarios invitados | Los usuarios invitados tienen el mismo acceso que los miembros |
| Restricciones de invitación | Cualquier persona de la organización puede invitar |
| Registro de autoservicio mediante flujos de usuario | **Sí** |
| Permitir que usuarios externos se quiten | Sí |
| Restricciones de colaboración | Permitir invitaciones a cualquier dominio |

---

## Fase 4 — User Flow y asociación a la app ✅ COMPLETADO

**User Flow creado:** `B2X_1_theogen_signin`  
**Tipo:** Registrarse e iniciar sesión (recomendado)  
**Proveedores habilitados:** Google, Cuenta Microsoft  
**Atributos recopilados:** Nombre para mostrar  
**Aplicación asociada:** `axial-app` (ID `c6d2cf71-dcd2-4400-a8be-9eb8c16b1174`)

> Cuando un usuario de Google inicia sesión, Azure AD crea una cuenta de invitado con `oid` UUID real y emite un JWT con el mismo formato que siempre usa el backend.

---

## Fase 5 — Frontend: Botón "Continuar con Google" ✅ COMPLETADO (reemplazado)

> Las fases 1-4 (Azure AD federation) se mantienen en el tenant pero el frontend ya no usa ese flujo. El botón ahora usa Google Identity Services directo.

**Commit final:** `45f726e` — rama `final`  
**Archivos modificados:**

| Archivo | Cambio |
|---|---|
| `frontend/src/lib/googleAuth.ts` | **Nuevo** — utilidades `getGoogleToken/setGoogleToken/clearGoogleToken` con validación de expiración JWT |
| `frontend/src/app/login/page.tsx` | Reemplaza handler MSAL por componente `GoogleLogin` de `@react-oauth/google` |
| `frontend/src/app/dashboard/page.tsx` | Estado combinado `msalIsAuthenticated \|\| googleAuth`; `getGoogleToken()` en auth guard |
| `frontend/src/lib/api.ts` | `getAccessToken()` chequea Google token en localStorage antes de MSAL |
| `frontend/src/app/providers.tsx` | Agrega `GoogleOAuthProvider clientId={NEXT_PUBLIC_GOOGLE_CLIENT_ID}` |
| `frontend/src/lib/msalConfig.ts` | Elimina `googleLoginRequest` (ya no necesario) |
| `frontend/.env.local` | Agrega `NEXT_PUBLIC_GOOGLE_CLIENT_ID` |
| `frontend/production.env` | Agrega `NEXT_PUBLIC_GOOGLE_CLIENT_ID` |
| `deploy_frontend_fixed.ps1` | Inyecta `NEXT_PUBLIC_GOOGLE_CLIENT_ID` en build |
| `backend/app/core/auth.py` | Validación dual-provider: detecta `iss` → Google o Azure/MSA path |
| `backend/app/core/settings.py` | Nuevo campo `GOOGLE_CLIENT_ID: str = ""` |
| Container App `theogen-backend` | Env var `GOOGLE_CLIENT_ID` agregada; imagen `20260226214908` |

### Lógica clave en `auth.py`

```python
# Peek unverified iss claim para routing
unverified_claims = jwt.get_unverified_claims(token)
token_issuer = unverified_claims.get("iss", "")

if token_issuer == "https://accounts.google.com":
    # Google path: JWKS de googleapis.com, audience = GOOGLE_CLIENT_ID
    ...
else:
    # Azure/MSA path: lógica original sin cambios
    ...
```

### Identidad del usuario en Google path

- `oid` = `sub` del token Google (string de 21 dígitos)
- `user_uuid` = `UUIDv5(NAMESPACE_URL, "theogen-user:{sub}")` (fallback ya existente)
- Los proyectos creados con Google login tendrán `owner_id` = ese UUIDv5

---

## Verificación del flujo

1. Abrir `https://theogen.nubeweb.cl/login` en ventana incógnita.
2. Hacer clic en **Continue with Google** → debe aparecer popup de Google nativo (sin pasar por Microsoft).
3. Tras seleccionar cuenta → consola muestra `[Login] Google id_token received, storing and redirecting.`
4. Dashboard carga; las llamadas API incluyen el `id_token` como Bearer.
5. Backend log: `JWKS keys refreshed from Google` en primer request.

---

## Resumen de cambios ejecutados

| Componente | Cambio | Estado |
|---|---|---|
| Google Cloud Console — OAuth client | `Cliente web theogen` + redirect URI Azure | ✅ |
| Google Cloud Console — JS origins | `theogen.nubeweb.cl` + `localhost:3000` | ✅ |
| Azure AD External Identities | Google registrado como proveedor social | ✅ |
| Azure AD Colaboración externa | Autoservicio habilitado, invitaciones abiertas | ✅ |
| Azure AD User Flow | `B2X_1_theogen_signin` → Google + MSA → `axial-app` | ✅ (conservado) |
| `frontend/src/lib/googleAuth.ts` | Nuevo — utilidades localStorage para Google `id_token` | ✅ |
| `frontend/src/app/login/page.tsx` | `GoogleLogin` component (reemplaza MSAL domainHint) | ✅ |
| `frontend/src/app/dashboard/page.tsx` | Auth guard combinado MSAL + Google localStorage | ✅ |
| `frontend/src/lib/api.ts` | `getAccessToken()` prioriza Google token | ✅ |
| `frontend/src/app/providers.tsx` | `GoogleOAuthProvider` wrapper | ✅ |
| `frontend/src/lib/msalConfig.ts` | `googleLoginRequest` eliminado | ✅ |
| `frontend/package.json` | `@react-oauth/google` instalado | ✅ |
| `backend/app/core/auth.py` | Validación dual-provider (Azure/MSA + Google) | ✅ |
| `backend/app/core/settings.py` | `GOOGLE_CLIENT_ID` setting | ✅ |
| Container App `theogen-backend` | `GOOGLE_CLIENT_ID` env var + imagen `20260226214908` | ✅ |

## Pendiente de seguridad

- [ ] Rotar Client Secret de Google en GCP Console: **APIs y Servicios → Credenciales → Cliente web theogen → Agregar secreto → eliminar el anterior**.
