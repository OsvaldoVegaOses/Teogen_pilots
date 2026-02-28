import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.neo4j_service import neo4j_service


class _DummySessionCtx:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _DummyDriver:
    def session(self):
        return _DummySessionCtx()


@pytest.mark.asyncio
async def test_batch_sync_interview_links_interview_and_coded_as(monkeypatch):
    project_id = uuid.uuid4()
    interview_id = uuid.uuid4()
    fragment_id = uuid.uuid4()
    code_id = uuid.uuid4()

    run_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(neo4j_service, "enabled", True, raising=False)
    monkeypatch.setattr(neo4j_service, "driver", _DummyDriver(), raising=False)
    monkeypatch.setattr(neo4j_service, "_run", run_mock, raising=False)

    await neo4j_service.batch_sync_interview(
        project_id=project_id,
        interview_id=interview_id,
        fragments=[(fragment_id, "Texto de ejemplo")],
        codes_cache={"codigo": SimpleNamespace(id=code_id)},
        fragment_code_pairs=[(fragment_id, code_id)],
        code_edge_rows=[
            {
                "code_id": str(code_id),
                "frag_id": str(fragment_id),
                "confidence": 0.91,
                "source": "ai",
                "run_id": "run-coding-1",
                "ts": "2026-02-28T00:00:00",
                "char_start": 3,
                "char_end": 20,
            }
        ],
    )

    queries = [call.args[1] for call in run_mock.await_args_list]
    assert any("HAS_INTERVIEW" in q for q in queries)
    assert any("CODED_AS" in q for q in queries)

    coded_call = next(call for call in run_mock.await_args_list if "CODED_AS" in call.args[1])
    pairs = coded_call.args[2]["pairs"]
    assert pairs and pairs[0]["run_id"] == "run-coding-1"
    assert pairs[0]["source"] == "ai"
    assert pairs[0]["char_start"] == 3
    assert pairs[0]["char_end"] == 20


@pytest.mark.asyncio
async def test_batch_sync_claims_persists_run_stage_and_contradicted_by(monkeypatch):
    project_id = uuid.uuid4()
    theory_id = uuid.uuid4()
    owner_id = str(uuid.uuid4())
    category_id = uuid.uuid4()

    run_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(neo4j_service, "enabled", True, raising=False)
    monkeypatch.setattr(neo4j_service, "driver", _DummyDriver(), raising=False)
    monkeypatch.setattr(neo4j_service, "_run", run_mock, raising=False)
    monkeypatch.setattr(
        neo4j_service,
        "_ensure_claim_constraints",
        AsyncMock(return_value=None),
        raising=False,
    )

    evidence_ok = str(uuid.uuid4())
    evidence_contra = str(uuid.uuid4())
    paradigm = {
        "conditions": [
            {
                "name": "Condicion X",
                "evidence_ids": [evidence_ok],
                "counter_evidence_ids": [evidence_contra],
            }
        ],
        "actions": [],
        "consequences": [],
        "propositions": [],
    }
    evidence_index = [
        {"fragment_id": evidence_ok, "score": 0.87},
        {"fragment_id": evidence_contra, "score": 0.22},
    ]

    await neo4j_service.batch_sync_claims(
        project_id=project_id,
        theory_id=theory_id,
        owner_id=owner_id,
        paradigm=paradigm,
        evidence_index=evidence_index,
        categories=[(category_id, "Condicion X")],
        run_id="task-123",
        stage="theory_pipeline",
    )

    claim_call = next(call for call in run_mock.await_args_list if "HAS_CLAIM" in call.args[1])
    claims_payload = claim_call.args[2]["claims"]
    assert claims_payload and claims_payload[0]["run_id"] == "task-123"
    assert claims_payload[0]["stage"] == "theory_pipeline"

    assert any("CONTRADICTED_BY" in call.args[1] for call in run_mock.await_args_list)
    contradict_call = next(call for call in run_mock.await_args_list if "CONTRADICTED_BY" in call.args[1])
    contradict_rows = contradict_call.args[2]["rows"]
    assert contradict_rows and contradict_rows[0]["fragment_id"] == evidence_contra
