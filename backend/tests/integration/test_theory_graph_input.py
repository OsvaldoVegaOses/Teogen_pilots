from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
import uuid

import pytest

from app.core.settings import settings
from app.engines.theory_pipeline import TheoryPipeline
from app.schemas.theory import TheoryGenerateRequest


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


class _RowsResult:
    def __init__(self, values):
        self._values = values

    def all(self):
        return self._values


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar(self):
        return self._value


@pytest.mark.asyncio
async def test_theory_pipeline_populates_network_metrics_summary(monkeypatch):
    # Keep the test focused: validate that real graph metrics + semantic evidence
    # are persisted into validation.network_metrics_summary.
    monkeypatch.setattr(settings, "THEORY_USE_SUBGRAPH_EVIDENCE", False)
    monkeypatch.setattr(settings, "THEORY_USE_JUDGE", False)
    monkeypatch.setattr(settings, "THEORY_SYNC_CLAIMS_NEO4J", False)

    project_id = uuid.uuid4()
    user_uuid = uuid.uuid4()

    project = SimpleNamespace(id=project_id, owner_id=user_uuid, name="Proyecto", language="es", domain_template="generic")
    cat_1 = SimpleNamespace(id=uuid.uuid4(), name="Categoria A", definition="Def A")
    cat_2 = SimpleNamespace(id=uuid.uuid4(), name="Categoria B", definition="Def B")
    code = SimpleNamespace(id=uuid.uuid4(), category_id=cat_1.id)

    frag_id = uuid.uuid4()

    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _ScalarOneResult(project),  # select(Project)
            _ScalarsResult([cat_1, cat_2]),  # select(Category)
            _ScalarsResult([code]),  # select(Code)
        ]
    )
    db.add = MagicMock()
    db.commit = AsyncMock()

    async def _refresh(obj):
        obj.id = uuid.uuid4()
        obj.created_at = datetime.utcnow()
        obj.version = 1

    db.refresh = AsyncMock(side_effect=_refresh)

    pipeline = TheoryPipeline()

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
        return [
            {"fragment_id": str(frag_id), "id": str(frag_id), "score": 0.87, "text": "fragmento de evidencia", "codes": ["C1"]}
        ]

    async def _identify(*args, **kwargs):
        return {"selected_central_category": "Categoria A"}

    async def _build(*args, **kwargs):
        return {
            "selected_central_category": "Categoria A",
            "conditions": [{"name": "Categoria A", "evidence_ids": [str(frag_id)]}],
            "context": [{"name": "Categoria B", "evidence_ids": [str(frag_id)]}],
            "intervening_conditions": [{"name": "Categoria B", "evidence_ids": [str(frag_id)]}],
            "actions": [{"name": "Categoria B", "evidence_ids": [str(frag_id)]}],
            "consequences": [
                {"name": "Impacto material", "type": "material", "horizon": "corto_plazo", "evidence_ids": [str(frag_id)]},
                {"name": "Impacto social", "type": "social", "horizon": "largo_plazo", "evidence_ids": [str(frag_id)]},
                {"name": "Impacto institucional", "type": "institutional", "horizon": "corto_plazo", "evidence_ids": [str(frag_id)]},
            ],
            "propositions": [
                {"text": "Si X y Y, entonces Z, porque M.", "evidence_ids": [str(frag_id)]}
                for _ in range(5)
            ],
            "confidence_score": 0.82,
        }

    async def _gaps(*args, **kwargs):
        return {"identified_gaps": []}

    monkeypatch.setattr(pipeline, "_auto_code_if_needed", AsyncMock(return_value=[cat_1, cat_2]))
    monkeypatch.setattr(pipeline.neo4j_service, "ensure_project_node", AsyncMock(side_effect=_noop))
    monkeypatch.setattr(pipeline.neo4j_service, "batch_sync_taxonomy", AsyncMock(side_effect=_noop))
    monkeypatch.setattr(pipeline.neo4j_service, "get_project_network_metrics", AsyncMock(side_effect=_network_metrics))
    monkeypatch.setattr(pipeline.foundry_openai, "generate_embeddings", AsyncMock(side_effect=_embeddings))
    monkeypatch.setattr(pipeline.qdrant_service, "search_supporting_fragments", AsyncMock(side_effect=_semantic_hits))
    monkeypatch.setattr(pipeline.theory_engine, "identify_central_category", AsyncMock(side_effect=_identify))
    monkeypatch.setattr(pipeline.theory_engine, "build_straussian_paradigm", AsyncMock(side_effect=_build))
    monkeypatch.setattr(pipeline.theory_engine, "analyze_saturation_and_gaps", AsyncMock(side_effect=_gaps))

    async def _mark_step(*_args, **_kwargs):
        return None

    async def _refresh_lock():
        return None

    result = await pipeline.run(
        task_id="t1",
        project_id=project_id,
        user_uuid=user_uuid,
        request=TheoryGenerateRequest(min_interviews=1, use_model_router=True),
        db=db,
        mark_step=_mark_step,
        refresh_lock=_refresh_lock,
    )

    summary = result["validation"]["network_metrics_summary"]
    assert summary["counts"]["category_count"] == 2
    assert len(summary["category_centrality_top"]) > 0
    assert len(summary["semantic_evidence_top"]) > 0


