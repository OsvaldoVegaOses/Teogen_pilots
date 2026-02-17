# Plan de Despliegue para TheoGen en Azure

## Resumen
Este documento describe el plan detallado para desplegar la infraestructura de TheoGen en Microsoft Azure, incluyendo todos los recursos necesarios para operar la plataforma de análisis teórico cualitativo.

## Requisitos Previos
- CLI de Azure instalado y configurado
- Cuenta de Azure con permisos suficientes para crear recursos
- Acceso a suscripción de Azure
- Powershell 7 o superior (si se usa Windows)

## Componentes de Infraestructura

### 1. Recursos Principales
- Grupo de recursos: `theogen-rg` (ubicación: West Europe)
- Microsoft Foundry Hub: Espacio de trabajo de Azure Machine Learning
- Azure OpenAI: Con modelos específicos (gpt-5.2-chat, Kimi-K2.5, DeepSeek-V3.2-Speciale, etc.)
- PostgreSQL Flexible Server: Base de datos con acceso privado y copias de seguridad
- Azure Cache for Redis: Con SKU Standard y copias de seguridad
- Cuenta de Almacenamiento: Para audio, documentos y exportaciones
- Servicio de Speech: Para transcripciones y procesamiento de voz
- Aplicación registrada en Microsoft Entra ID: Para autenticación

### 2. Configuración de Seguridad
- PostgreSQL con acceso público deshabilitado
- Copias de seguridad geográficas habilitadas para PostgreSQL
- Redis con copias de seguridad periódicas
- Política de red restrictiva para recursos

## Proceso de Despliegue

### Paso 1: Preparación del Entorno
```bash
# Iniciar sesión en Azure
az login

# Establecer la suscripción
az account set --subscription <your-subscription-id>
```

### Paso 2: Ejecutar el Despliegue
```bash
# Navegar al directorio de infraestructura
cd infra/

# Ejecutar el script de despliegue
pwsh -ExecutionPolicy Bypass -File ./deploy.ps1
```

### Paso 3: Validación del Despliegue
- Verificar que todos los recursos se hayan creado correctamente
- Confirmar que los endpoints estén accesibles
- Validar la configuración de seguridad

## Archivos de Despliegue
- `main.bicep`: Archivo principal de infraestructura
- `modules/foundry.bicep`: Módulo para Foundry Hub
- `modules/openai.bicep`: Módulo para Azure OpenAI
- `modules/postgres.bicep`: Módulo para PostgreSQL
- `modules/storage.bicep`: Módulo para almacenamiento
- `modules/entra.bicep`: Módulo para Microsoft Entra ID
- `deploy.ps1`: Script de despliegue PowerShell

## Configuración Post-Despliegue
1. Actualizar el archivo `.env` con los valores de salida del despliegue
2. Configurar la aplicación backend con los endpoints correctos
3. Verificar la conectividad a todos los servicios

## Consideraciones de Costo
- Los recursos seleccionados están configurados para un equilibrio entre rendimiento y costo
- Monitorear el uso de los servicios de IA para controlar costos
- Considerar la posibilidad de usar planes dedicados para producción

## Riesgos y Mitigaciones
- Riesgo: Fallo en el despliegue de Entra ID
  - Mitigación: El script de despliegue incluye pasos manuales alternativos si es necesario
- Riesgo: Cuotas de suscripción insuficientes
  - Mitigación: Verificar cuotas antes del despliegue completo
- Riesgo: Configuración incorrecta de redes
  - Mitigación: Validar configuración de firewall y red después del despliegue