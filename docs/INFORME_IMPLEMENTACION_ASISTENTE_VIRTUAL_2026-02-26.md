# Informe de Implementacion: Asistente Virtual TheoGen

Fecha: 26-02-2026  
Proyecto: TheoGen  
Alcance: Chatbot para visitantes (landing) + chatbot tecnico para usuarios logeados, con seguridad de no exposicion de codigo/datos internos y persistencia en base dedicada del asistente.

## 1. Objetivo cumplido

Se implemento un modulo de asistente virtual en dos modos:

1. Publico (landing): accesible a potenciales usuarios para resolver dudas de plataforma/contacto y capturar leads.
2. Autenticado (dashboard): ayuda tecnica de uso para el caso de uso de la plataforma.

En ambos modos se aplicaron guardrails para bloquear solicitudes sensibles (codigo fuente, secretos, credenciales y datos internos del proyecto).

## 2. Arquitectura implementada

### 2.1 Frontend

1. Widget flotante en landing para visitantes.
2. Widget flotante en dashboard para usuarios autenticados.
3. Integracion con backend via endpoints dedicados:
   - Publico: `publicApiClient(...)`
   - Autenticado: `apiClient(...)` con token Bearer.

### 2.2 Backend

Router nuevo de asistente en `/api/assistant` con endpoints:

1. `POST /api/assistant/public/chat`
2. `POST /api/assistant/authenticated/chat`
3. `POST /api/assistant/public/lead`
4. `GET /api/assistant/authenticated/metrics`

### 2.3 Persistencia

Se implemento una conexion separada para el asistente:

1. Opcion A: `ASSISTANT_DATABASE_URL` (recomendada).
2. Opcion B: reutilizar host/user/pass y cambiar DB con `ASSISTANT_PG_DATABASE`.

Si no hay DB de asistente configurada, el chat sigue operativo y omite logging/persistencia.

### 2.4 Integracion con LLM existente

No se creo una conexion nueva para el asistente.  
Se reutiliza la conexion Azure OpenAI / Foundry ya existente del backend.

Se agregaron deployments configurables separados para el asistente:

1. `MODEL_ASSISTANT_PUBLIC`
2. `MODEL_ASSISTANT_AUTHENTICATED`

Esto permite desacoplar el consumo del asistente respecto de otros flujos del sistema sin duplicar la integracion tecnica.

## 3. Seguridad y politicas aplicadas

Bloqueo explicito de consultas sobre:

1. Codigo fuente / repositorios.
2. Credenciales, tokens, passwords, secrets, `.env`.
3. Datos internos de proyecto / base de datos interna / connection strings.

Respuesta controlada: el asistente redirige a informacion publica o soporte funcional sin exponer datos sensibles.

## 4. Base de datos dedicada del asistente

### 4.1 Tablas creadas (create_all)

1. `assistant_message_logs`
   - sesion, modo, mensaje usuario, respuesta, intent, blocked, user_id opcional, metadata cliente.
2. `assistant_contact_leads`
   - sesion, datos de contacto, consentimiento, modo origen, user_id opcional, metadata cliente.

### 4.2 Modo de inicializacion

`ensure_assistant_schema()` crea esquema en primer uso.  
Nota: para madurez productiva, se recomienda migracion Alembic formal.

## 5. Flujos implementados

### 5.1 Landing (visitante)

1. Chat publico responde sobre:
   - que es TheoGen,
   - flujo de uso,
   - segmentos/industrias,
   - contacto comercial.
2. Formulario de lead embebido:
   - nombre, email, empresa (opcional), consentimiento.
3. Registro de interacciones y leads si DB de asistente esta habilitada.
4. Modo hibrido `rules-first + LLM fallback`:
   - primero intenta responder con reglas + KB publica,
   - si no encuentra respuesta especifica y no es una consulta sensible, usa LLM,
   - maximo 4 disparos LLM por sesion publica.

### 5.2 Dashboard (usuario logeado)

1. Chat tecnico autenticado responde sobre:
   - codificacion abierta/axial/selectiva,
   - trazabilidad de teoria por claim,
   - operacion de entrevistas/transcripcion,
   - exportaciones y troubleshooting funcional.
2. Visualizacion de metricas 7d en cabecera del widget:
   - mensajes totales,
   - mensajes bloqueados,
   - leads capturados.
3. Modo LLM autenticado:
   - usa el mismo recurso Azure OpenAI existente,
   - aplica prompt estricto de seguridad,
   - si falla el modelo, cae a respuesta determinista segura.
4. Personalizacion de sesion:
   - nombre visible editable,
   - organizacion o cargo editable,
   - avatar con iniciales en cabecera.
