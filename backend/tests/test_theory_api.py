import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.auth import get_current_user, CurrentUser
from app.database import get_db
from unittest.mock import MagicMock, AsyncMock
from datetime import datetime, timezone
import uuid

# Mock User
mock_user_uuid = uuid.uuid4()
mock_user = CurrentUser(oid=str(mock_user_uuid), email="test@example.com", name="Test User")

# Dependency Overrides
async def override_get_current_user():
    return mock_user

async def override_get_db():
    db = AsyncMock()
    yield db

@pytest.fixture
def client():
    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()

def test_export_theory_not_found(client):
    """Test export when theory doesn't exist or user doesn't own it."""
    project_id = uuid.uuid4()
    theory_id = uuid.uuid4()
    
    # Mock DB response to return None (no row found)
    mock_db = MagicMock()
    mock_db.execute = AsyncMock(return_value=MagicMock(first=MagicMock(return_value=None)))
    app.dependency_overrides[get_db] = lambda: mock_db
    
    response = client.post(f"/api/projects/{project_id}/theories/{theory_id}/export")
    assert response.status_code == 404
    assert response.json()["detail"] == "Theory or Project not found"

@pytest.mark.asyncio
async def test_export_theory_success_logic(client, monkeypatch):
    """
    Test the successful logic path (mocking services).
    Note: We monkeypatch the services used in the endpoint.
    """
    project_id = uuid.uuid4()
    theory_id = uuid.uuid4()
    
    # 1. Mock Database
    mock_theory = MagicMock()
    mock_theory.id = theory_id
    mock_theory.version = 1
    mock_theory.confidence_score = 0.9
    mock_theory.generated_by = "AI"
    mock_theory.model_json = {}
    mock_theory.propositions = []
    mock_theory.gaps = []
    
    mock_project = MagicMock()
    mock_project.id = project_id
    mock_project.name = "Test Project"
    mock_project.language = "es"
    
    mock_db = MagicMock()
    mock_db.execute = AsyncMock(return_value=MagicMock(first=MagicMock(return_value=(mock_theory, mock_project))))
    app.dependency_overrides[get_db] = lambda: mock_db

    # 2. Mock Services
    mock_pdf = MagicMock()
    mock_pdf.getvalue.return_value = b"%PDF-mock-content"
    
    async def mock_gen_pdf(*args, **kwargs):
        return mock_pdf
        
    async def mock_upload(*args, **kwargs):
        return "https://azure.com/blob"
        
    async def mock_sas(*args, **kwargs):
        return "https://azure.com/blob?sas=123"

    monkeypatch.setattr("app.services.export_service.export_service.generate_theory_pdf", mock_gen_pdf)
    monkeypatch.setattr("app.services.storage_service.storage_service.upload_blob", mock_upload)
    monkeypatch.setattr("app.services.storage_service.storage_service.generate_sas_url", mock_sas)

    response = client.post(f"/api/projects/{project_id}/theories/{theory_id}/export")
    
    assert response.status_code == 200
    data = response.json()
    assert "download_url" in data
    assert data["download_url"] == "https://azure.com/blob?sas=123"
    assert "TheoGen_Test_Project.pdf" in data["filename"]


