import httpx
import os
import asyncio
from pathlib import Path

async def upload_audio(file_path: str, project_id: str):
    url = f"http://localhost:8000/api/interviews/upload?project_id={project_id}"
    path = Path(file_path)
    
    async with httpx.AsyncClient(timeout=300.0) as client:
        print(f"🚀 Subiendo: {path.name}...")
        files = {"file": (path.name, open(path, "rb"), "audio/mpeg")}
        data = {"participant_pseudonym": path.stem}
        
        try:
            response = await client.post(url, files=files, data=data)
            if response.status_code == 200:
                print(f"✅ Éxito: {path.name} subido correctamente.")
                return response.json()
            else:
                print(f"❌ Error {response.status_code}: {response.text}")
        except Exception as e:
            print(f"❌ Error de conexión: {e}")

async def create_project(project_id: str):
    url = f"http://localhost:8000/api/projects/"
    async with httpx.AsyncClient() as client:
        # Check if project exists or just try to create (the API I wrote handles this or we can just try)
        # Assuming the API for projects is simple (label/description)
        # Based on previous implementation plan: @router.post("/")
        payload = {
            "id": project_id,
            "name": "PAC San Felipe - Actores Comunitarios",
            "description": "Análisis de entrevistas a actores comunitarios en San Felipe."
        }
        try:
            res = await client.post(url, json=payload)
            if res.status_code in [200, 201]:
                print("✅ Proyecto creado/listo.")
            else:
                print(f"⚠️ Aviso Proyecto: {res.text}")
        except Exception:
            pass

async def main():
    project_id = "123e4567-e89b-12d3-a456-426614174000" 
    await create_project(project_id)
    audio_dir = Path(r"C:\Users\osval\OneDrive - ONG Tren Ciudadano\Escritorio\PAC San Felipe\audios\Actores comunitarios\Audios_Actores_Comunitarios")
    
    # Get all audio files (m4a, mp3, wav, etc.)
    audio_files = list(audio_dir.rglob("*.m4a")) + list(audio_dir.rglob("*.mp3")) + list(audio_dir.rglob("*.wav"))
    
    if not audio_files:
        print("No se encontraron archivos de audio en temp_audio.")
        return

    # Process first 2 files for testing
    for audio_file in audio_files[:2]:
        await upload_audio(str(audio_file), project_id)

if __name__ == "__main__":
    asyncio.run(main())
