from types import SimpleNamespace
from unittest.mock import AsyncMock
import uuid

import pytest

from app.core.settings import settings
from app.services.qdrant_service import FoundryQdrantService


@pytest.mark.asyncio
async def test_search_similar_retries_and_recovers(monkeypatch):
    monkeypatch.setattr(settings, "QDRANT_SEARCH_MAX_RETRIES", 3)
    monkeypatch.setattr(settings, "QDRANT_SEARCH_BACKOFF_SECONDS", 0.01)

    service = FoundryQdrantService()
    service.enabled = True
    query_points = AsyncMock(
        side_effect=[
            RuntimeError("transient"),
            SimpleNamespace(points=[SimpleNamespace(id="f1", score=0.91, payload={"text": "ok"})]),
        ]
    )
    service.client = SimpleNamespace(query_points=query_points)
    sleep_mock = AsyncMock()
    monkeypatch.setattr("app.services.qdrant_service.asyncio.sleep", sleep_mock)

    result = await service.search_similar(
        project_id=uuid.uuid4(),
        vector=[0.1, 0.2, 0.3],
        limit=1,
        score_threshold=0.0,
    )

    assert len(result) == 1
    assert query_points.await_count == 2
    sleep_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_search_similar_returns_empty_after_retry_exhaustion(monkeypatch):
    monkeypatch.setattr(settings, "QDRANT_SEARCH_MAX_RETRIES", 2)
    monkeypatch.setattr(settings, "QDRANT_SEARCH_BACKOFF_SECONDS", 0.0)

    service = FoundryQdrantService()
    service.enabled = True
    query_points = AsyncMock(side_effect=RuntimeError("persistent"))
    service.client = SimpleNamespace(query_points=query_points)
    sleep_mock = AsyncMock()
    monkeypatch.setattr("app.services.qdrant_service.asyncio.sleep", sleep_mock)

    result = await service.search_similar(
        project_id=uuid.uuid4(),
        vector=[0.1, 0.2, 0.3],
        limit=1,
        score_threshold=0.0,
    )

    assert result == []
    assert query_points.await_count == 2
