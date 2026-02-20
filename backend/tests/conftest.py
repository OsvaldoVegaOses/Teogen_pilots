import os
import sys
from pathlib import Path


# Ensure required settings are present for test imports/startup.
os.environ.setdefault("TESTING", "true")
os.environ.setdefault("NEO4J_URI", "bolt://localhost:7687")
os.environ.setdefault("NEO4J_USER", "neo4j")
os.environ.setdefault("NEO4J_PASSWORD", "test-password")
os.environ.setdefault("QDRANT_URL", "http://localhost:6333")

# Ensure `app` package is importable when running tests from repo root.
backend_dir = Path(__file__).resolve().parents[1]
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))
