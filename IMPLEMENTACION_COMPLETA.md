# Implementación Completa de TheoGen

Este documento detalla todos los pasos necesarios para completar la implementación de TheoGen con los recursos ya desplegados en Azure.

## 1. Configuración del Backend

### Instalar dependencias
```bash
cd backend
pip install -r requirements.txt
```

### Configurar variables de entorno
Ya tienes el archivo `.env` configurado con los valores correctos. Asegúrate de que todas las claves provisionales estén actualizadas:

- `AZURE_STORAGE_KEY`: Tu clave real de almacenamiento
- `AZURE_AD_CLIENT_ID`: Tu ID de cliente de Azure AD
- `AZURE_SPEECH_KEY`: Tu clave de Azure Speech
- `AZURE_REDIS_KEY`: Tu clave de Azure Redis

### Inicializar la base de datos
```bash
python init_db.py
```

## 2. Configuración del Frontend

### Instalar dependencias
```bash
cd frontend
npm install
```

### Configurar variables de entorno para el frontend
Crea un archivo `.env.local` en el directorio frontend con las siguientes variables:
```
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api
NEXT_PUBLIC_AZURE_AD_TENANT_ID=3e151d68-e5ed-4878-932d-251fe1b0eaf1
```

## 3. Iniciar la aplicación

### Backend
```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

### Frontend (en otra terminal)
```bash
cd frontend
npm run dev
```

## 4. Configuración de Azure AD (Microsoft Entra ID)

Debes completar manualmente la configuración de Entra ID en Azure Portal:

1. Ve a Azure Portal > Microsoft Entra ID > Registros de aplicaciones
2. Registra una nueva aplicación:
   - Nombre: `theogen-app`
   - Tipo de cuenta: "Cuentas en cualquier directorio organizacional (por ejemplo, Azure AD) y cuentas Microsoft personales"
   - URI de redirección: `http://localhost:3000/api/auth/callback` (para desarrollo)

3. Copia el Application (client) ID y actualiza la variable `AZURE_AD_CLIENT_ID` en tu archivo `.env`

4. En la configuración de la aplicación, activa "Autenticación silenciosa" y agrega los permisos necesarios para los recursos de Azure.

## 5. Verificación de recursos desplegados

Todos los recursos siguientes ya están desplegados según tu archivo .env:

- ✅ Azure OpenAI Service (endpoint: axial-resource.cognitiveservices.azure.com)
- ✅ Azure PostgreSQL Flexible Server
- ✅ Azure Cache for Redis
- ✅ Azure Storage Account
- ⚠️ Azure AD (requiere configuración manual)
- ✅ Neo4j Database (externa gestionada)
- ✅ QDrant Vector Database (externa gestionada)

## 6. Probar la aplicación

1. Accede a `http://localhost:3000` en tu navegador
2. Verifica que puedes:
   - Subir archivos de audio o video
   - Transcribirlos usando el modelo gpt-4o-transcribe-diarize
   - Generar teoría usando los modelos disponibles
   - Crear códigos y categorías axiales
   - Exportar resultados

## 7. Solución de problemas comunes

### Error de conexión a PostgreSQL
- Verifica que el firewall de PostgreSQL permita conexiones desde tu IP
- Asegúrate de que el nombre de host, usuario y contraseña sean correctos

### Error de autenticación OpenAI
- Confirma que la clave API y el endpoint sean correctos
- Verifica que los modelos estén correctamente desplegados y disponibles

### Error de almacenamiento
- Asegúrate de que la clave de almacenamiento sea correcta
- Verifica que los contenedores necesarios existan (audio, documents, exports)

## 8. Pasos finales

Una vez que todo esté funcionando correctamente:

1. Documenta cualquier ajuste específico que hayas realizado
2. Considera crear un script de despliegue automatizado para futuras implementaciones
3. Realiza pruebas de extremo a extremo para asegurar la funcionalidad completa