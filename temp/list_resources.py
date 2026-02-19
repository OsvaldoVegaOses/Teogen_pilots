import subprocess
import json

try:
    # Obtener Container Apps
    apps_raw = subprocess.check_output(["az", "containerapp", "list", "-g", "theogen-rg-eastus", "-o", "json"], text=True)
    apps = json.loads(apps_raw)
    
    # Obtener ACR
    acr_raw = subprocess.check_output(["az", "acr", "list", "-g", "theogen-rg-eastus", "-o", "json"], text=True)
    acrs = json.loads(acr_raw)
    
    print("--- Container Apps ---")
    for app in apps:
        print(f"Name: {app['name']}")
        print(f"FQDN: {app['properties']['configuration']['ingress']['fqdn']}")
        print(f"Ingress Target Port: {app['properties']['configuration']['ingress']['targetPort']}")
        try:
            print(f"Image: {app['properties']['template']['containers'][0]['image']}")
        except:
            print("Image info not found")
        print("-" * 20)
        
    print("\n--- Container Registries ---")
    for acr in acrs:
        print(f"Name: {acr['name']}")
        print(f"Server: {acr['loginServer']}")
        
except Exception as e:
    print(f"Error: {e}")
