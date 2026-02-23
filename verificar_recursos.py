import os
import sys
from dotenv import load_dotenv
import psycopg2
from azure.storage.blob import BlobServiceClient
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient
import redis
import requests
import time

# Cargar variables de entorno
load_dotenv()

def verificar_conexion_postgresql():
    """Verifica la conexión a PostgreSQL"""
    print("🔍 Verificando conexión a PostgreSQL...")
    try:
        conn = psycopg2.connect(
            host=os.getenv('AZURE_PG_HOST'),
            database=os.getenv('AZURE_PG_DATABASE'),
            user=os.getenv('AZURE_PG_USER'),
            password=os.getenv('AZURE_PG_PASSWORD')
        )
        cursor = conn.cursor()
        cursor.execute('SELECT version();')
        version = cursor.fetchone()
        print(f"✅ Conexión a PostgreSQL exitosa. Versión: {version[0]}")
        conn.close()
        return True
    except Exception as e:
        print(f"❌ Error en la conexión a PostgreSQL: {str(e)}")
        return False

def verificar_conexion_redis():
    """Verifica la conexión a Redis"""
    print("🔍 Verificando conexión a Redis...")
    try:
        r = redis.Redis(
            host=os.getenv('AZURE_REDIS_HOST'),
            port=6380,
            password=os.getenv('AZURE_REDIS_KEY'),
            ssl=True
        )
        r.ping()
        print("✅ Conexión a Redis exitosa")
        return True
    except Exception as e:
        print(f"❌ Error en la conexión a Redis: {str(e)}")
        return False

def verificar_conexion_storage():
    """Verifica la conexión a Azure Storage"""
    print("🔍 Verificando conexión a Azure Storage...")
    try:
        connection_string = f"DefaultEndpointsProtocol=https;AccountName={os.getenv('AZURE_STORAGE_ACCOUNT')};AccountKey={os.getenv('AZURE_STORAGE_KEY')};EndpointSuffix=core.windows.net"
        blob_service_client = BlobServiceClient.from_connection_string(connection_string)
        
        # Intentar listar contenedores para verificar la conexión
        containers = list(blob_service_client.list_containers())
        print(f"✅ Conexión a Azure Storage exitosa. Contenedores encontrados: {len(containers)}")
        return True
    except Exception as e:
        print(f"❌ Error en la conexión a Azure Storage: {str(e)}")
        return False

def verificar_conexion_openai():
    """Verifica la conexión a Azure OpenAI"""
    print("🔍 Verificando conexión a Azure OpenAI...")
    try:
        endpoint = os.getenv('AZURE_OPENAI_ENDPOINT')
        api_key = os.getenv('AZURE_OPENAI_API_KEY')
        api_version = os.getenv('AZURE_OPENAI_API_VERSION')
        
        headers = {
            'api-key': api_key,
            'Content-Type': 'application/json'
        }
        
        url = f"{endpoint.rstrip('/')}/openai/models?api-version={api_version}"
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            models = response.json().get('data', [])
            model_names = [model['id'] for model in models]
            print(f"✅ Conexión a Azure OpenAI exitosa. Modelos disponibles: {len(model_names)}")
            print(f"   Modelos: {', '.join(model_names[:5])}{'...' if len(model_names) > 5 else ''}")
            return True
        else:
            print(f"❌ Error en la conexión a Azure OpenAI: Status {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Error en la conexión a Azure OpenAI: {str(e)}")
        return False

def verificar_neo4j():
    """Verifica la conexión a Neo4j"""
    print("🔍 Verificando conexión a Neo4j...")
    try:
        from neo4j import GraphDatabase
        
        uri = os.getenv('NEO4J_URI')
        user = os.getenv('NEO4J_USERNAME')
        password = os.getenv('NEO4J_PASSWORD')
        database = os.getenv('NEO4J_DATABASE')
        
        driver = GraphDatabase.driver(uri, auth=(user, password))
        with driver.session(database=database) as session:
            result = session.run("RETURN 1 AS test")
            record = result.single()
            if record and record["test"] == 1:
                print("✅ Conexión a Neo4j exitosa")
                driver.close()
                return True
            else:
                print("❌ Error en la conexión a Neo4j: No se pudo ejecutar la consulta de prueba")
                driver.close()
                return False
    except ImportError:
        print("⚠️  Neo4j driver no instalado. Ejecuta: pip install neo4j")
        return False
    except Exception as e:
        print(f"❌ Error en la conexión a Neo4j: {str(e)}")
        return False

def verificar_qdrant():
    """Verifica la conexión a Qdrant"""
    print("🔍 Verificando conexión a Qdrant...")
    try:
        from qdrant_client import QdrantClient
        
        url = os.getenv('QDRANT_URL')
        api_key = os.getenv('QDRANT_API_KEY')
        
        client = QdrantClient(url=url, api_key=api_key, timeout=10)
        
        # Intentar obtener información del cluster
        cluster_info = client.get_collection_aliases()
        print("✅ Conexión a Qdrant exitosa")
        return True
    except ImportError:
        print("⚠️  Qdrant client no instalado. Ejecuta: pip install qdrant-client")
        return False
    except Exception as e:
        print(f"❌ Error en la conexión a Qdrant: {str(e)}")
        return False

def main():
    print("🚀 Verificación de recursos de TheoGen")
    print("="*50)
    
    resultados = []
    
    # Verificar cada recurso
    resultados.append(("PostgreSQL", verificar_conexion_postgresql()))
    resultados.append(("Redis", verificar_conexion_redis()))
    resultados.append(("Storage", verificar_conexion_storage()))
    resultados.append(("OpenAI", verificar_conexion_openai()))
    resultados.append(("Neo4j", verificar_neo4j()))
    resultados.append(("Qdrant", verificar_qdrant()))
    
    print("\n" + "="*50)
    print("📋 Resultado de la verificación:")
    
    exito_total = True
    for nombre, exito in resultados:
        estado = "✅" if exito else "❌"
        print(f"{estado} {nombre}")
        if not exito:
            exito_total = False
    
    print("\n" + "="*50)
    if exito_total:
        print("🎉 ¡Todos los recursos están accesibles!")
        print("Puedes proceder con la ejecución de TheoGen.")
    else:
        print("⚠️  Algunos recursos no están accesibles.")
        print("Por favor, verifica la configuración e inténtalo de nuevo.")
    
    return exito_total

if __name__ == "__main__":
    main()