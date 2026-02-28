import pytest
from io import BytesIO
from unittest.mock import AsyncMock

from app.services.export_service import export_service


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
            "consequences": "Some consequences",
        },
        "propositions": ["Prop 1", "Prop 2"],
        "gaps": ["Gap 1"],
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
        "gaps": [],
    }
    pdf_buffer = await export_service.generate_theory_pdf("EN Project", "en", theory_data)
    assert isinstance(pdf_buffer, BytesIO)
    assert len(pdf_buffer.getvalue()) > 0


def test_i18n_keys():
    from app.services.export_service import I18N

    assert "es" in I18N
    assert "en" in I18N
    assert "Informe de Teor" in I18N["es"]["report_title"]
    assert I18N["en"]["report_title"] == "Grounded Theory Report"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fmt,method_name,expected_extension,expected_content_type",
    [
        (
            "pptx",
            "generate_theory_pptx",
            "pptx",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ),
        (
            "xlsx",
            "generate_theory_xlsx",
            "xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ),
        ("png", "generate_theory_infographic", "png", "image/png"),
    ],
)
async def test_generate_theory_report_dispatches_non_pdf_formats(
    fmt, method_name, expected_extension, expected_content_type, monkeypatch
):
    buffer = BytesIO(f"mock-{fmt}".encode("utf-8"))
    generator_mock = AsyncMock(return_value=buffer)
    monkeypatch.setattr(export_service, method_name, generator_mock)

    report_buffer, extension, content_type = await export_service.generate_theory_report(
        project_name="Proyecto X",
        language="es",
        theory_data={"model_json": {}},
        format=fmt,
        template_key="consulting",
    )

    assert report_buffer is buffer
    assert extension == expected_extension
    assert content_type == expected_content_type
    generator_mock.assert_awaited_once_with("Proyecto X", {"model_json": {}}, "consulting")


@pytest.mark.asyncio
async def test_generate_theory_report_raises_for_unsupported_format():
    with pytest.raises(ValueError, match="Unsupported export format"):
        await export_service.generate_theory_report(
            project_name="Proyecto X",
            language="es",
            theory_data={"model_json": {}},
            format="docx",
            template_key="generic",
        )
