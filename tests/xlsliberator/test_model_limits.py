"""Public-showcase model budget tests."""

from unittest.mock import patch

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, ToolMessage

from agent.xlsliberator.model_limits import (
    SHOWCASE_CONTEXT_WINDOW_TOKENS,
    SHOWCASE_HISTORY_GROUPS,
    SHOWCASE_MAX_INPUT_TOKENS,
    SHOWCASE_MAX_OUTPUT_TOKENS,
    SHOWCASE_OLD_TOOL_RESULT_CHARS,
    SHOWCASE_TASK_DESCRIPTION,
    bound_showcase_model_kwargs,
    compact_showcase_messages,
    is_binary_artifact_path,
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


def test_showcase_context_keeps_tool_call_pairs_and_bounds_old_results() -> None:
    messages: list[AnyMessage] = [HumanMessage(content="migrate workbook")]
    for index in range(SHOWCASE_HISTORY_GROUPS + 2):
        tool_call_id = f"call-{index}"
        messages.extend(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "read_file",
                            "args": {"file_path": f"/workspace/source/{'x' * 500}.txt"},
                            "id": tool_call_id,
                            "type": "tool_call",
                        }
                    ],
                ),
                ToolMessage(content="evidence " * 1_000, tool_call_id=tool_call_id),
            ]
        )

    compacted = compact_showcase_messages(messages)

    assert compacted[0].content == "migrate workbook"
    assert sum(isinstance(message, AIMessage) for message in compacted) == SHOWCASE_HISTORY_GROUPS
    calls = {
        tool_call["id"]
        for message in compacted
        if isinstance(message, AIMessage)
        for tool_call in message.tool_calls
    }
    results = {message.tool_call_id for message in compacted if isinstance(message, ToolMessage)}
    assert calls == results
    old_result = next(message for message in compacted if isinstance(message, ToolMessage))
    assert len(str(old_result.content)) <= SHOWCASE_OLD_TOOL_RESULT_CHARS + 30


def test_showcase_context_removes_binary_payload_blocks() -> None:
    compacted = compact_showcase_messages(
        [
            HumanMessage(content="inspect"),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "read_file",
                        "args": {"file_path": "/workspace/source/book.xlsb"},
                        "id": "binary-call",
                        "type": "tool_call",
                    }
                ],
            ),
            ToolMessage(
                content=[
                    {"type": "text", "text": "metadata"},
                    {"type": "file", "base64": "A" * 20_000},
                ],
                tool_call_id="binary-call",
            ),
        ]
    )

    tool_result = compacted[-1]
    assert isinstance(tool_result, ToolMessage)
    assert "metadata" in str(tool_result.content)
    assert "binary artifact omitted" in str(tool_result.content)
    assert "A" * 100 not in str(tool_result.content)


def test_binary_artifact_paths_require_runtime_inspection() -> None:
    assert is_binary_artifact_path("/workspace/source/book.XLSB")
    assert is_binary_artifact_path("/workspace/output/replay.webm")
    assert not is_binary_artifact_path("/workspace/source/vba/Game.bas")