@pytest.mark.asyncio
async def test_theory_pipeline_uses_coarse_fine_qdrant_retrieval(monkeypatch):
    monkeypatch.setattr(settings, "THEORY_USE_SUBGRAPH_EVIDENCE", True)
    monkeypatch.setattr(settings, "THEORY_USE_JUDGE", False)
    monkeypatch.setattr(settings, "THEORY_SYNC_CLAIMS_NEO4J", False)
    monkeypatch.setattr(settings, "THEORY_SYNC_CLAIMS_QDRANT", False)

    project_id = uuid.uuid4()
    user_uuid = uuid.uuid4()
    project = SimpleNamespace(id=project_id, owner_id=user_uuid, name="Proyecto", language="es", domain_template="generic")
    cat_1 = SimpleNamespace(id=uuid.uuid4(), name="Categoria A", definition="Def A")
    cat_2 = SimpleNamespace(id=uuid.uuid4(), name="Categoria B", definition="Def B")
    code = SimpleNamespace(id=uuid.uuid4(), category_id=cat_1.id)
    frag_id = uuid.uuid4()
    interview_id = uuid.uuid4()

    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _ScalarOneResult(project),
            _ScalarsResult([cat_1, cat_2]),
            _ScalarsResult([code]),
            _RowsResult([(frag_id, interview_id)]),
        ]
    )
    db.add = MagicMock()
    db.commit = AsyncMock()

    async def _refresh(obj):
        obj.id = uuid.uuid4()
        obj.created_at = datetime.utcnow()
        obj.version = 1

    db.refresh = AsyncMock(side_effect=_refresh)

    pipeline = TheoryPipeline()

    async def _noop(*args, **kwargs):
        return None

    async def _network_metrics(*args, **kwargs):
        return {
            "counts": {"category_count": 2, "code_count": 1, "fragment_count": 3},
            "category_centrality": [
                {"category_id": str(cat_1.id), "category_name": cat_1.name, "code_degree": 1, "fragment_degree": 2},
                {"category_id": str(cat_2.id), "category_name": cat_2.name, "code_degree": 1, "fragment_degree": 1},
            ],
            "category_cooccurrence": [
                {"category_a_id": str(cat_1.id), "category_b_id": str(cat_2.id), "shared_fragments": 1}
            ],
        }

    async def _embeddings(texts, *args, **kwargs):
        return [[0.1, 0.2, 0.3] for _ in texts]

    qdrant_calls = []

    async def _semantic_hits(*args, **kwargs):
        qdrant_calls.append(kwargs)
        source_types = kwargs.get("source_types") or []
        if source_types == ["category_summary"]:
            return [
                {
                    "id": f"category_summary:{cat_2.id}",
                    "fragment_id": f"category_summary:{cat_2.id}",
                    "metadata": {"category_id": str(cat_2.id), "source_type": "category_summary"},
                }
            ]
        return [
            {
                "fragment_id": str(frag_id),
                "id": str(frag_id),
                "score": 0.89,
                "text": "evidencia fragmento",
                "codes": ["C1"],
            }
        ]

    async def _identify(*args, **kwargs):
        return {"selected_central_category": "Categoria A"}

    async def _build(*args, **kwargs):
        return {
            "selected_central_category": "Categoria A",
            "conditions": [{"name": "Categoria A", "evidence_ids": [str(frag_id)]}],
            "context": [{"name": "Categoria B", "evidence_ids": [str(frag_id)]}],
            "intervening_conditions": [{"name": "Categoria B", "evidence_ids": [str(frag_id)]}],
            "actions": [{"name": "Categoria B", "evidence_ids": [str(frag_id)]}],
            "consequences": [
                {"name": "Impacto material", "type": "material", "horizon": "corto_plazo", "evidence_ids": [str(frag_id)]},
                {"name": "Impacto social", "type": "social", "horizon": "largo_plazo", "evidence_ids": [str(frag_id)]},
                {"name": "Impacto institucional", "type": "institutional", "horizon": "corto_plazo", "evidence_ids": [str(frag_id)]},
            ],
            "propositions": [{"text": "P1", "evidence_ids": [str(frag_id)]} for _ in range(5)],
            "confidence_score": 0.8,
        }

    async def _gaps(*args, **kwargs):
        return {"identified_gaps": []}

    monkeypatch.setattr(pipeline, "_auto_code_if_needed", AsyncMock(return_value=[cat_1, cat_2]))
    monkeypatch.setattr(pipeline, "_sync_category_summary_vectors", AsyncMock(return_value=2))
    monkeypatch.setattr(pipeline.neo4j_service, "ensure_project_node", AsyncMock(side_effect=_noop))
    monkeypatch.setattr(pipeline.neo4j_service, "batch_sync_taxonomy", AsyncMock(side_effect=_noop))
    monkeypatch.setattr(pipeline.neo4j_service, "get_project_network_metrics", AsyncMock(side_effect=_network_metrics))
    monkeypatch.setattr(pipeline.foundry_openai, "generate_embeddings", AsyncMock(side_effect=_embeddings))
    monkeypatch.setattr(pipeline.qdrant_service, "search_supporting_fragments", AsyncMock(side_effect=_semantic_hits))
    monkeypatch.setattr(pipeline.theory_engine, "identify_central_category", AsyncMock(side_effect=_identify))
    monkeypatch.setattr(pipeline.theory_engine, "build_straussian_paradigm", AsyncMock(side_effect=_build))
    monkeypatch.setattr(pipeline.theory_engine, "analyze_saturation_and_gaps", AsyncMock(side_effect=_gaps))

    async def _mark_step(*_args, **_kwargs):
        return None

    async def _refresh_lock():
        return None

    result = await pipeline.run(
        task_id="t2",
        project_id=project_id,
        user_uuid=user_uuid,
        request=TheoryGenerateRequest(min_interviews=1, use_model_router=True),
        db=db,
        mark_step=_mark_step,
        refresh_lock=_refresh_lock,
    )

    summary = result["validation"]["network_metrics_summary"]
    assert summary.get("coarse_summary_hits", 0) >= 1
    assert summary.get("refined_category_count", 0) >= 2
    assert any(call.get("source_types") == ["category_summary"] for call in qdrant_calls)
    assert any(call.get("source_types") == ["fragment"] for call in qdrant_calls)


