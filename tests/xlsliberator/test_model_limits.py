"""Public-showcase model budget tests."""

from agent.xlsliberator.model_limits import (
    SHOWCASE_CONTEXT_WINDOW_TOKENS,
    SHOWCASE_MAX_INPUT_TOKENS,
    SHOWCASE_MAX_OUTPUT_TOKENS,
    bound_showcase_model_kwargs,
    showcase_system_prompt,
)


def test_showcase_model_budget_matches_github_models_limit() -> None:
    bounded = bound_showcase_model_kwargs({"max_tokens": 32_768})

    assert SHOWCASE_CONTEXT_WINDOW_TOKENS == 8_000
    assert SHOWCASE_MAX_INPUT_TOKENS + SHOWCASE_MAX_OUTPUT_TOKENS == 8_000
    assert bounded["max_tokens"] == SHOWCASE_MAX_OUTPUT_TOKENS
    assert bounded["profile"] == {
        "max_input_tokens": SHOWCASE_MAX_INPUT_TOKENS,
        "max_output_tokens": SHOWCASE_MAX_OUTPUT_TOKENS,
        "text_inputs": True,
        "text_outputs": True,
        "tool_calling": True,
        "structured_output": True,
    }


def test_showcase_prompt_drops_general_coding_base() -> None:
    assert showcase_system_prompt() == {"base": None}
    assert showcase_system_prompt("review") == {"base": None, "prefix": "review"}
