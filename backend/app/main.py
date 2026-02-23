# TheoGen API - Deployment Trigger
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import projects, theory, interviews, codes, memos, search
from app.core.settings import settings
from app.services.neo4j_service import neo4j_service
from app.services.qdrant_service import qdrant_service

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="TheoGen - Grounded Theory AI Generator",
    version="0.1.0",
)

# CORS context
# Define allowed origins specifically, avoiding "*" in production if possible
origins = [
    settings.FRONTEND_URL,
    "http://localhost:3000",
    "https://theogenfrontwpdxe2pv.z13.web.core.windows.net",
    "https://theogenfrontpllrx4ji.z13.web.core.windows.net", # URL actual del usuario
    "https://theogen-app.whitepebble-c2a4715b.eastus.azurecontainerapps.io",
    "https://theogen-backend.gentlemoss-dcba183f.eastus.azurecontainerapps.io"
]
# Clean up empty strings or duplicates
origins = list(set([o for o in origins if o]))

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=r"https://.*\.z13\.web\.core\.windows\.net",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(projects.router, prefix="/api")
app.include_router(interviews.router, prefix="/api")
app.include_router(codes.router, prefix="/api")
app.include_router(memos.router, prefix="/api")
app.include_router(theory.router, prefix="/api")
app.include_router(search.router, prefix="/api")

@app.on_event("startup")
async def startup_checks():
    if settings.TESTING:
        return

    required_env = {
        "NEO4J_URI": settings.NEO4J_URI,
        "NEO4J_USER": settings.NEO4J_USER,
        "NEO4J_PASSWORD": settings.NEO4J_PASSWORD,
        "QDRANT_URL": settings.QDRANT_URL,
    }
    missing = [name for name, value in required_env.items() if not value]
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")

    neo4j_ok = await neo4j_service.verify_connectivity()
    if not neo4j_ok:
        raise RuntimeError("Neo4j connectivity check failed during startup")

    qdrant_ok = await qdrant_service.verify_connectivity()
    if not qdrant_ok:
        raise RuntimeError("Qdrant connectivity check failed during startup")

@app.get("/")
async def root():
    return {"message": "Welcome to TheoGen API", "auth": "enabled"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