@pytest.mark.asyncio
async def test_theory_pipeline_syncs_claim_vectors_to_qdrant(monkeypatch):
    monkeypatch.setattr(settings, "THEORY_USE_SUBGRAPH_EVIDENCE", False)
    monkeypatch.setattr(settings, "THEORY_USE_JUDGE", False)
    monkeypatch.setattr(settings, "THEORY_SYNC_CLAIMS_NEO4J", False)
    monkeypatch.setattr(settings, "THEORY_SYNC_CLAIMS_QDRANT", True)

    project_id = uuid.uuid4()
    user_uuid = uuid.uuid4()
    project = SimpleNamespace(id=project_id, owner_id=user_uuid, name="Proyecto", language="es", domain_template="generic")
    cat_1 = SimpleNamespace(id=uuid.uuid4(), name="Categoria A", definition="Def A")
    cat_2 = SimpleNamespace(id=uuid.uuid4(), name="Categoria B", definition="Def B")
    code = SimpleNamespace(id=uuid.uuid4(), category_id=cat_1.id)
    frag_id = uuid.uuid4()

    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _ScalarOneResult(project),
            _ScalarsResult([cat_1, cat_2]),
            _ScalarsResult([code]),
        ]
    )
    db.add = MagicMock()
    db.commit = AsyncMock()

    async def _refresh(obj):
        obj.id = uuid.uuid4()
        obj.created_at = datetime.utcnow()
        obj.version = 1

    db.refresh = AsyncMock(side_effect=_refresh)
    pipeline = TheoryPipeline()

    async def _noop(*args, **kwargs):
        return None

    async def _network_metrics(*args, **kwargs):
        return {
            "counts": {"category_count": 2, "code_count": 1, "fragment_count": 3},
            "category_centrality": [{"category_id": str(cat_1.id), "category_name": cat_1.name}],
            "category_cooccurrence": [],
        }

    async def _embeddings(*args, **kwargs):
        return [[0.1, 0.2, 0.3]]

    async def _semantic_hits(*args, **kwargs):
        return [{"fragment_id": str(frag_id), "id": str(frag_id), "score": 0.9, "text": "evidencia", "codes": ["C1"]}]

    async def _identify(*args, **kwargs):
        return {"selected_central_category": "Categoria A"}

    async def _build(*args, **kwargs):
        return {
            "selected_central_category": "Categoria A",
            "conditions": [{"name": "Categoria A", "evidence_ids": [str(frag_id)]}],
            "context": [{"name": "Categoria B", "evidence_ids": [str(frag_id)]}],
            "intervening_conditions": [{"name": "Categoria B", "evidence_ids": [str(frag_id)]}],
            "actions": [{"name": "Categoria B", "evidence_ids": [str(frag_id)]}],
            "consequences": [
                {"name": "Impacto material", "type": "material", "horizon": "corto_plazo", "evidence_ids": [str(frag_id)]},
                {"name": "Impacto social", "type": "social", "horizon": "largo_plazo", "evidence_ids": [str(frag_id)]},
                {"name": "Impacto institucional", "type": "institutional", "horizon": "corto_plazo", "evidence_ids": [str(frag_id)]},
            ],
            "propositions": [{"text": "P1", "evidence_ids": [str(frag_id)]} for _ in range(5)],
            "confidence_score": 0.83,
        }

    async def _gaps(*args, **kwargs):
        return {"identified_gaps": []}

    sync_claim_vectors = AsyncMock(return_value=5)

    monkeypatch.setattr(pipeline, "_auto_code_if_needed", AsyncMock(return_value=[cat_1, cat_2]))
    monkeypatch.setattr(pipeline.neo4j_service, "ensure_project_node", AsyncMock(side_effect=_noop))
    monkeypatch.setattr(pipeline.neo4j_service, "batch_sync_taxonomy", AsyncMock(side_effect=_noop))
    monkeypatch.setattr(pipeline.neo4j_service, "get_project_network_metrics", AsyncMock(side_effect=_network_metrics))
    monkeypatch.setattr(pipeline.foundry_openai, "generate_embeddings", AsyncMock(side_effect=_embeddings))
    monkeypatch.setattr(pipeline.qdrant_service, "search_supporting_fragments", AsyncMock(side_effect=_semantic_hits))
    monkeypatch.setattr(pipeline.theory_engine, "identify_central_category", AsyncMock(side_effect=_identify))
    monkeypatch.setattr(pipeline.theory_engine, "build_straussian_paradigm", AsyncMock(side_effect=_build))
    monkeypatch.setattr(pipeline.theory_engine, "analyze_saturation_and_gaps", AsyncMock(side_effect=_gaps))
    monkeypatch.setattr(pipeline, "_sync_claim_vectors", sync_claim_vectors)

    async def _mark_step(*_args, **_kwargs):
        return None

    async def _refresh_lock():
        return None

    result = await pipeline.run(
        task_id="t3",
        project_id=project_id,
        user_uuid=user_uuid,
        request=TheoryGenerateRequest(min_interviews=1, use_model_router=True),
        db=db,
        mark_step=_mark_step,
        refresh_lock=_refresh_lock,
    )

    qdrant_sync = result["validation"]["qdrant_claim_sync"]
    assert qdrant_sync["enabled"] is True
    assert qdrant_sync["claims_synced_count"] == 5
    assert qdrant_sync["qdrant_sync_failed"] is False
    sync_claim_vectors.assert_awaited_once()


