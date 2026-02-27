from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql

from app.api import assistant as assistant_api
from app.core.auth import CurrentUser


class _CountResult:
    def __init__(self, value: int):
        self._value = value

    def scalar(self):
        return self._value


class _RowsResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, results):
        self._results = list(results)
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        return self._results.pop(0)


def _to_sql(statement) -> str:
    return str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


def _where_clause(sql_query: str) -> str:
    marker = " WHERE "
    if marker not in sql_query:
        return ""
    return sql_query.split(marker, 1)[1]


@pytest.mark.asyncio
async def test_authenticated_metrics_queries_are_user_scoped(monkeypatch):
    async def _schema_enabled():
        return True

    monkeypatch.setattr(assistant_api, "ensure_assistant_schema", _schema_enabled)

    user = CurrentUser(oid=str(uuid4()), email="user@example.com")
    fake_db = _FakeSession([_CountResult(10), _CountResult(2), _CountResult(3)])

    response = await assistant_api.get_authenticated_metrics(user=user, assistant_db=fake_db)

    assert response.logging_enabled is True
    assert response.total_messages_7d == 10
    assert response.blocked_messages_7d == 2
    assert response.leads_7d == 3

    assert len(fake_db.statements) == 3
    sql_queries = [_to_sql(stmt) for stmt in fake_db.statements]
    assert "assistant_message_logs.user_id" in sql_queries[0]
    assert "assistant_message_logs.user_id" in sql_queries[1]
    assert "assistant_contact_leads.user_id" in sql_queries[2]


@pytest.mark.asyncio
async def test_authenticated_ops_forbidden_for_non_tenant_admin(monkeypatch):
    async def _schema_enabled():
        return True

    monkeypatch.setattr(assistant_api, "ensure_assistant_schema", _schema_enabled)

    user = CurrentUser(oid=str(uuid4()), email="user@example.com")
    fake_db = _FakeSession([])

    with pytest.raises(HTTPException) as exc_info:
        await assistant_api.get_authenticated_ops(user=user, assistant_db=fake_db)

    assert exc_info.value.status_code == 403
    assert len(fake_db.statements) == 0


@pytest.mark.asyncio
async def test_authenticated_metrics_tenant_admin_queries_are_tenant_scoped(monkeypatch):
    async def _schema_enabled():
        return True

    monkeypatch.setattr(assistant_api, "ensure_assistant_schema", _schema_enabled)

    user = CurrentUser(
        oid=str(uuid4()),
        email="admin@example.com",
        tenant_id="tenant-a",
        roles=["tenant_admin"],
    )
    fake_db = _FakeSession([_CountResult(20), _CountResult(4), _CountResult(5)])

    response = await assistant_api.get_authenticated_metrics(user=user, assistant_db=fake_db)

    assert response.logging_enabled is True
    assert response.total_messages_7d == 20
    assert response.blocked_messages_7d == 4
    assert response.leads_7d == 5

    assert len(fake_db.statements) == 3
    sql_queries = [_to_sql(stmt) for stmt in fake_db.statements]
    assert "assistant_message_logs.tenant_id" in sql_queries[0]
    assert "assistant_message_logs.tenant_id" in sql_queries[1]
    assert "assistant_contact_leads.tenant_id" in sql_queries[2]
    assert "assistant_message_logs.user_id" not in _where_clause(sql_queries[0])
    assert "assistant_contact_leads.user_id" not in _where_clause(sql_queries[2])


@pytest.mark.asyncio
async def test_authenticated_ops_tenant_admin_queries_are_tenant_scoped(monkeypatch):
    async def _schema_enabled():
        return True

    monkeypatch.setattr(assistant_api, "ensure_assistant_schema", _schema_enabled)

    user = CurrentUser(
        oid=str(uuid4()),
        email="admin@example.com",
        tenant_id="tenant-a",
        roles=["ops"],
    )
    now = datetime.utcnow()

    message_row = SimpleNamespace(
        session_id="session-1",
        mode="authenticated",
        user_message="hola",
        assistant_reply="respuesta",
        intent="general",
        blocked=False,
        created_at=now,
    )
    lead_row = SimpleNamespace(
        session_id="session-1",
        source_mode="authenticated",
        name="Nombre",
        email="user@example.com",
        company="Org",
        phone=None,
        created_at=now,
    )
    fake_db = _FakeSession([_RowsResult([message_row]), _RowsResult([lead_row])])

    response = await assistant_api.get_authenticated_ops(user=user, assistant_db=fake_db)

    assert response.logging_enabled is True
    assert len(response.recent_messages) == 1
    assert len(response.recent_leads) == 1

    assert len(fake_db.statements) == 2
    sql_queries = [_to_sql(stmt) for stmt in fake_db.statements]
    assert "assistant_message_logs.tenant_id" in sql_queries[0]
    assert "assistant_contact_leads.tenant_id" in sql_queries[1]
    assert "assistant_message_logs.user_id" not in _where_clause(sql_queries[0])
    assert "assistant_contact_leads.user_id" not in _where_clause(sql_queries[1])
