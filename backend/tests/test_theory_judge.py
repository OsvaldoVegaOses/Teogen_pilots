from app.engines.theory_judge import TheoryJudge


def _base_paradigm(evidence_ids):
    return {
        "conditions": [{"name": "Condicion A", "evidence_ids": [evidence_ids[0]]}],
        "actions": [{"name": "Accion A", "evidence_ids": [evidence_ids[1]]}],
        "context": [{"name": "Contexto A", "evidence_ids": [evidence_ids[0]]}],
        "intervening_conditions": [{"name": "Interv A", "evidence_ids": [evidence_ids[1]]}],
        "consequences": [
            {"name": "Impacto material", "type": "material", "horizon": "corto_plazo", "evidence_ids": [evidence_ids[0]]},
            {"name": "Impacto social", "type": "social", "horizon": "largo_plazo", "evidence_ids": [evidence_ids[1]]},
            {"name": "Impacto institucional", "type": "institutional", "horizon": "corto_plazo", "evidence_ids": [evidence_ids[0]]},
            {"name": "Impacto social 2", "type": "social", "horizon": "corto_plazo", "evidence_ids": [evidence_ids[1]]},
            {"name": "Impacto material 2", "type": "material", "horizon": "largo_plazo", "evidence_ids": [evidence_ids[0]]},
        ],
        "propositions": [{"text": f"P{i}", "evidence_ids": [evidence_ids[i % len(evidence_ids)]]} for i in range(5)],
    }


def test_judge_adaptive_min_interviews_does_not_block_small_projects():
    evidence_ids = ["f1", "f2"]
    paradigm = _base_paradigm(evidence_ids)
    fragment_to_interview = {"f1": "i1", "f2": "i2"}

    judge = TheoryJudge(
        min_interviews=4,
        adaptive_thresholds=True,
        available_interviews=2,
        min_interviews_floor=1,
        min_interviews_ratio=0.6,
    )
    result = judge.evaluate(
        paradigm=paradigm,
        fragment_to_interview=fragment_to_interview,
        missing_evidence_ids=[],
    )

    assert result["ok"] is True
    assert result["stats"]["min_interviews_effective"] == 2
    assert not any(err.get("code") == "COVERAGE_MIN_INTERVIEWS" for err in result["errors"])


def test_judge_non_adaptive_keeps_strict_coverage():
    evidence_ids = ["f1", "f2"]
    paradigm = _base_paradigm(evidence_ids)
    fragment_to_interview = {"f1": "i1", "f2": "i2"}

    judge = TheoryJudge(
        min_interviews=4,
        adaptive_thresholds=False,
        available_interviews=2,
    )
    result = judge.evaluate(
        paradigm=paradigm,
        fragment_to_interview=fragment_to_interview,
        missing_evidence_ids=[],
    )

    assert result["ok"] is False
    assert any(err.get("code") == "COVERAGE_MIN_INTERVIEWS" for err in result["errors"])


def test_judge_balance_consequences_becomes_warning_when_evidence_is_low():
    paradigm = {
        "conditions": [{"name": "Condicion A", "evidence_ids": ["f1"]}],
        "actions": [{"name": "Accion A", "evidence_ids": ["f1"]}],
        "context": [{"name": "Contexto A", "evidence_ids": ["f1"]}],
        "intervening_conditions": [{"name": "Interv A", "evidence_ids": ["f1"]}],
        "consequences": [{"name": "Impacto social", "type": "social", "horizon": "corto_plazo", "evidence_ids": ["f1"]}],
        "propositions": [{"text": f"P{i}", "evidence_ids": ["f1"]} for i in range(5)],
    }
    judge = TheoryJudge(
        min_interviews=1,
        adaptive_thresholds=True,
        available_interviews=1,
        balance_min_evidence=12,
    )
    result = judge.evaluate(
        paradigm=paradigm,
        fragment_to_interview={"f1": "i1"},
        missing_evidence_ids=[],
    )

    assert not any(err.get("code") == "BALANCE_CONSEQUENCES" for err in result["errors"])
    assert any(w.get("code") == "BALANCE_CONSEQUENCES_WARN" for w in result["warnings"])
