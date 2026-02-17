import os
import re
from dotenv import load_dotenv

def actualizar_archivo_env():
    """
    Script para actualizar el archivo .env con valores reales obtenidos de Azure
    """
    print("🔄 Actualizando archivo .env con valores reales")
    
    # Cargar el archivo .env actual
    env_path = '.env'
    if not os.path.exists(env_path):
        print("❌ El archivo .env no existe en el directorio actual")
        return False
    
    with open(env_path, 'r', encoding='utf-8') as file:
        content = file.read()
    
    print("🔍 Identificando valores provisionales en .env...")
    
    # Valores provisionales a reemplazar
    placeholders = {
        'AZURE_STORAGE_KEY': '<tu-clave-storage>',
        'AZURE_AD_CLIENT_ID': '<tu-client-id>',
        'AZURE_SPEECH_KEY': '<tu-clave-speech>',
        'AZURE_REDIS_KEY': '<tu-clave-redis>'
    }
    
    # Mostrar qué valores necesitan actualización
    for key, placeholder in placeholders.items():
        if placeholder in content:
            print(f"  - {key}: Necesita actualización")
        else:
            print(f"  - {key}: Ya está actualizado")
    
    print("\n📝 Sigue las instrucciones del script 'obtener_claves_azure.ps1' para obtener los valores reales")
    print("   Luego regresa aquí para actualizar el archivo .env con esos valores")
    
    # Pedir al usuario los valores reales
    valores_reales = {}
    for key, placeholder in placeholders.items():
        if placeholder in content:
            print(f"\nIngresa el valor real para {key}:")
            valor_real = input().strip()
            
            if valor_real:
                valores_reales[key] = valor_real
                print(f"  ✓ Valor para {key} registrado")
            else:
                print(f"  ⚠ No se proporcionó valor para {key}, se mantendrá el valor actual")
    
    # Actualizar el contenido con los nuevos valores
    updated_content = content
    for key, valor_real in valores_reales.items():
        # Patrón para encontrar la línea con la variable
        pattern = rf'^({key}=).*?$'
        updated_content = re.sub(pattern, f'{key}={valor_real}', updated_content, flags=re.MULTILINE)
    
    # Escribir el archivo actualizado
    with open(env_path, 'w', encoding='utf-8') as file:
        file.write(updated_content)
    
    print(f"\n✅ Archivo .env actualizado exitosamente")
    
    # Mostrar resumen
    print("\n📋 Resumen de actualización:")
    for key in valores_reales.keys():
        print(f"  - {key}: Actualizado")
    
    return True

def validar_configuracion():
    """
    Validar que la configuración en .env sea coherente
    """
    print("\n🔍 Validando configuración en .env...")
    
    load_dotenv('.env')
    
    # Variables importantes que deben estar presentes
    required_vars = [
        'AZURE_OPENAI_API_KEY',
        'AZURE_OPENAI_ENDPOINT',
        'AZURE_PG_HOST',
        'AZURE_PG_USER',
        'AZURE_PG_PASSWORD',
        'AZURE_PG_DATABASE',
        'AZURE_STORAGE_ACCOUNT',
        'AZURE_STORAGE_KEY',
        'AZURE_AD_TENANT_ID',
        'AZURE_AD_CLIENT_ID',
        'AZURE_SPEECH_KEY',
        'AZURE_SPEECH_REGION',
        'AZURE_REDIS_HOST',
        'AZURE_REDIS_KEY',
        'NEO4J_URI',
        'NEO4J_USERNAME',
        'NEO4J_PASSWORD',
        'QDRANT_URL',
        'QDRANT_API_KEY'
    ]
    
    missing_vars = []
    for var in required_vars:
        value = os.getenv(var)
        if not value or value.startswith('<') and value.endswith('>'):
            missing_vars.append(var)
    
    if missing_vars:
        print("❌ Variables faltantes o incompletas:")
        for var in missing_vars:
            print(f"  - {var}")
        return False
    else:
        print("✅ Todas las variables requeridas están presentes y completas")
        return True

def main():
    print("🚀 Proceso de actualización de configuración de TheoGen")
    print("="*60)
    
    # Actualizar el archivo .env
    success = actualizar_archivo_env()
    
    if success:
        # Validar la configuración
        print("\n" + "="*60)
        validar_configuracion()
        
        print("\n💡 Para completar la configuración de TheoGen:")
        print("   1. Asegúrate de tener todos los recursos de Azure creados")
        print("   2. Verifica que las claves ingresadas sean correctas")
        print("   3. Ejecuta 'python verificar_recursos.py' para comprobar la conectividad")
        print("   4. Ejecuta 'iniciar_theogen.ps1' para iniciar la aplicación")
        
        print("\n🎉 ¡Configuración completada exitosamente!")

if __name__ == "__main__":
    main()