@pytest.mark.asyncio
async def test_theory_pipeline_deterministic_routing_falls_back_to_sql(monkeypatch):
    monkeypatch.setattr(settings, "THEORY_USE_SUBGRAPH_EVIDENCE", False)
    monkeypatch.setattr(settings, "THEORY_USE_JUDGE", False)
    monkeypatch.setattr(settings, "THEORY_SYNC_CLAIMS_NEO4J", False)
    monkeypatch.setattr(settings, "THEORY_SYNC_CLAIMS_QDRANT", False)
    monkeypatch.setattr(settings, "THEORY_USE_DETERMINISTIC_GAPS", False)
    monkeypatch.setattr(settings, "THEORY_USE_DETERMINISTIC_ROUTING", True)

    project_id = uuid.uuid4()
    user_uuid = uuid.uuid4()
    project = SimpleNamespace(id=project_id, owner_id=user_uuid, name="Proyecto", language="es", domain_template="generic")
    cat_1 = SimpleNamespace(id=uuid.uuid4(), name="Categoria A", definition="Def A")
    cat_2 = SimpleNamespace(id=uuid.uuid4(), name="Categoria B", definition="Def B")
    code = SimpleNamespace(id=uuid.uuid4(), category_id=cat_1.id, label="Codigo A")
    frag_id = uuid.uuid4()
    interview_id = uuid.uuid4()

    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _ScalarOneResult(project),
            _ScalarsResult([cat_1, cat_2]),
            _ScalarsResult([code]),
            _ScalarResult(1),
            _RowsResult([(cat_1.id, 1, 1), (cat_2.id, 0, 0)]),
            _RowsResult([(frag_id, "evidencia sql", interview_id, cat_1.id)]),
        ]
    )
    db.add = MagicMock()
    db.commit = AsyncMock()

    async def _refresh(obj):
        obj.id = uuid.uuid4()
        obj.created_at = datetime.utcnow()
        obj.version = 1

    db.refresh = AsyncMock(side_effect=_refresh)

    pipeline = TheoryPipeline()

    async def _embeddings(texts, *args, **kwargs):
        return [[0.1, 0.2, 0.3] for _ in texts]

    async def _identify(*args, **kwargs):
        return {"selected_central_category": "Categoria A"}

    async def _build(*args, **kwargs):
        return {
            "selected_central_category": "Categoria A",
            "conditions": [{"name": "Categoria A", "evidence_ids": [str(frag_id)]}],
            "context": [{"name": "Categoria B", "evidence_ids": [str(frag_id)]}],
            "intervening_conditions": [{"name": "Categoria B", "evidence_ids": [str(frag_id)]}],
            "actions": [{"name": "Categoria B", "evidence_ids": [str(frag_id)]}],
            "consequences": [
                {"name": "Impacto material", "type": "material", "horizon": "corto_plazo", "evidence_ids": [str(frag_id)]},
                {"name": "Impacto social", "type": "social", "horizon": "largo_plazo", "evidence_ids": [str(frag_id)]},
                {"name": "Impacto institucional", "type": "institutional", "horizon": "corto_plazo", "evidence_ids": [str(frag_id)]},
            ],
            "propositions": [{"text": "P1", "evidence_ids": [str(frag_id)]} for _ in range(5)],
            "confidence_score": 0.8,
        }

    async def _gaps(*args, **kwargs):
        return {"identified_gaps": []}

    monkeypatch.setattr(pipeline, "_auto_code_if_needed", AsyncMock(return_value=[cat_1, cat_2]))
    monkeypatch.setattr(pipeline.neo4j_service, "ensure_project_node", AsyncMock(side_effect=RuntimeError("neo4j down")))
    monkeypatch.setattr(pipeline.neo4j_service, "batch_sync_taxonomy", AsyncMock(return_value=None))
    monkeypatch.setattr(
        pipeline.neo4j_service,
        "get_project_network_metrics",
        AsyncMock(side_effect=RuntimeError("neo4j metrics unavailable")),
    )
    monkeypatch.setattr(pipeline.foundry_openai, "generate_embeddings", AsyncMock(side_effect=_embeddings))
    monkeypatch.setattr(pipeline.qdrant_service, "search_supporting_fragments", AsyncMock(return_value=[]))
    monkeypatch.setattr(pipeline.theory_engine, "identify_central_category", AsyncMock(side_effect=_identify))
    monkeypatch.setattr(pipeline.theory_engine, "build_straussian_paradigm", AsyncMock(side_effect=_build))
    monkeypatch.setattr(pipeline.theory_engine, "analyze_saturation_and_gaps", AsyncMock(side_effect=_gaps))

    async def _mark_step(*_args, **_kwargs):
        return None

    async def _refresh_lock():
        return None

    result = await pipeline.run(
        task_id="t-routing",
        project_id=project_id,
        user_uuid=user_uuid,
        request=TheoryGenerateRequest(min_interviews=1, use_model_router=False),
        db=db,
        mark_step=_mark_step,
        refresh_lock=_refresh_lock,
    )

    validation = result["validation"]
    routing = validation["deterministic_routing"]
    assert routing["enabled"] is True
    assert routing["execution"]["network_metrics_source"] == "sql_fallback"
    assert routing["execution"]["semantic_evidence_source"] == "sql_fallback"
    assert validation["quality_metrics"]["evidence_index_size"] >= 1


