# TheoGen API - Deployment Trigger
import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from time import perf_counter

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from app.api import projects, theory, interviews, codes, memos, search, assistant, profile
from app.core.settings import settings
from app.services.neo4j_service import neo4j_service
from app.services.qdrant_service import qdrant_service

# Uvicorn's default logging config often only shows access logs; ensure app logs are visible.
_level_name = (os.getenv("APP_LOG_LEVEL") or "INFO").upper()
_level = getattr(logging, _level_name, logging.INFO)
logging.getLogger().setLevel(_level)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    if settings.TESTING:
        yield
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

    try:
        yield
    finally:
        # Shutdown: best-effort close of services that support it
        try:
            close = getattr(neo4j_service, "close", None)
            if close:
                await close()
        except Exception:
            logging.exception("Error closing neo4j_service during shutdown")
        try:
            close_q = getattr(qdrant_service, "close", None)
            if close_q:
                await close_q()
        except Exception:
            logging.exception("Error closing qdrant_service during shutdown")


app = FastAPI(
    title=settings.PROJECT_NAME,
    description="TheoGen - Grounded Theory AI Generator",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS context
# Endurecido: solo lista explícita, sin regex abierto
origins = [
    settings.FRONTEND_URL,
    "https://theogen.nubeweb.cl",
    "https://theogenfrontwpdxe2pv.z13.web.core.windows.net",
    "https://theogenfrontpllrx4ji.z13.web.core.windows.net",
    "https://theogen-app.whitepebble-c2a4715b.eastus.azurecontainerapps.io",
    "https://theogen-backend.gentlemoss-dcba183f.eastus.azurecontainerapps.io"
]
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
app.include_router(assistant.router, prefix="/api")
app.include_router(profile.router, prefix="/api")

# (startup checks and shutdown cleanup handled by `lifespan`)

@app.get("/")
async def root():
    return {"message": "Welcome to TheoGen API", "auth": "enabled"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}


def _dependency_error_code(exc: Exception) -> str:
    if isinstance(exc, asyncio.TimeoutError):
        return "TIMEOUT"
    name = exc.__class__.__name__.upper() if exc.__class__.__name__ else "ERROR"
    return name[:60]


@app.get("/health/dependencies")
async def health_dependencies(x_health_key: str | None = Header(default=None, alias="X-Health-Key")):
    expected_key = (settings.HEALTHCHECK_DEPENDENCIES_KEY or "").strip()
    if expected_key and x_health_key != expected_key:
        raise HTTPException(status_code=401, detail="Unauthorized")

    timeout_s = max(1, int(settings.HEALTHCHECK_TIMEOUT_SECONDS))
    payload = {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "dependencies": {
            "neo4j": {
                "enabled": bool(getattr(neo4j_service, "enabled", False)),
                "ok": False,
                "latency_ms": None,
                "error_code": None,
            },
            "qdrant": {
                "enabled": bool(getattr(qdrant_service, "enabled", False)),
                "ok": False,
                "latency_ms": None,
                "error_code": None,
            },
        },
    }

    async def _check(name: str, fn):
        if not payload["dependencies"][name]["enabled"]:
            payload["dependencies"][name]["ok"] = False
            return
        started = perf_counter()
        try:
            ok = await asyncio.wait_for(fn(), timeout=timeout_s)
            payload["dependencies"][name]["ok"] = bool(ok)
        except Exception as e:
            payload["dependencies"][name]["ok"] = False
            payload["dependencies"][name]["error_code"] = _dependency_error_code(e)
        payload["dependencies"][name]["latency_ms"] = round((perf_counter() - started) * 1000.0, 2)

    await _check("neo4j", neo4j_service.verify_connectivity)
    await _check("qdrant", qdrant_service.verify_connectivity)

    neo4j_enabled = payload["dependencies"]["neo4j"]["enabled"]
    qdrant_enabled = payload["dependencies"]["qdrant"]["enabled"]
    neo4j_ok = payload["dependencies"]["neo4j"]["ok"]
    qdrant_ok = payload["dependencies"]["qdrant"]["ok"]
    if (neo4j_enabled and not neo4j_ok) or (qdrant_enabled and not qdrant_ok):
        payload["status"] = "degraded"
    return payload

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
