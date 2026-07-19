"""Bounded model configuration for the public autonomous showcase."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any, Final

from deepagents import (
    GeneralPurposeSubagentProfile,
    HarnessProfile,
    SystemPromptConfig,
    register_harness_profile,
)
from langchain.agents.middleware.types import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.language_models import ModelProfile
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command

from ..utils.model import ModelKwargs

SHOWCASE_CONTEXT_WINDOW_TOKENS: Final[int] = 8_000
SHOWCASE_MAX_OUTPUT_TOKENS: Final[int] = 768
SHOWCASE_MAX_INPUT_TOKENS: Final[int] = SHOWCASE_CONTEXT_WINDOW_TOKENS - SHOWCASE_MAX_OUTPUT_TOKENS
SHOWCASE_HISTORY_GROUPS: Final[int] = 4
SHOWCASE_RECENT_TOOL_RESULTS: Final[int] = 2
SHOWCASE_RECENT_TOOL_RESULT_CHARS: Final[int] = 1_800
SHOWCASE_OLD_TOOL_RESULT_CHARS: Final[int] = 240
SHOWCASE_MESSAGE_CHARS: Final[int] = 1_200
SHOWCASE_TOOL_ARGUMENT_CHARS: Final[int] = 240
SHOWCASE_TASK_DESCRIPTION: Final[str] = (
    "Delegate one independent workbook-migration task. Available specialists:\n{available_agents}"
)
_BINARY_ARTIFACT_SUFFIXES: Final[frozenset[str]] = frozenset(
    {
        ".bin",
        ".gif",
        ".jpeg",
        ".jpg",
        ".mp4",
        ".ods",
        ".pdf",
        ".png",
        ".webm",
        ".webp",
        ".xls",
        ".xlsb",
        ".xlsm",
        ".xlsx",
        ".zip",
    }
)
_BINARY_OMISSION = (
    "[binary artifact omitted: inspect it through bounded XLSLiberator runtime metadata]"
)


def _truncate_text(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return f"{value[:limit]}...[bounded context omitted]"


def _truncate_value(value: Any, limit: int) -> Any:  # noqa: ANN401
    if isinstance(value, str):
        return _truncate_text(value, limit)
    if isinstance(value, Mapping):
        return {str(key): _truncate_value(item, limit) for key, item in value.items()}
    if isinstance(value, list):
        return [_truncate_value(item, limit) for item in value]
    if isinstance(value, tuple):
        return tuple(_truncate_value(item, limit) for item in value)
    return value


def _tool_content_text(content: str | list[str | dict[str, Any]]) -> str:
    if isinstance(content, str):
        return content
    text: list[str] = []
    binary = False
    for block in content:
        if isinstance(block, str):
            text.append(block)
            continue
        block_type = block.get("type")
        if (
            block_type in {"audio", "file", "image", "image_url", "video"}
            or "base64" in block
            or "blob" in block
        ):
            binary = True
            continue
        block_text = block.get("text")
        if isinstance(block_text, str):
            text.append(block_text)
            continue
        text.append(
            json.dumps(
                _truncate_value(block, SHOWCASE_TOOL_ARGUMENT_CHARS),
                sort_keys=True,
            )
        )
    if binary:
        text.append(_BINARY_OMISSION)
    return "\n".join(text)


def _message_groups(messages: Sequence[BaseMessage]) -> list[list[BaseMessage]]:
    groups: list[list[BaseMessage]] = []
    index = 0
    while index < len(messages):
        message = messages[index]
        group = [message]
        index += 1
        if isinstance(message, AIMessage) and message.tool_calls:
            tool_call_ids = {
                tool_call.get("id")
                for tool_call in message.tool_calls
                if isinstance(tool_call.get("id"), str)
            }
            while (
                index < len(messages)
                and isinstance(messages[index], ToolMessage)
                and messages[index].tool_call_id in tool_call_ids
            ):
                group.append(messages[index])
                index += 1
        groups.append(group)
    return groups


def compact_showcase_messages(messages: Sequence[BaseMessage]) -> list[BaseMessage]:
    """Bound provider input without separating assistant tool calls from their results."""

    groups = _message_groups(messages)
    selected = groups[-SHOWCASE_HISTORY_GROUPS:]
    if groups and isinstance(groups[0][0], HumanMessage) and groups[0] not in selected:
        selected = [groups[0], *selected]
    bounded = [message for group in selected for message in group]
    tool_positions = [
        index for index, message in enumerate(bounded) if isinstance(message, ToolMessage)
    ]
    recent_positions = set(tool_positions[-SHOWCASE_RECENT_TOOL_RESULTS:])

    compacted: list[BaseMessage] = []
    for index, message in enumerate(bounded):
        if isinstance(message, ToolMessage):
            limit = (
                SHOWCASE_RECENT_TOOL_RESULT_CHARS
                if index in recent_positions
                else SHOWCASE_OLD_TOOL_RESULT_CHARS
            )
            compacted.append(
                message.model_copy(
                    update={"content": _truncate_text(_tool_content_text(message.content), limit)}
                )
            )
            continue
        if isinstance(message, AIMessage):
            tool_calls = [
                {
                    **tool_call,
                    "args": _truncate_value(
                        tool_call.get("args", {}),
                        SHOWCASE_TOOL_ARGUMENT_CHARS,
                    ),
                }
                for tool_call in message.tool_calls
            ]
            content = (
                _truncate_text(message.content, SHOWCASE_MESSAGE_CHARS)
                if isinstance(message.content, str)
                else message.content
            )
            compacted.append(
                message.model_copy(update={"content": content, "tool_calls": tool_calls})
            )
            continue
        if isinstance(message.content, str):
            compacted.append(
                message.model_copy(
                    update={"content": _truncate_text(message.content, SHOWCASE_MESSAGE_CHARS)}
                )
            )
        else:
            compacted.append(message)
    return compacted


def is_binary_artifact_path(value: object) -> bool:
    """Return whether a filesystem read would inject opaque binary bytes."""

    if not isinstance(value, str):
        return False
    lowered = value.lower().split("?", maxsplit=1)[0]
    return any(lowered.endswith(suffix) for suffix in _BINARY_ARTIFACT_SUFFIXES)


class ShowcaseContextBudgetMiddleware(AgentMiddleware[Any, Any, Any]):
    """Keep the constrained public provider below its joint request budget."""

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        return await handler(request.override(messages=compact_showcase_messages(request.messages)))


class BinaryArtifactReadGuardMiddleware(AgentMiddleware[Any, Any, Any]):
    """Keep opaque workbooks and media behind bounded runtime inspection."""

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command]],
    ) -> ToolMessage | Command:
        tool_call = request.tool_call
        if isinstance(tool_call, Mapping) and tool_call.get("name") == "read_file":
            args = tool_call.get("args")
            file_path = args.get("file_path") if isinstance(args, Mapping) else None
            if is_binary_artifact_path(file_path):
                tool_call_id = tool_call.get("id")
                return ToolMessage(
                    content=json.dumps(
                        {
                            "status": "error",
                            "error": (
                                "Binary artifacts cannot be loaded into model context. "
                                "Use hydrated text evidence or authorized XLSLiberator runtime "
                                "inspection."
                            ),
                            "name": "read_file",
                        }
                    ),
                    tool_call_id=tool_call_id if isinstance(tool_call_id, str) else "",
                    status="error",
                )
        return await handler(request)


def showcase_model_profile() -> ModelProfile:
    """Describe the constrained GitHub Models endpoint used by the showcase."""

    return {
        "max_input_tokens": SHOWCASE_MAX_INPUT_TOKENS,
        "max_output_tokens": SHOWCASE_MAX_OUTPUT_TOKENS,
        "text_inputs": True,
        "text_outputs": True,
        "tool_calling": True,
        "structured_output": True,
    }


def bound_showcase_model_kwargs(kwargs: ModelKwargs) -> ModelKwargs:
    """Apply the endpoint's joint input and output budget."""

    bounded: ModelKwargs = kwargs.copy()
    bounded["max_tokens"] = SHOWCASE_MAX_OUTPUT_TOKENS
    bounded["profile"] = showcase_model_profile()
    return bounded


def showcase_system_prompt(prefix: str | None = None) -> SystemPromptConfig:
    """Drop the general coding base prompt from the bounded showcase graph."""

    prompt: SystemPromptConfig = {"base": None}
    if prefix:
        prompt["prefix"] = prefix
    return prompt


def register_showcase_harness_profile() -> None:
    """Remove unused general-agent context in the dedicated showcase process."""

    register_harness_profile(
        "openai",
        HarnessProfile(
            tool_description_overrides={"task": SHOWCASE_TASK_DESCRIPTION},
            excluded_tools=frozenset({"delete", "glob", "grep"}),
            general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False),
        ),
    )