@pytest.mark.asyncio
async def test_judge_rollout_policy_auto_promotes_to_strict(monkeypatch):
    monkeypatch.setattr(settings, "THEORY_USE_JUDGE", True)
    monkeypatch.setattr(settings, "THEORY_JUDGE_WARN_ONLY", True)
    monkeypatch.setattr(settings, "THEORY_JUDGE_STRICT_COHORT_PERCENT", 100)
    monkeypatch.setattr(settings, "THEORY_JUDGE_STRICT_WINDOW", 5)
    monkeypatch.setattr(settings, "THEORY_JUDGE_STRICT_MIN_THEORIES", 3)
    monkeypatch.setattr(settings, "THEORY_JUDGE_STRICT_MAX_BAD_RUNS", 1)
    monkeypatch.setattr(settings, "THEORY_EVIDENCE_MIN_INTERVIEWS", 4)
    monkeypatch.setattr(settings, "THEORY_EVIDENCE_TARGET_MIN", 30)

    pipeline = TheoryPipeline()
    project_id = uuid.uuid4()
    db = AsyncMock()
    db.execute = AsyncMock(
        return_value=_ScalarsResult(
            [
                {
                    "judge": {"warn_only": False},
                    "claim_metrics": {"claims_without_evidence": 0, "interviews_covered": 5},
                    "quality_metrics": {"evidence_index_size": 40},
                },
                {
                    "judge": {"warn_only": False},
                    "claim_metrics": {"claims_without_evidence": 0, "interviews_covered": 4},
                    "quality_metrics": {"evidence_index_size": 35},
                },
                {
                    "judge": {"warn_only": False},
                    "claim_metrics": {"claims_without_evidence": 0, "interviews_covered": 6},
                    "quality_metrics": {"evidence_index_size": 50},
                },
            ]
        )
    )

    policy = await pipeline._resolve_judge_rollout_policy(project_id=project_id, db=db)
    assert policy["in_strict_cohort"] is True
    assert policy["stable"] is True
    assert policy["effective_warn_only"] is False
    assert policy["reason"] == "strict_auto_promoted"


