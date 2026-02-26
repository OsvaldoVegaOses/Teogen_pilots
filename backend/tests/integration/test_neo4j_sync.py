import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.engines.coding_engine import coding_engine
from app.services.neo4j_service import neo4j_service


class _ScalarOneResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def scalars(self):
        return self

    def first(self):
        return self._value


class _ScalarsResult:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return self

    def all(self):
        return self._values


@pytest.mark.asyncio
async def test_auto_code_interview_ensures_project_node(monkeypatch):
    project_id = uuid.uuid4()
    interview_id = uuid.uuid4()
    db = AsyncMock()

    project = SimpleNamespace(id=project_id, name="Proyecto GT")
    db.execute = AsyncMock(side_effect=[
        _ScalarOneResult(project),   # select(Project)
        _ScalarsResult([]),          # select(Fragment)
    ])

    ensure_project_node = AsyncMock()
    monkeypatch.setattr(neo4j_service, "ensure_project_node", ensure_project_node)
    monkeypatch.setattr(coding_engine, "process_fragment", AsyncMock())

    await coding_engine.auto_code_interview(project_id, interview_id, db)

    ensure_project_node.assert_awaited_once_with(project_id, "Proyecto GT")
    db.commit.assert_not_called()
