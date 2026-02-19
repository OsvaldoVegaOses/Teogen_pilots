import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.auth import get_current_user, CurrentUser
from app.database import get_db
from unittest.mock import MagicMock, AsyncMock
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
