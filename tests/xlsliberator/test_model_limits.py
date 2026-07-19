"""Public-showcase model budget tests."""

from unittest.mock import patch

from agent.xlsliberator.model_limits import (
    SHOWCASE_CONTEXT_WINDOW_TOKENS,
    SHOWCASE_MAX_INPUT_TOKENS,
    SHOWCASE_MAX_OUTPUT_TOKENS,
    SHOWCASE_TASK_DESCRIPTION,
    bound_showcase_model_kwargs,
    register_showcase_harness_profile,
    showcase_system_prompt,
)


def test_showcase_model_budget_matches_github_models_limit() -> None:
    bounded = bound_showcase_model_kwargs({"max_tokens": 32_768})

    assert SHOWCASE_CONTEXT_WINDOW_TOKENS == 8_000
    assert SHOWCASE_MAX_INPUT_TOKENS + SHOWCASE_MAX_OUTPUT_TOKENS == 8_000
    assert bounded.get("max_tokens") == SHOWCASE_MAX_OUTPUT_TOKENS
    assert bounded.get("profile") == {
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


def test_showcase_harness_removes_general_agent_and_large_tool_surface() -> None:
    with patch("agent.xlsliberator.model_limits.register_harness_profile") as register:
        register_showcase_harness_profile()

    profile = register.call_args.args[1]
    assert profile.general_purpose_subagent is not None
    assert profile.general_purpose_subagent.enabled is False
    assert profile.tool_description_overrides["task"] == SHOWCASE_TASK_DESCRIPTION
    assert profile.excluded_tools == frozenset({"delete", "glob", "grep"})
