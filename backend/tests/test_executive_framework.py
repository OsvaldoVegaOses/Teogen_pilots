from app.services.export.executive_framework import build_executive_framework


def test_executive_framework_go_when_quality_is_clean():
    theory_data = {
        "model_json": {
            "conditions": [{"name": "Cond A", "evidence_ids": ["f1"]}],
            "actions": [{"name": "Act A", "evidence_ids": ["f2"]}],
            "consequences": [{"name": "Cons A", "evidence_ids": ["f3"]}],
            "propositions": [{"text": "Si X entonces Y", "evidence_ids": ["f4"]}],
            "context": [],
            "intervening_conditions": [],
        },
        "validation": {
            "claim_metrics": {
                "claims_count": 4,
                "claims_without_evidence": 0,
                "interviews_covered": 4,
            },
            "judge": {"warn_only": False},
        },
        "gaps": [],
    }
    result = build_executive_framework(theory_data)
    assert result["recommendation"] == "GO"
    assert result["quality_metrics"]["claims_without_evidence"] == 0


def test_executive_framework_pilot_when_warn_only_or_high_gap():
    theory_data = {
        "validation": {
            "claim_metrics": {
                "claims_count": 10,
                "claims_without_evidence": 0,
                "interviews_covered": 3,
            },
            "judge": {"warn_only": True},
        },
        "gaps": [{"severity": "high", "gap_description": "Falta contraste por actor"}],
    }
    result = build_executive_framework(theory_data)
    assert result["recommendation"] == "PILOT"
    assert any("warn-only" in reason for reason in result["reasons"])


def test_executive_framework_no_go_when_missing_evidence_is_high():
    theory_data = {
        "validation": {
            "claim_metrics": {
                "claims_count": 10,
                "claims_without_evidence": 4,
                "interviews_covered": 2,
            },
            "judge": {"warn_only": False},
        },
        "gaps": [],
    }
    result = build_executive_framework(theory_data)
    assert result["recommendation"] == "NO_GO"
    assert result["quality_metrics"]["claims_without_evidence"] == 4

