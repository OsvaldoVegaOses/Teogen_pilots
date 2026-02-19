import pytest
from app.services.export_service import export_service
from io import BytesIO

@pytest.mark.asyncio
async def test_generate_theory_pdf_success():
    # Mock data
    project_name = "Test Project"
    language = "es"
    theory_data = {
        "version": 1,
        "confidence_score": 0.85,
        "generated_by": "Test AI",
        "model_json": {
            "selected_central_category": "Cat Central",
            "conditions": "Some conditions",
            "actions": "Some actions",
            "consequences": "Some consequences"
        },
        "propositions": ["Prop 1", "Prop 2"],
        "gaps": ["Gap 1"]
    }

    pdf_buffer = await export_service.generate_theory_pdf(project_name, language, theory_data)
    
    assert isinstance(pdf_buffer, BytesIO)
    content = pdf_buffer.getvalue()
    assert len(content) > 0
    # PDF files start with %PDF
    assert content.startswith(b"%PDF")

@pytest.mark.asyncio
async def test_generate_theory_pdf_english():
    theory_data = {
        "model_json": {"selected_central_category": "Central Cat"},
        "propositions": [],
        "gaps": []
    }
    pdf_buffer = await export_service.generate_theory_pdf("EN Project", "en", theory_data)
    assert isinstance(pdf_buffer, BytesIO)
    assert len(pdf_buffer.getvalue()) > 0

def test_i18n_keys():
    from app.services.export_service import I18N
    assert "es" in I18N
    assert "en" in I18N
    assert I18N["es"]["report_title"] == "Informe de Teoría Fundamentada"
    assert I18N["en"]["report_title"] == "Grounded Theory Report"
