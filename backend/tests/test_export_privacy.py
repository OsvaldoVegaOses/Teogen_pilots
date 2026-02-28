from app.services.export.privacy import detect_pii_types, redact_pii_text


def test_redact_pii_email_phone_rut_and_long_id():
    text = (
        "Contacto: maria.perez@example.org, telefono +56 9 8765 4321, "
        "RUT 12.345.678-5, folio 123456789."
    )
    out = redact_pii_text(text)
    assert "[REDACTED_EMAIL]" in out
    assert "[REDACTED_PHONE]" in out
    assert "[REDACTED_RUT]" in out
    assert "[REDACTED_ID]" in out
    assert "example.org" not in out
    assert "12.345.678-5" not in out


def test_redact_pii_no_change_when_no_sensitive_tokens():
    text = "Informe cualitativo con hallazgos por categoria y evidencia."
    out = redact_pii_text(text)
    assert out == text


def test_detect_pii_types_returns_expected_labels():
    text = "mail: test@correo.cl, rut 12.345.678-5, tel +56 9 1111 2222, id 12345678"
    types = detect_pii_types(text)
    assert "email" in types
    assert "rut" in types
    assert "phone" in types
    assert "id" in types
