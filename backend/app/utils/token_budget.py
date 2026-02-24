from __future__ import annotations

from typing import Any, Callable, Dict, List, Tuple


def estimate_tokens(text: str, model: str = "") -> int:
    """
    Approximate token count.
    - Preferred: tiktoken (when available)
    - Fallback: chars/4 heuristic
    """
    if not text:
        return 0
    try:
        import tiktoken  # type: ignore

        if model:
            try:
                enc = tiktoken.encoding_for_model(model)
            except Exception:
                enc = tiktoken.get_encoding("cl100k_base")
        else:
            enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:
        return max(1, len(text) // 4)


def estimate_messages_tokens(messages: List[Dict[str, Any]], model: str = "") -> int:
    total = 0
    for msg in messages:
        role = str(msg.get("role", ""))
        content = str(msg.get("content", ""))
        total += estimate_tokens(role, model)
        total += estimate_tokens(content, model)
        # conservative overhead per message
        total += 6
    # reply priming overhead
    return total + 3


def fits_context(
    messages: List[Dict[str, Any]],
    model: str,
    context_limit: int,
    max_output_tokens: int,
    margin_tokens: int = 2000,
) -> bool:
    input_tokens = estimate_messages_tokens(messages, model)
    return (input_tokens + max_output_tokens + margin_tokens) <= context_limit


def ensure_within_budget(
    messages_builder: Callable[[], List[Dict[str, Any]]],
    model: str,
    context_limit: int,
    max_output_tokens: int,
    degrade_cb: Callable[[], Dict[str, Any] | None],
    margin_tokens: int = 2000,
    max_degradation_steps: int = 6,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Build messages and progressively degrade payload (local trims) until context fits.
    """
    debug: Dict[str, Any] = {
        "model": model,
        "context_limit": context_limit,
        "max_output_tokens": max_output_tokens,
        "margin_tokens": margin_tokens,
        "attempts": 0,
        "degradation_steps": [],
        "input_tokens_estimate": 0,
        "fits": False,
    }

    messages = messages_builder()
    for attempt in range(max_degradation_steps + 1):
        debug["attempts"] = attempt + 1
        input_tokens = estimate_messages_tokens(messages, model)
        debug["input_tokens_estimate"] = input_tokens
        if (input_tokens + max_output_tokens + margin_tokens) <= context_limit:
            debug["fits"] = True
            return messages, debug

        if attempt >= max_degradation_steps:
            break

        step_result = degrade_cb()
        if not step_result:
            break
        debug["degradation_steps"].append(step_result)
        messages = messages_builder()

    return messages, debug
