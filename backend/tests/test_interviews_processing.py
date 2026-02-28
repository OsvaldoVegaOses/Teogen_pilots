from app.api.interviews import _segments_from_full_text


def test_segments_from_full_text_returns_empty_for_blank_input():
    assert _segments_from_full_text("") == []
    assert _segments_from_full_text("   \n\t   ") == []


def test_segments_from_full_text_generates_fallback_segments():
    text = (
        "Primera idea con evidencia concreta. "
        "Segunda idea para mantener trazabilidad. "
        "Tercera idea para completar el bloque.\n\n"
        "Cuarta idea en otro parrafo para validar separacion."
    )

    segments = _segments_from_full_text(text, max_chars=90)

    assert len(segments) >= 2
    assert all(str(seg.get("text") or "").strip() for seg in segments)
    assert all(seg.get("speaker") == "Unknown" for seg in segments)


def test_segments_from_full_text_splits_very_long_sentence():
    long_sentence = "a" * 1000

    segments = _segments_from_full_text(long_sentence, max_chars=200)

    assert len(segments) == 5
    assert all(len(seg.get("text") or "") <= 200 for seg in segments)