5. Cierre de sesion:
   - boton dedicado en dashboard,
   - limpieza de cache local del navegador,
   - limpieza de storage de MSAL / Google / estado UI de la app.

### 5.3 Perfil de sesion

Se implemento un perfil de sesion con dos modos de persistencia:

1. Microsoft:
   - sincroniza con backend mediante `GET /api/profile/me` y `PATCH /api/profile/me`
   - persiste en tabla `user_profiles`
2. Google:
   - usa persistencia local en navegador como fallback

El objetivo es que el usuario no dependa solo del email de autenticacion para personalizar su experiencia.

## 6. Archivos creados/modificados

### Backend

1. `backend/app/api/assistant.py` (nuevo)
2. `backend/app/assistant_database.py` (nuevo)
3. `backend/app/models/assistant_models.py` (nuevo)
4. `backend/app/schemas/assistant.py` (nuevo)
5. `backend/app/services/assistant_knowledge.py` (nuevo)
6. `backend/app/services/assistant_llm_service.py` (nuevo)
7. `backend/app/data/assistant_knowledge_v1.json` (nuevo)
8. `backend/app/services/azure_openai.py` (modificado)
9. `backend/app/api/profile.py` (nuevo)
10. `backend/app/schemas/profile.py` (nuevo)
11. `backend/app/core/settings.py` (modificado)
12. `backend/app/main.py` (modificado)

### Frontend

1. `frontend/src/components/marketing/LandingChatbot.tsx` (nuevo)
2. `frontend/src/components/assistant/AuthenticatedChatbot.tsx` (nuevo)
3. `frontend/src/lib/api.ts` (modificado)
4. `frontend/src/app/page.tsx` (modificado: integracion widget landing + contacto empresarial)
5. `frontend/src/app/dashboard/page.tsx` (modificado: integracion widget tecnico + perfil + logout)
6. `frontend/src/lib/sessionProfile.ts` (nuevo)

## 7. Variables de entorno relevantes

1. `ASSISTANT_DATABASE_URL` (opcional, preferente)
2. `ASSISTANT_PG_DATABASE` (default: `theogen_assistant`)
3. `AZURE_PG_HOST`, `AZURE_PG_USER`, `AZURE_PG_PASSWORD` (si no se usa URL completa)
4. `MODEL_ASSISTANT_PUBLIC`
5. `MODEL_ASSISTANT_AUTHENTICATED`

## 8. Validaciones ejecutadas

1. Frontend: `npm run build` -> OK
2. Backend: `python -m compileall backend/app` -> OK

## 9. Mejoras posteriores implementadas

Despues de la primera entrega se agregaron estas mejoras:

1. Base de conocimiento versionada externa en:
   - `backend/app/data/assistant_knowledge_v1.json`
2. Servicio lector de conocimiento:
   - `backend/app/services/assistant_knowledge.py`
3. Rate limit basico en endpoints publicos:
   - chat publico: ventana 5 min, max 20 requests por IP/sesion
   - lead publico: ventana 60 min, max 5 requests por IP/sesion
4. Entorno Alembic separado para la DB del asistente:
   - `backend/alembic_assistant.ini`
   - `backend/alembic_assistant/env.py`
   - `backend/alembic_assistant/versions/20260227_0001_create_assistant_tables.py`
5. Integracion con LLM existente del sistema:
   - servicio del asistente: `backend/app/services/assistant_llm_service.py`
   - reutiliza `backend/app/services/azure_openai.py`
6. Fallback LLM restringido para landing publica:
   - solo si reglas no resuelven,
   - maximo 4 disparos por sesion.
7. Perfil persistido para usuarios Microsoft:
   - tabla `user_profiles`
   - endpoint `/api/profile/me`
8. Cierre de sesion con limpieza de cache local:
   - tokens,
   - estado UI,
   - storage de autenticacion y tareas locales.

### 9.1 Comando recomendado de migracion para la DB del asistente

Desde `backend/`:

```powershell
alembic -c alembic_assistant.ini upgrade head
```

Esto requiere que la configuracion de DB del asistente este disponible por:

1. `ASSISTANT_DATABASE_URL`
2. o `AZURE_PG_HOST` + `AZURE_PG_USER` + `AZURE_PG_PASSWORD` + `ASSISTANT_PG_DATABASE`

## 10. Limitaciones actuales

1. Inicializacion de esquema por `create_all` (sin versionado de migraciones).
2. No usa RAG documental ni recuperacion sobre fuentes privadas; la inteligencia actual se apoya en KB publica/autenticada + LLM controlado.
3. No incluye aun filtros avanzados, exportacion ni paginacion para operaciones del asistente.
4. La persistencia remota del perfil hoy cubre Microsoft; Google sigue con persistencia local en navegador.