@pytest.mark.asyncio
async def test_judge_rollout_policy_keeps_warn_only_when_unstable(monkeypatch):
    monkeypatch.setattr(settings, "THEORY_USE_JUDGE", True)
    monkeypatch.setattr(settings, "THEORY_JUDGE_WARN_ONLY", True)
    monkeypatch.setattr(settings, "THEORY_JUDGE_STRICT_COHORT_PERCENT", 100)
    monkeypatch.setattr(settings, "THEORY_JUDGE_STRICT_WINDOW", 5)
    monkeypatch.setattr(settings, "THEORY_JUDGE_STRICT_MIN_THEORIES", 3)
    monkeypatch.setattr(settings, "THEORY_JUDGE_STRICT_MAX_BAD_RUNS", 1)
    monkeypatch.setattr(settings, "THEORY_EVIDENCE_MIN_INTERVIEWS", 4)
    monkeypatch.setattr(settings, "THEORY_EVIDENCE_TARGET_MIN", 30)

    pipeline = TheoryPipeline()
    project_id = uuid.uuid4()
    db = AsyncMock()
    db.execute = AsyncMock(
        return_value=_ScalarsResult(
            [
                {
                    "judge": {"warn_only": True},
                    "claim_metrics": {"claims_without_evidence": 0, "interviews_covered": 4},
                    "quality_metrics": {"evidence_index_size": 35},
                },
                {
                    "judge": {"warn_only": False},
                    "claim_metrics": {"claims_without_evidence": 1, "interviews_covered": 3},
                    "quality_metrics": {"evidence_index_size": 20},
                },
                {
                    "judge": {"warn_only": False},
                    "claim_metrics": {"claims_without_evidence": 0, "interviews_covered": 4},
                    "quality_metrics": {"evidence_index_size": 31},
                },
            ]
        )
    )

    policy = await pipeline._resolve_judge_rollout_policy(project_id=project_id, db=db)
    assert policy["in_strict_cohort"] is True
    assert policy["stable"] is False
    assert policy["effective_warn_only"] is True
    assert policy["reason"] == "warn_only_insufficient_stability"


