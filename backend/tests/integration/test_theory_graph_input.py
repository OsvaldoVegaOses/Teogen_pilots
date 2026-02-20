from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
import uuid

from fastapi.testclient import TestClient

from app.core.auth import CurrentUser, get_current_user
from app.database import get_db
from app.main import app


class _ScalarOneResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _ScalarsResult:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return self

    def all(self):
        return self._values


def test_generate_theory_populates_network_metrics_summary(monkeypatch):
    project_id = uuid.uuid4()
    user = CurrentUser(oid=str(uuid.uuid4()), email="test@example.com", name="Tester")

    project = SimpleNamespace(id=project_id, owner_id=user.user_uuid, name="Proyecto", language="es")
    cat_1 = SimpleNamespace(id=uuid.uuid4(), name="Categoria A", definition="Def A")
    cat_2 = SimpleNamespace(id=uuid.uuid4(), name="Categoria B", definition="Def B")
    code = SimpleNamespace(id=uuid.uuid4(), category_id=cat_1.id)

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(side_effect=[
        _ScalarOneResult(project),           # select(Project)
        _ScalarsResult([cat_1, cat_2]),      # select(Category)
        _ScalarsResult([code]),              # select(Code)
    ])
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()

    async def _refresh(obj):
        obj.id = uuid.uuid4()
        obj.created_at = datetime.utcnow()
        obj.version = 1

    mock_db.refresh = AsyncMock(side_effect=_refresh)

    async def override_get_current_user():
        return user

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_db] = override_get_db

    async def _noop(*args, **kwargs):
        return None

    async def _network_metrics(*args, **kwargs):
        return {
            "counts": {"category_count": 2, "code_count": 1, "fragment_count": 3},
            "category_centrality": [
                {"category_id": str(cat_1.id), "category_name": cat_1.name, "code_degree": 1, "fragment_degree": 2},
                {"category_id": str(cat_2.id), "category_name": cat_2.name, "code_degree": 0, "fragment_degree": 1},
            ],
            "category_cooccurrence": [
                {"category_a_id": str(cat_1.id), "category_b_id": str(cat_2.id), "shared_fragments": 1}
            ],
        }

    async def _embeddings(*args, **kwargs):
        return [[0.1, 0.2, 0.3]]

    async def _semantic_hits(*args, **kwargs):
        return [{"fragment_id": str(uuid.uuid4()), "score": 0.87, "text": "fragmento de evidencia", "codes": ["C1"]}]

    async def _identify(*args, **kwargs):
        return {"selected_central_category": "Categoria A"}

    async def _build(*args, **kwargs):
        return {"selected_central_category": "Categoria A", "propositions": [], "confidence_score": 0.82}

    async def _gaps(*args, **kwargs):
        return {"identified_gaps": []}

    monkeypatch.setattr("app.api.theory.neo4j_service.ensure_project_node", _noop)
    monkeypatch.setattr("app.api.theory.neo4j_service.create_category_node", _noop)
    monkeypatch.setattr("app.api.theory.neo4j_service.link_code_to_category", _noop)
    monkeypatch.setattr("app.api.theory.neo4j_service.get_project_network_metrics", _network_metrics)
    monkeypatch.setattr("app.api.theory.foundry_openai.generate_embeddings", _embeddings)
    monkeypatch.setattr("app.api.theory.qdrant_service.search_supporting_fragments", _semantic_hits)
    monkeypatch.setattr("app.api.theory.theory_engine.identify_central_category", _identify)
    monkeypatch.setattr("app.api.theory.theory_engine.build_straussian_paradigm", _build)
    monkeypatch.setattr("app.api.theory.theory_engine.analyze_saturation_and_gaps", _gaps)

    with TestClient(app) as client:
        response = client.post(
            f"/api/projects/{project_id}/generate-theory",
            json={"min_interviews": 1, "use_model_router": True},
        )

    app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    summary = data["validation"]["network_metrics_summary"]
    assert summary["counts"]["category_count"] == 2
    assert len(summary["category_centrality_top"]) > 0
    assert len(summary["semantic_evidence_top"]) > 0
