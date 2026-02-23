import json
from json import JSONDecodeError


def _extract_json_candidate(raw: str) -> str:
    """Extract the first JSON object/array candidate from a noisy model output."""
    if not raw:
        return raw
    start_obj = raw.find("{")
    start_arr = raw.find("[")
    starts = [idx for idx in (start_obj, start_arr) if idx >= 0]
    if not starts:
        return raw.strip()
    start = min(starts)
    return raw[start:].strip()


def _escape_control_chars_in_json(raw: str) -> str:
    """
    Escape control chars inside quoted JSON strings and remove invalid raw controls
    outside strings (except standard whitespace separators).
    """
    out = []
    in_string = False
    escaped = False

    for ch in raw:
        code = ord(ch)
        if in_string:
            if escaped:
                out.append(ch)
                escaped = False
                continue
            if ch == "\\":
                out.append(ch)
                escaped = True
                continue
            if ch == '"':
                out.append(ch)
                in_string = False
                continue
            if code < 0x20:
                if ch == "\n":
                    out.append("\\n")
                elif ch == "\r":
                    out.append("\\r")
                elif ch == "\t":
                    out.append("\\t")
                else:
                    out.append(f"\\u{code:04x}")
                continue
            out.append(ch)
            continue

        # Outside string
        if ch == '"':
            out.append(ch)
            in_string = True
            escaped = False
            continue
        if code < 0x20 and ch not in ("\n", "\r", "\t", " "):
            # Invalid raw control outside strings for JSON text; drop it.
            continue
        out.append(ch)
    return "".join(out)


def safe_json_loads(raw: str):
    """Robust JSON decoder for LLM outputs with common formatting defects."""
    candidate = _extract_json_candidate(raw or "")
    try:
        return json.loads(candidate)
    except JSONDecodeError:
        cleaned = _escape_control_chars_in_json(candidate)
        return json.loads(cleaned)
