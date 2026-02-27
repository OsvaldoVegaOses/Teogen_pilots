# Informe Continuacion Prueba UX/UI TheoGen

Fecha: 2026-02-27  
Canal: revision tecnica del frontend (code-assisted QA)  
Rol objetivo: usuario nuevo en movil (investigacion cualitativa)

## 0) Estado de implementacion (misma fecha)

Implementado en frontend:

1. Correcciones de texto:
   - `Navegación` en menu movil.
   - `Sociólogo` en footer.
   - Footer unificado a español.
2. Menu movil:
   - overlay mas oscuro y con mayor `z-index` para bloquear mejor la interaccion de fondo.
3. Hero:
   - agregado texto explicativo para `INSIGHTS SYNC`.
4. Asistente virtual landing:
   - boton flotante reducido en movil para minimizar superposicion.
   - panel con mas alto util para respuestas largas.
   - render de markdown simple (`**negrita**`).
   - mensajes de validacion de nombre/email en español.
   - chips sugeridos se ocultan al ser usados.
5. Login / Signup:
   - Signup ahora soporta Google (consistente con login).
   - enlaces superiores actualizados a anclas existentes del landing.

## 1) Resultado de continuacion

Tu evaluacion funcional es consistente con el codigo actual en la mayoria de los puntos.

Hallazgos confirmados por evidencia de implementacion:

1. Error ortografico en menu movil: `Navegacion` sin tilde.
2. Footer con `Sociologo` sin tilde.
3. Footer con mezcla de idioma y simbolo de copyright corrupto.
4. Componente `INSIGHTS SYNC` sin texto explicativo adicional.
5. Inconsistencia login/signup: login ofrece Microsoft + Google, signup solo Microsoft.
6. Chat landing no renderiza markdown (muestra texto plano).
7. Boton flotante del asistente anclado fijo en movil, susceptible a superposicion.

## 2) Evidencia tecnica por hallazgo

## Tipografia e idioma

- `Navegacion`:
  - `frontend/src/app/page.tsx:169`
- `Sociologo`:
  - `frontend/src/app/page.tsx:349`
- Footer mixto ES/EN + simbolo corrupto:
  - `frontend/src/app/page.tsx:353`

## Hero / claridad

- `INSIGHTS SYNC` presente sin descripcion contextual:
  - `frontend/src/app/page.tsx:225`

## Menu movil / overlay

- Overlay existe y cubre pantalla, pero con `z-40`:
  - `frontend/src/app/page.tsx:122`
- Header usa `z-50`:
  - `frontend/src/app/page.tsx:126`

Implicancia: partes del header pueden quedar por encima del overlay y seguir siendo interactuables.

## Login / signup inconsistente

- Login incluye Google:
  - `frontend/src/app/login/page.tsx:146`
- Signup solo Microsoft:
  - `frontend/src/app/signup/page.tsx:76`

## Asistente virtual landing

- Boton flotante fijo:
  - `frontend/src/components/marketing/LandingChatbot.tsx:194`
- Input de chat libre:
  - `frontend/src/components/marketing/LandingChatbot.tsx:283`
- Mensajes se renderizan como texto plano (sin markdown parser):
  - `frontend/src/components/marketing/LandingChatbot.tsx:222`
- Chips siempre visibles:
  - `frontend/src/components/marketing/LandingChatbot.tsx:12`

## 3) Bugs criticos reportados por ti: estado de verificacion tecnica

### A) Chat libre no envia

Estado: `pendiente reproduccion funcional directa`  
Observacion tecnica: el flujo de envio existe (`onSubmit -> askAssistant`) y no hay bloqueo evidente en la logica.  
Siguiente verificacion recomendada:

1. Probar en movil real (Chrome Android + Safari iOS) con teclado abierto.
2. Probar con DevTools Network si se dispara `POST /assistant/public/chat`.
3. Verificar si algun submit/validacion del formulario de contacto interfiere en UX movil.

### B) Formulario contacto se limpia al fallar validacion de consentimiento

Estado: `no reproducible por lectura de codigo`  
Observacion tecnica: en `!leadConsent` se hace `return` temprano y no hay reset de campos (`setLeadName/setLeadEmail/...` solo ocurren cuando `payload.created`).  
Siguiente verificacion recomendada:

1. Reproducir paso a paso en movil real con captura de consola.
2. Confirmar si el “limpiado” coincide con remount del componente (cerrar/abrir chat, reload, navegacion).

## 4) Hallazgos adicionales de continuacion

1. En login, nav superior apunta a anclas no existentes en landing (`#features`, `#methodology`, `#pricing`):
   - `frontend/src/app/login/page.tsx:103-105`
   - Landing usa `#valor`, `#como-funciona`, `#para-quien`, `#industrias`.
2. Hay texto con mojibake/encoding en varios labels (ej. `EducaciÃ³n`, `CÃ³mo`, `Â¿...`), afectando calidad percibida.

## 5) Priorizacion actualizada (UX/UI + conversion)

## Alta

1. Chat libre no envia (si se confirma en reproduccion).
2. Formulario contacto pierde datos al validar (si se confirma).
3. Superposicion del boton flotante en movil.
4. Inconsistencia de metodos de autenticacion login vs signup.
5. Falta de claridad de “Probar gratis” (alcance/pricing) para conversion.

## Media

1. Overlay menu vs z-index header.
2. `INSIGHTS SYNC` sin descripcion.
3. Markdown sin render en respuestas.
4. Mensajeria de validacion en ingles.
5. Seccion “Para quien” sin interactividad contextual.

## Baja

1. Tildes y consistencia de idioma en footer/menu.
2. Chips sin estado de “usado”.

## 6) Proximo paso de prueba recomendado

Ejecutar un mini ciclo de reproduccion en movil real (15-20 min) con captura de red y consola para cerrar definitivamente los 2 bugs criticos del chatbot (envio libre + persistencia de campos en validacion).
