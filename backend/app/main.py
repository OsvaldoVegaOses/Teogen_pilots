# TheoGen API - Deployment Trigger
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import projects, theory, interviews, codes, memos, search
from app.core.settings import settings

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

@app.get("/")
async def root():
    return {"message": "Welcome to TheoGen API", "auth": "enabled"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
