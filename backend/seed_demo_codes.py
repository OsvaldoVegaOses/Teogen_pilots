import asyncio
from app.database import AsyncSessionLocal
from app.models.models import Code, Project, Fragment, code_fragment_links
from sqlalchemy import select, insert
import uuid

async def seed_codes():
    async with AsyncSessionLocal() as db:
        try:
            # 1. Get the project
            project_id = uuid.UUID("123e4567-e89b-12d3-a456-426614174000")
            
            # 2. Create some codes
            codes_data = [
                {
                    "label": "Capital Social Comunitario",
                    "definition": "Nivel de confianza y cooperación entre vecinos de San Felipe.",
                    "code_type": "open",
                    "created_by": "ai"
                },
                {
                    "label": "Resiliencia Territorial",
                    "definition": "Capacidad de adaptación frente a crisis ambientales o sociales.",
                    "code_type": "axial",
                    "created_by": "ai"
                },
                {
                    "label": "Autogestión de Espacios",
                    "definition": "Iniciativas propias para el mantenimiento de plazas y sedes.",
                    "code_type": "open",
                    "created_by": "human"
                }
            ]
            
            for cdata in codes_data:
                # Check if exists
                res = await db.execute(select(Code).filter(Code.label == cdata["label"], Code.project_id == project_id))
                if not res.scalar_one_or_none():
                    new_code = Code(
                        project_id = project_id,
                        label = cdata["label"],
                        definition = cdata["definition"],
                        code_type = cdata["code_type"],
                        created_by = cdata["created_by"]
                    )
                    db.add(new_code)
            
            await db.commit()
            print("✅ Codes seeded successfully for San Felipe.")

        except Exception as e:
            print(f"ERROR: {e}")

if __name__ == "__main__":
    asyncio.run(seed_codes())