def test_explain_theory_claims_fallback_validation(client, monkeypatch):
    project_id = uuid.uuid4()
    theory_id = uuid.uuid4()
    fragment_id = str(uuid.uuid4())

    mock_theory = MagicMock()
    mock_theory.id = theory_id
    mock_theory.model_json = {
        "conditions": [{"name": "Riesgo hídrico", "evidence_ids": [fragment_id]}],
        "actions": [],
        "consequences": [],
        "propositions": [],
        "context": [],
        "intervening_conditions": [],
    }
    mock_theory.validation = {
        "network_metrics_summary": {
            "evidence_index": [
                {
                    "id": fragment_id,
                    "fragment_id": fragment_id,
                    "text": "Fragmento de evidencia",
                    "score": 0.92,
                    "interview_id": str(uuid.uuid4()),
                }
            ]
        }
    }

    mock_project = MagicMock()
    mock_project.id = project_id
    mock_project.owner_id = mock_user_uuid

    mock_db = MagicMock()
    mock_db.execute = AsyncMock(return_value=MagicMock(first=MagicMock(return_value=(mock_theory, mock_project))))
    app.dependency_overrides[get_db] = lambda: mock_db

    monkeypatch.setattr(
        "app.api.theory.neo4j_service.get_theory_claims_explain",
        AsyncMock(return_value=[]),
    )

    response = client.get(f"/api/projects/{project_id}/theories/{theory_id}/claims/explain")
    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "validation_fallback"
    assert body["claim_count"] >= 1
    assert body["claims"][0]["evidence"][0]["fragment_id"] == fragment_id


def test_explain_theory_claims_prefers_neo4j(client, monkeypatch):
    project_id = uuid.uuid4()
    theory_id = uuid.uuid4()
    fragment_id = str(uuid.uuid4())

    mock_theory = MagicMock()
    mock_theory.id = theory_id
    mock_theory.model_json = {}
    mock_theory.validation = {}

    mock_project = MagicMock()
    mock_project.id = project_id
    mock_project.owner_id = mock_user_uuid

    mock_db = MagicMock()
    mock_db.execute = AsyncMock(return_value=MagicMock(first=MagicMock(return_value=(mock_theory, mock_project))))
    app.dependency_overrides[get_db] = lambda: mock_db

    monkeypatch.setattr(
        "app.api.theory.neo4j_service.get_theory_claims_explain",
        AsyncMock(
            return_value=[
                {
                    "claim_id": "c1",
                    "claim_type": "condition",
                    "section": "conditions",
                    "order": 0,
                    "text": "Riesgo hídrico",
                    "categories": [{"id": str(uuid.uuid4()), "name": "Agua"}],
                    "evidence": [{"fragment_id": fragment_id, "score": 0.88, "rank": 0, "text": "snippet"}],
                }
            ]
        ),
    )

    response = client.get(f"/api/projects/{project_id}/theories/{theory_id}/claims/explain")
    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "neo4j"
    assert body["claim_count"] == 1
    assert body["claims"][0]["claim_id"] == "c1"
    assert body["total"] == 1
    assert body["has_more"] is False


