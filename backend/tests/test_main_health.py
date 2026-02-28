from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

import app.main as main_module


def test_health_dependencies_healthy(monkeypatch):
    monkeypatch.setattr(main_module.settings, "HEALTHCHECK_DEPENDENCIES_KEY", "")
    monkeypatch.setattr(main_module.settings, "THEORY_CONFIG_ISSUES", [])
    monkeypatch.setattr(main_module.neo4j_service, "enabled", True, raising=False)
    monkeypatch.setattr(main_module.qdrant_service, "enabled", True, raising=False)
    monkeypatch.setattr(
        main_module.neo4j_service,
        "verify_connectivity",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        main_module.qdrant_service,
        "verify_connectivity",
        AsyncMock(return_value=True),
    )

    with TestClient(main_module.app) as client:
        resp = client.get("/health/dependencies")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"
    assert body["dependencies"]["neo4j"]["ok"] is True
    assert body["dependencies"]["qdrant"]["ok"] is True
    assert body["pipeline"]["theory_runtime_config"]["ok"] is True


def test_health_dependencies_degraded_when_qdrant_fails(monkeypatch):
    monkeypatch.setattr(main_module.settings, "HEALTHCHECK_DEPENDENCIES_KEY", "")
    monkeypatch.setattr(main_module.settings, "THEORY_CONFIG_ISSUES", [])
    monkeypatch.setattr(main_module.neo4j_service, "enabled", True, raising=False)
    monkeypatch.setattr(main_module.qdrant_service, "enabled", True, raising=False)
    monkeypatch.setattr(
        main_module.neo4j_service,
        "verify_connectivity",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        main_module.qdrant_service,
        "verify_connectivity",
        AsyncMock(return_value=False),
    )

    with TestClient(main_module.app) as client:
        resp = client.get("/health/dependencies")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["dependencies"]["neo4j"]["ok"] is True
    assert body["dependencies"]["qdrant"]["ok"] is False


def test_health_dependencies_requires_key_when_configured(monkeypatch):
    monkeypatch.setattr(main_module.settings, "HEALTHCHECK_DEPENDENCIES_KEY", "secret-health-key")
    monkeypatch.setattr(main_module.settings, "THEORY_CONFIG_ISSUES", [])
    monkeypatch.setattr(main_module.neo4j_service, "enabled", True, raising=False)
    monkeypatch.setattr(main_module.qdrant_service, "enabled", True, raising=False)
    monkeypatch.setattr(main_module.neo4j_service, "verify_connectivity", AsyncMock(return_value=True))
    monkeypatch.setattr(main_module.qdrant_service, "verify_connectivity", AsyncMock(return_value=True))

    with TestClient(main_module.app) as client:
        denied = client.get("/health/dependencies")
        allowed = client.get("/health/dependencies", headers={"X-Health-Key": "secret-health-key"})

    assert denied.status_code == 401
    assert allowed.status_code == 200
    assert allowed.json()["status"] == "healthy"


def test_health_dependencies_degraded_when_theory_runtime_config_is_invalid(monkeypatch):
    monkeypatch.setattr(main_module.settings, "HEALTHCHECK_DEPENDENCIES_KEY", "")
    monkeypatch.setattr(
        main_module.settings,
        "THEORY_CONFIG_ISSUES",
        ["Produccion requiere THEORY_USE_JUDGE=true."],
    )
    monkeypatch.setattr(main_module.neo4j_service, "enabled", True, raising=False)
    monkeypatch.setattr(main_module.qdrant_service, "enabled", True, raising=False)
    monkeypatch.setattr(main_module.neo4j_service, "verify_connectivity", AsyncMock(return_value=True))
    monkeypatch.setattr(main_module.qdrant_service, "verify_connectivity", AsyncMock(return_value=True))

    with TestClient(main_module.app) as client:
        resp = client.get("/health/dependencies")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["pipeline"]["theory_runtime_config"]["ok"] is False
    assert len(body["pipeline"]["theory_runtime_config"]["issues"]) >= 1