Nota: la limitacion 1 quedo parcialmente mitigada con el nuevo entorno Alembic separado para la base del asistente. El `create_all` sigue presente como fallback operativo.
Nota: la limitacion 2 reemplaza la version previa del documento; ya no es correcto decir que el asistente opera solo con respuestas deterministas.

## 11. Recomendaciones siguientes

1. Formalizar migraciones Alembic para tablas del asistente.
2. Agregar rate-limit por IP/sesion para endpoint publico.
3. Implementar panel interno de operaciones del asistente (filtros por fecha/intencion/blocked/leads).
4. Versionar base de conocimiento (FAQ/KB) separada del codigo.

Las recomendaciones 1, 2 y 4 ya quedaron implementadas en esta fase. Tambien se implemento un panel interno basico de operaciones del asistente en dashboard.

### 11.1 Panel interno implementado

Se agrego una pestana `Assistant Ops` en dashboard con:

1. mensajes recientes del asistente,
2. leads recientes,
3. visibilidad de `blocked`,
4. modo de origen (`public`, `authenticated`, `authenticated_public`).

Archivos:

1. `frontend/src/components/assistant/AssistantOpsPanel.tsx`
2. `backend/app/api/assistant.py` (`GET /api/assistant/authenticated/ops`)
3. `backend/app/schemas/assistant.py`

### 11.2 Integracion LLM implementada

Se implemento integracion con el LLM ya usado por TheoGen sin crear otra conexion:

1. Servicio base reutilizado:
   - `backend/app/services/azure_openai.py`
2. Servicio especifico del asistente:
   - `backend/app/services/assistant_llm_service.py`

#### Modo autenticado

1. Usa `MODEL_ASSISTANT_AUTHENTICATED`
2. Prompt estricto con guardrails
3. Fallback a respuesta determinista si el modelo falla

#### Modo publico

1. Usa `MODEL_ASSISTANT_PUBLIC`
2. Solo como fallback cuando no hay respuesta clara en reglas
3. Maximo 4 disparos LLM por sesion
4. Guardrails previos al modelo para consultas sensibles

### 11.3 Perfil y cierre de sesion implementados

Se agrego soporte para identidad de sesion mas util en dashboard:

1. avatar con iniciales,
2. nombre visible editable,
3. organizacion/cargo editable,
4. persistencia remota en backend para Microsoft,
5. persistencia local para Google,
6. boton de cierre de sesion con limpieza de cache.

Backend:

1. `backend/app/api/profile.py`
2. `backend/app/schemas/profile.py`
3. `backend/app/models/models.py` (`user_profiles`)
4. `backend/alembic/versions/20260227_0003_add_user_profiles_table.py`

Frontend:

1. `frontend/src/lib/sessionProfile.ts`
2. `frontend/src/app/dashboard/page.tsx`

## 12. Estado final

Implementacion funcional completada para:

1. Chatbot visitante en landing.
2. Chatbot tecnico autenticado en dashboard.
3. Registro en DB dedicada del asistente (cuando esta configurada).
4. Politica de seguridad para evitar exposicion de codigo y datos internos.
5. Integracion con el LLM existente del sistema usando deployments separados para el asistente.
6. Modo hibrido publico restringido con limite de 4 fallbacks LLM por sesion.
7. Perfil de sesion personalizable con avatar e identidad visible en dashboard.
8. Cierre de sesion con limpieza de cache local del navegador.

Pendientes a ejecutar 

 Además de la BD del asistente, faltan tareas de infraestructura y operación  
  que no puedo cerrar desde el código local: crear/configurar la base          
  theogen_assistant y ejecutar su migración (alembic -c alembic_assistant.ini  
  upgrade head), definir en .env los deployments reales MODEL_ASSISTANT_PUBLIC 
  y MODEL_ASSISTANT_AUTHENTICATED, validar que el recurso Azure OpenAI tenga   
  capacidad/cuota suficiente para esos deployments, desplegar backend/frontend 
  con esas variables activas, y decidir si el contador de 4 fallback públicos  
  por sesión seguirá en memoria o se moverá a un almacenamiento distribuido    
  (Redis/DB) para entornos con múltiples réplicas. También queda pendiente la  
  validación operativa en ambiente real: probar extremo a extremo el chat      
  público, el chat autenticado, el registro de leads y el panel Assistant Ops  
  con datos reales de despliegue, porque eso requiere acceso al entorno        
  desplegado, credenciales activas y confirmación de infraestructura que yo no 
  puedo ejecutar automáticamente desde aquí.    