def test_explain_theory_claims_fallback_with_filters_and_pagination(client, monkeypatch):
    project_id = uuid.uuid4()
    theory_id = uuid.uuid4()

    frag_a = str(uuid.uuid4())
    frag_b = str(uuid.uuid4())
    frag_c = str(uuid.uuid4())

    mock_theory = MagicMock()
    mock_theory.id = theory_id
    mock_theory.model_json = {
        "conditions": [
            {"name": "Condicion A", "evidence_ids": [frag_a]},
            {"name": "Condicion B", "evidence_ids": [frag_b]},
        ],
        "actions": [{"name": "Accion A", "evidence_ids": [frag_c]}],
        "consequences": [],
        "propositions": [],
        "context": [],
        "intervening_conditions": [],
    }
    mock_theory.validation = {
        "network_metrics_summary": {
            "evidence_index": [
                {"id": frag_a, "fragment_id": frag_a, "text": "E1"},
                {"id": frag_b, "fragment_id": frag_b, "text": "E2"},
                {"id": frag_c, "fragment_id": frag_c, "text": "E3"},
            ]
        }
    }
    mock_project = MagicMock()
    mock_project.id = project_id
    mock_project.owner_id = mock_user_uuid

    mock_db = MagicMock()
    mock_db.execute = AsyncMock(return_value=MagicMock(first=MagicMock(return_value=(mock_theory, mock_project))))
    app.dependency_overrides[get_db] = lambda: mock_db

    monkeypatch.setattr(
        "app.api.theory.neo4j_service.get_theory_claims_explain",
        AsyncMock(return_value={"total": 0, "claims": []}),
    )

    response = client.get(
        f"/api/projects/{project_id}/theories/{theory_id}/claims/explain?section=conditions&offset=1&limit=1"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "validation_fallback"
    assert body["total"] == 2
    assert body["claim_count"] == 1
    assert body["has_more"] is False
    assert body["section_filter"] == "conditions"
    assert body["claims"][0]["text"] == "Condicion B"


def test_explain_theory_claims_neo4j_filters_and_offset(client, monkeypatch):
    project_id = uuid.uuid4()
    theory_id = uuid.uuid4()
    fragment_id = str(uuid.uuid4())

    mock_theory = MagicMock()
    mock_theory.id = theory_id
    mock_theory.model_json = {}
    mock_theory.validation = {}
    mock_project = MagicMock()
    mock_project.id = project_id
    mock_project.owner_id = mock_user_uuid

    mock_db = MagicMock()
    mock_db.execute = AsyncMock(return_value=MagicMock(first=MagicMock(return_value=(mock_theory, mock_project))))
    app.dependency_overrides[get_db] = lambda: mock_db

    neo_mock = AsyncMock(
        return_value={
            "total": 3,
            "claims": [
                {
                    "claim_id": "c2",
                    "claim_type": "condition",
                    "section": "conditions",
                    "order": 1,
                    "text": "Condicion B",
                    "categories": [{"id": str(uuid.uuid4()), "name": "Agua"}],
                    "evidence": [{"fragment_id": fragment_id, "score": 0.8, "rank": 0, "text": "snippet"}],
                }
            ],
        }
    )
    monkeypatch.setattr("app.api.theory.neo4j_service.get_theory_claims_explain", neo_mock)

    response = client.get(
        f"/api/projects/{project_id}/theories/{theory_id}/claims/explain?section=conditions&claim_type=condition&offset=1&limit=1"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "neo4j"
    assert body["total"] == 3
    assert body["claim_count"] == 1
    assert body["has_more"] is True
    assert body["offset"] == 1
    assert body["limit"] == 1
    assert body["section_filter"] == "conditions"
    assert body["claim_type_filter"] == "condition"
    neo_mock.assert_awaited_once()


def test_get_judge_rollout_success(client, monkeypatch):
    project_id = uuid.uuid4()
    theory_id = uuid.uuid4()

    mock_project = MagicMock()
    mock_project.id = project_id
    mock_project.owner_id = mock_user_uuid

    mock_theory = MagicMock()
    mock_theory.id = theory_id
    mock_theory.created_at = None
    mock_theory.validation = {
        "judge": {"ok": True},
        "judge_rollout": {"effective_warn_only": False},
        "claim_metrics": {"claims_without_evidence": 0},
        "quality_metrics": {"evidence_index_size": 40},
        "neo4j_claim_sync": {"enabled": True},
        "qdrant_claim_sync": {"enabled": True},
    }

    project_result = MagicMock()
    project_result.scalar_one_or_none = MagicMock(return_value=mock_project)
    theory_result = MagicMock()
    theory_result.scalars = MagicMock(return_value=MagicMock(first=MagicMock(return_value=mock_theory)))

    mock_db = MagicMock()
    mock_db.execute = AsyncMock(side_effect=[project_result, theory_result])
    app.dependency_overrides[get_db] = lambda: mock_db

    monkeypatch.setattr(
        "app.api.theory.theory_pipeline.get_judge_rollout_policy",
        AsyncMock(
            return_value={
                "enabled": True,
                "configured_warn_only": True,
                "effective_warn_only": False,
                "reason": "strict_auto_promoted",
            }
        ),
    )

    response = client.get(f"/api/projects/{project_id}/theories/judge-rollout")
    assert response.status_code == 200
    body = response.json()
    assert body["project_id"] == str(project_id)
    assert body["policy"]["effective_warn_only"] is False
    assert body["latest_theory_id"] == str(theory_id)
    assert body["latest_validation"]["quality_metrics"]["evidence_index_size"] == 40


def test_get_judge_rollout_project_not_found(client):
    project_id = uuid.uuid4()

    project_result = MagicMock()
    project_result.scalar_one_or_none = MagicMock(return_value=None)

    mock_db = MagicMock()
    mock_db.execute = AsyncMock(return_value=project_result)
    app.dependency_overrides[get_db] = lambda: mock_db

    response = client.get(f"/api/projects/{project_id}/theories/judge-rollout")
    assert response.status_code == 404
    assert response.json()["detail"] == "Project not found"


def test_get_theory_pipeline_slo_success(client):
    project_id = uuid.uuid4()
    theory_id = uuid.uuid4()

    mock_project = MagicMock()
    mock_project.id = project_id
    mock_project.owner_id = mock_user_uuid

    project_result = MagicMock()
    project_result.scalar_one_or_none = MagicMock(return_value=mock_project)

    validation_a = {
        "pipeline_runtime": {
            "latency_ms": {
                "neo4j_metrics_ms": 120.0,
                "qdrant_retrieval_ms": 80.0,
                "identify_llm_ms": 900.0,
                "paradigm_llm_ms": 1200.0,
                "gaps_llm_ms": 300.0,
            }
        },
        "judge": {"warn_only": False},
        "deterministic_routing": {"execution": {"network_metrics_source": "neo4j", "semantic_evidence_source": "qdrant_subgraph"}},
        "claim_metrics": {"claims_without_evidence": 0},
        "neo4j_claim_sync": {"neo4j_sync_failed": False},
        "qdrant_claim_sync": {"qdrant_sync_failed": False},
    }
    validation_b = {
        "pipeline_runtime": {
            "latency_ms": {
                "neo4j_metrics_ms": 150.0,
                "qdrant_retrieval_ms": 200.0,
                "identify_llm_ms": 1100.0,
                "paradigm_llm_ms": 1400.0,
                "gaps_llm_ms": 500.0,
            }
        },
        "judge": {"warn_only": True},
        "deterministic_routing": {"execution": {"network_metrics_source": "sql_fallback", "semantic_evidence_source": "sql_fallback"}},
        "claim_metrics": {"claims_without_evidence": 2},
        "neo4j_claim_sync": {"neo4j_sync_failed": True},
        "qdrant_claim_sync": {"qdrant_sync_failed": False},
    }
    slo_rows = [
        (theory_id, datetime.now(timezone.utc), validation_a),
        (uuid.uuid4(), datetime.now(timezone.utc), validation_b),
    ]
    slo_result = MagicMock()
    slo_result.all = MagicMock(return_value=slo_rows)

    mock_db = MagicMock()
    mock_db.execute = AsyncMock(side_effect=[project_result, slo_result])
    app.dependency_overrides[get_db] = lambda: mock_db

    response = client.get(f"/api/projects/{project_id}/theories/pipeline-slo?window=20")
    assert response.status_code == 200
    body = response.json()
    assert body["project_id"] == str(project_id)
    assert body["sample_size"] == 2
    assert body["latest_theory_id"] == str(theory_id)
    assert body["latency_p95_ms"]["neo4j_metrics_ms"] >= 120.0
    assert body["quality"]["judge_warn_only_runs"] == 1
    assert body["reliability"]["network_sql_fallback_runs"] == 1


def test_get_theory_pipeline_slo_project_not_found(client):
    project_id = uuid.uuid4()
    project_result = MagicMock()
    project_result.scalar_one_or_none = MagicMock(return_value=None)
    mock_db = MagicMock()
    mock_db.execute = AsyncMock(return_value=project_result)
    app.dependency_overrides[get_db] = lambda: mock_db

    response = client.get(f"/api/projects/{project_id}/theories/pipeline-slo")
    assert response.status_code == 404
    assert response.json()["detail"] == "Project not found"