@pytest.mark.asyncio
async def test_judge_rollout_policy_holds_mode_during_cooldown(monkeypatch):
    monkeypatch.setattr(settings, "THEORY_USE_JUDGE", True)
    monkeypatch.setattr(settings, "THEORY_JUDGE_WARN_ONLY", True)
    monkeypatch.setattr(settings, "THEORY_JUDGE_STRICT_COHORT_PERCENT", 100)
    monkeypatch.setattr(settings, "THEORY_JUDGE_STRICT_WINDOW", 5)
    monkeypatch.setattr(settings, "THEORY_JUDGE_STRICT_MIN_THEORIES", 1)
    monkeypatch.setattr(settings, "THEORY_JUDGE_STRICT_PROMOTE_MAX_BAD_RUNS", 0)
    monkeypatch.setattr(settings, "THEORY_JUDGE_STRICT_DEGRADE_MIN_BAD_RUNS", 1)
    monkeypatch.setattr(settings, "THEORY_JUDGE_STRICT_COOLDOWN_RUNS", 3)
    monkeypatch.setattr(settings, "THEORY_JUDGE_STRICT_MAX_MODE_CHANGES_PER_WINDOW", 1)
    monkeypatch.setattr(settings, "THEORY_EVIDENCE_MIN_INTERVIEWS", 4)
    monkeypatch.setattr(settings, "THEORY_EVIDENCE_TARGET_MIN", 30)

    pipeline = TheoryPipeline()
    project_id = uuid.uuid4()
    db = AsyncMock()
    db.execute = AsyncMock(
        return_value=_ScalarsResult(
            [
                {
                    "judge": {"warn_only": False},
                    "judge_rollout": {
                        "effective_warn_only": False,
                        "mode_changed": True,
                        "runs_since_last_change": 0,
                    },
                    "claim_metrics": {"claims_without_evidence": 2, "interviews_covered": 1},
                    "quality_metrics": {"evidence_index_size": 5},
                }
            ]
        )
    )

    policy = await pipeline._resolve_judge_rollout_policy(project_id=project_id, db=db)
    assert policy["effective_warn_only"] is False
    assert policy["mode"] == "strict"
    assert policy["cooldown_active"] is True
    assert policy["reason"] == "mode_change_cooldown"
