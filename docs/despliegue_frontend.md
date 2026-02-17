# Despliegue del Frontend de TheoGen en Azure

## Descripción

Este documento describe el proceso para desplegar el frontend de TheoGen (aplicación Next.js) en Azure utilizando almacenamiento estático y CDN para distribución global.

## Arquitectura

El frontend se despliega como una aplicación web estática en Azure Storage Account con las siguientes características:

- **Azure Storage Account**: Hospeda los archivos estáticos del frontend
- **Azure CDN**: Proporciona distribución global y aceleración de contenido
- **Dominio personalizado**: Opcionalmente se puede configurar un dominio personalizado

## Recursos de Azure Desplegados

### Storage Account
- SKU: Standard_LRS
- Kind: StorageV2
- Hosting web estático: Habilitado
- Documento índice: index.html
- Documento de error 404: 404.html

### CDN Profile y Endpoint
- SKU: Standard_Microsoft
- Origen: Storage Account
- Compresión: Habilitada para tipos de contenido comunes
- Caché: Configuración para ignorar cadenas de consulta

## Proceso de Despliegue

### Prerrequisitos
1. Azure CLI instalado y configurado
2. Sesion activa en Azure (`az login`)
3. Node.js y npm instalados
4. Acceso a la suscripción de Azure

### Pasos

1. **Compilación local**:
   - Instalar dependencias: `npm install`
   - Compilar para producción: `npm run build`
   - El comando `npm run build` generará una carpeta `out` con los archivos estáticos

2. **Despliegue de infraestructura**:
   - Crear grupo de recursos (si no existe)
   - Desplegar Storage Account con hosting web estático
   - Configurar CDN Profile y Endpoint

3. **Publicación de contenido**:
   - Subir archivos estáticos desde la carpeta `out` al contenedor `$web` del Storage Account

4. **Configuración**:
   - Actualizar variables de entorno para apuntar al backend correcto

## Configuración del Backend

El frontend debe estar configurado para comunicarse con el backend de TheoGen. Las variables de entorno importantes son:

- `NEXT_PUBLIC_API_BASE_URL`: URL del backend de TheoGen (ej. `https://theogen-backend.azurewebsites.net/api`)

## Scripts Disponibles

- `deploy_frontend.ps1`: Script principal para desplegar el frontend en Azure
- `production.env`: Archivo de ejemplo con variables de entorno para producción

## Consideraciones de Seguridad

- El frontend es una aplicación estática, por lo que no almacena credenciales sensibles
- Todas las comunicaciones con el backend deben hacerse a través de HTTPS
- Se recomienda usar CORS correctamente configurado en el backend

## Monitoreo y Mantenimiento

- Los archivos se pueden actualizar simplemente reemplazando los archivos en el Storage Account
- Azure CDN puede requerir invalidación de caché para ver cambios inmediatos
- Se pueden usar herramientas de Azure para monitorear el tráfico y rendimiento

## Costos Estimados

- Storage Account: Basado en almacenamiento usado y operaciones
- Azure CDN: Basado en volumen de datos transferidos
- Total estimado: Menos de $10/mes para uso típico de desarrollo

## Solución de Problemas

### Problemas comunes:
1. **Archivos no se actualizan**: Limpiar caché de CDN
2. **Errores 404**: Verificar que los archivos estén en el contenedor `$web`
3. **Problemas de CORS**: Asegurarse de que el backend tenga CORS correctamente configurado

### Verificación:
- Verificar que `index.html` esté en la raíz del contenedor `$web`
- Confirmar que el dominio del CDN responda correctamente
- Probar la comunicación con el backend

## Personalización

Para personalizar el despliegue:

1. Modificar `infra/modules/frontend.bicep` para cambiar configuraciones
2. Actualizar variables en el archivo de entorno según sea necesario
3. Ajustar `next.config.ts` para requerimientos específicos de despliegue