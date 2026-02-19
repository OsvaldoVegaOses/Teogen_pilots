import subprocess
import json
import sys

print("Verificando URIs de redireccion en Azure AD...")
try:
    result = subprocess.run(
        ["az", "ad", "app", "show", "--id", "c6d2cf71-dcd2-4400-a8be-9eb8c16b1174", "--query", "spa.redirectUris", "-o", "json"],
        capture_output=True, text=True, shell=True
    )
    uris = json.loads(result.stdout)
    login_uris = [u for u in uris if u.endswith("/login/")]
    
    if login_uris:
        print(f"✅ Correcto: Se encontraron {len(login_uris)} URIs de login.")
        for u in login_uris:
            print(f"   - {u}")
    else:
        print("❌ Error: No se encontraron URIs terminadas en /login/. Esto debe corregirse antes de desplegar.")
        # Aquí podriamos intentar corregirlo nuevamente si falla
        sys.exit(1)

except Exception as e:
    print(f"Error al verificar URIs: {e}")
    sys.exit(1)

print("\nObteniendo clave de almacenamiento...")
try:
    # Obtener nombre de la cuenta (buscamos la que empieza con theogenfront...)
    cmd_name = ["az", "storage", "account", "list", "--resource-group", "theogen-rg-eastus", "--query", "[?starts_with(name, 'theogenfront')].name", "-o", "tsv"]
    account_name = subprocess.check_output(cmd_name, shell=True, text=True).strip().split('\n')[0]
    
    if not account_name:
        print("❌ No se encontró la cuenta de almacenamiento.")
        sys.exit(1)
        
    print(f"Cuenta encontrada: {account_name}")
    
    # Obtener clave
    cmd_key = ["az", "storage", "account", "keys", "list", "--account-name", account_name, "--resource-group", "theogen-rg-eastus", "--query", "[0].value", "-o", "tsv"]
    account_key = subprocess.check_output(cmd_key, shell=True, text=True).strip()
    
    if not account_key:
        print("❌ No se pudo obtener la clave.")
        sys.exit(1)

    print("✅ Clave obtenida correctamente.")

    # Subir archivos
    print(f"\nSubiendo archivos desde 'frontend/out' a '{account_name}/$web'...")
    # Usamos shell=True y construimos el comando string para evitar problemas de argumentos en Windows
    upload_cmd = f'az storage blob upload-batch --account-name {account_name} --account-key {account_key} --destination "$web" --source "frontend/out" --overwrite'
    
    upload_result = subprocess.run(upload_cmd, shell=True, capture_output=True, text=True)
    
    if upload_result.returncode == 0:
        print("\n✅ Despliegue completado exitosamente!")
        
        # Obtener URL
        cmd_url = f"az storage account show --name {account_name} --resource-group theogen-rg-eastus --query primaryEndpoints.web -o tsv"
        try:
            url = subprocess.check_output(cmd_url, shell=True, text=True).strip()
            print(f"\n🌍 URL del Frontend: {url}")
            print(f"👉 Login URL: {url}login/")
        except Exception as e:
            print(f"Error al obtener URL: {e}")
            
    else:
        print("❌ Error en la subida:")
        # Imprimir stdout y stderr para ver qué pasó
        print(upload_result.stdout)
        print(upload_result.stderr)
        sys.exit(1)

except Exception as e:
    print(f"Error durante el despliegue: {e}")
    sys.exit(1)
