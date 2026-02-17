from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import projects, theory, interviews, codes, memos
from app.core.settings import settings

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="TheoGen - Grounded Theory AI Generator",
    version="0.1.0",
)

# CORS context
origins = [settings.FRONTEND_URL] if settings.FRONTEND_URL else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(projects.router, prefix="/api")
app.include_router(theory.router, prefix="/api")
app.include_router(interviews.router, prefix="/api")
app.include_router(codes.router, prefix="/api")
app.include_router(memos.router, prefix="/api")

@app.get("/")
async def root():
    return {"message": "Welcome to TheoGen API"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
