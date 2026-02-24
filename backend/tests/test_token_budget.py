from app.utils.token_budget import ensure_within_budget


def test_budget_no_change_when_under_limit():
    state = {"text": "short"}

    def builder():
        return [{"role": "user", "content": state["text"]}]

    def degrade():
        state["text"] = state["text"][:3]
        return {"changed": True}

    messages, debug = ensure_within_budget(
        messages_builder=builder,
        model="gpt-5.2-chat",
        context_limit=10000,
        max_output_tokens=100,
        degrade_cb=degrade,
        margin_tokens=50,
        max_degradation_steps=2,
    )

    assert debug["fits"] is True
    assert debug["degradation_steps"] == []
    assert messages[0]["content"] == "short"


def test_budget_degrades_when_over_limit():
    state = {"text": "x" * 16000}

    def builder():
        return [{"role": "user", "content": state["text"]}]

    def degrade():
        before = len(state["text"])
        if before <= 100:
            return None
        state["text"] = state["text"][: before // 2]
        return {"before": before, "after": len(state["text"])}

    _, debug = ensure_within_budget(
        messages_builder=builder,
        model="gpt-5.2-chat",
        context_limit=4000,
        max_output_tokens=500,
        degrade_cb=degrade,
        margin_tokens=200,
        max_degradation_steps=6,
    )

    assert debug["fits"] is True
    assert len(debug["degradation_steps"]) > 0
