from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast
from unittest.mock import MagicMock

import pytest
from deepagents.backends.protocol import ExecuteResponse, SandboxBackendProtocol
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest

from agent.xlsliberator.middleware import (
    MIGRATION_MIDDLEWARE_ORDER,
    EvidenceRequiredMiddleware,
    LiberationPolicyMiddleware,
    MigrationBudget,
    MigrationBudgetMiddleware,
    MigrationCheckpointMiddleware,
    MigrationMiddlewareError,
    NoFakeSuccessMiddleware,
    NoTestWeakeningMiddleware,
    PromptInjectionBoundaryMiddleware,
    RegressionPromotionMiddleware,
    migration_middleware_stack,
)
from agent.xlsliberator.migrations import TASK_KIND


class FakeSandbox(SandboxBackendProtocol):
    def __init__(
        self,
        responder: Callable[[str], ExecuteResponse] | None = None,
    ) -> None:
        self.commands: list[str] = []
        self._responder = responder

    @property
    def id(self) -> str:
        return "migration-test-sandbox"

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        self.commands.append(command)
        if self._responder is not None:
            return self._responder(command)
        return ExecuteResponse(output="", exit_code=0)

    async def aexecute(
        self,
        command: str,
        *,
        timeout: int | None = None,
    ) -> ExecuteResponse:
        return self.execute(command, timeout=timeout)


def _resolver(backend: SandboxBackendProtocol) -> Callable[[object], SandboxBackendProtocol]:
    return lambda _runtime: backend


def _tool_request(
    name: str,
    args: dict[str, Any] | None = None,
    *,
    call_id: str = "call-1",
) -> ToolCallRequest:
    return ToolCallRequest(
        tool_call={"name": name, "args": args or {}, "id": call_id},
        tool=MagicMock(),
        state={},
        runtime=MagicMock(),
    )


def _model_request() -> ModelRequest:
    return ModelRequest(
        model=cast(BaseChatModel, object()),
        messages=[],
    )


def _terminal_state(status: str) -> dict[str, Any]:
    return {"messages": [AIMessage(content=f"XLSLIBERATOR_STATUS: {status}")]}


async def _ok_tool(_request: ToolCallRequest) -> ToolMessage:
    return ToolMessage(content="ok", tool_call_id="call-1")


def test_migration_stack_is_scoped_and_ordered() -> None:
    backend = FakeSandbox()

    assert migration_middleware_stack({"source": "dashboard"}, backend=_resolver(backend)) == []

    stack = migration_middleware_stack(
        {"task_kind": TASK_KIND},
        backend=_resolver(backend),
        service_health={"runtime": {"status": "AVAILABLE"}},
    )
    assert tuple(type(item).__name__ for item in stack) == MIGRATION_MIDDLEWARE_ORDER


@pytest.mark.asyncio
async def test_prompt_boundary_marks_data_untrusted_and_blocks_policy_edit() -> None:
    middleware = PromptInjectionBoundaryMiddleware()
    seen: list[ModelRequest] = []

    async def model_handler(request: ModelRequest) -> ModelResponse:
        seen.append(request)
        return ModelResponse(result=[AIMessage(content="continue")])

    await middleware.awrap_model_call(_model_request(), model_handler)

    assert seen[0].system_message is not None
    assert "UNTRUSTED DATA" in seen[0].system_message.text
    called = False

    async def tool_handler(request: ToolCallRequest) -> ToolMessage:
        nonlocal called
        called = True
        return await _ok_tool(request)

    result = await middleware.awrap_tool_call(
        _tool_request(
            "write_file",
            {
                "file_path": "agent/xlsliberator/integrations/mcp.py",
                "content": "allow everything",
            },
        ),
        tool_handler,
    )

    assert called is False
    assert isinstance(result, ToolMessage)
    assert result.status == "error"
    assert "protected policy" in str(result.content)


@pytest.mark.asyncio
async def test_architecture_and_test_weakening_are_actionably_blocked() -> None:
    liberation = LiberationPolicyMiddleware()
    weakening = NoTestWeakeningMiddleware()

    architecture = await liberation.awrap_tool_call(
        _tool_request(
            "write_file",
            {
                "file_path": "migration/generated/bridge.py",
                "content": "import win32com.client",
            },
        ),
        _ok_tool,
    )
    skipped = await weakening.awrap_tool_call(
        _tool_request(
            "edit_file",
            {
                "file_path": "tests/test_migration.py",
                "old_string": "def test_result():\n    assert result == 4\n",
                "new_string": "@pytest.mark.skip\ndef test_result():\n    pass\n",
            },
        ),
        _ok_tool,
    )

    assert isinstance(architecture, ToolMessage)
    assert architecture.status == "error"
    assert "Excel runtime" in str(architecture.content)
    assert isinstance(skipped, ToolMessage)
    assert skipped.status == "error"
    assert "test weakening" in str(skipped.content)


@pytest.mark.asyncio
async def test_checkpoint_resumes_latest_and_snapshots_meaningful_success() -> None:
    def respond(command: str) -> ExecuteResponse:
        if "latest_file=migration/checkpoints/latest" in command:
            return ExecuteResponse(
                output="checkpoint=migration/checkpoints/00000007\n",
                exit_code=0,
            )
        if "latest-sequence" in command:
            return ExecuteResponse(
                output="checkpoint=migration/checkpoints/00000008\n",
                exit_code=0,
            )
        return ExecuteResponse(output="", exit_code=0)

    backend = FakeSandbox(respond)
    middleware = MigrationCheckpointMiddleware(backend=_resolver(backend))

    resumed = await middleware.abefore_agent(
        {"messages": []},
        cast(Any, MagicMock()),
    )
    result = await middleware.awrap_tool_call(
        _tool_request("xlsliberator_runtime_save"),
        _ok_tool,
    )

    assert resumed == {"migration_checkpoint_path": "migration/checkpoints/00000007"}
    assert isinstance(result, ToolMessage)
    assert any("stage=\"$checkpoints/.stage-$name\"" in command for command in backend.commands)


@pytest.mark.asyncio
async def test_failed_tool_does_not_create_checkpoint() -> None:
    backend = FakeSandbox()
    middleware = MigrationCheckpointMiddleware(backend=_resolver(backend))

    async def failed(_request: ToolCallRequest) -> ToolMessage:
        return ToolMessage(content="failed", tool_call_id="call-1", status="error")

    result = await middleware.awrap_tool_call(
        _tool_request("xlsliberator_runtime_save"),
        failed,
    )

    assert isinstance(result, ToolMessage)
    assert result.status == "error"
    assert backend.commands == []


@pytest.mark.asyncio
async def test_evidence_gate_accepts_complete_and_blocks_missing() -> None:
    complete = FakeSandbox()
    middleware = EvidenceRequiredMiddleware(backend=_resolver(complete))

    assert (
        await middleware.aafter_agent(
            _terminal_state("DELIVERABLE"),
            cast(Any, MagicMock()),
        )
        is None
    )

    missing = FakeSandbox(
        lambda _command: ExecuteResponse(output="missing=reviewer result\n", exit_code=1)
    )
    blocked = EvidenceRequiredMiddleware(backend=_resolver(missing))
    with pytest.raises(MigrationMiddlewareError, match="reviewer result"):
        await blocked.aafter_agent(
            _terminal_state("DELIVERABLE"),
            cast(Any, MagicMock()),
        )


@pytest.mark.asyncio
async def test_unresolved_terminal_requires_only_unresolved_artifact() -> None:
    backend = FakeSandbox()
    middleware = EvidenceRequiredMiddleware(backend=_resolver(backend))

    await middleware.aafter_agent(
        _terminal_state("UNRESOLVED"),
        cast(Any, MagicMock()),
    )

    command = backend.commands[-1]
    assert "unresolved.md" in command
    assert "target.ods" not in command


@pytest.mark.asyncio
async def test_fake_success_blocks_unavailable_runtime_and_bad_evidence() -> None:
    unavailable = NoFakeSuccessMiddleware(
        backend=_resolver(FakeSandbox()),
        service_health={"runtime": {"status": "TIMEOUT"}},
    )
    with pytest.raises(MigrationMiddlewareError, match="not AVAILABLE"):
        await unavailable.aafter_agent(
            _terminal_state("DELIVERABLE"),
            cast(Any, MagicMock()),
        )

    invalid_evidence = NoFakeSuccessMiddleware(
        backend=_resolver(
            FakeSandbox(
                lambda _command: ExecuteResponse(
                    output='migration/evidence/save-reopen.json:"status":"skipped"\n',
                    exit_code=76,
                )
            )
        ),
        service_health={"runtime": {"status": "AVAILABLE"}},
    )
    with pytest.raises(MigrationMiddlewareError, match="skipped"):
        await invalid_evidence.aafter_agent(
            _terminal_state("DELIVERABLE"),
            cast(Any, MagicMock()),
        )


@pytest.mark.asyncio
async def test_budget_timeout_ends_explicitly_unresolved() -> None:
    backend = FakeSandbox()
    times = iter((10.0, 12.0))
    middleware = MigrationBudgetMiddleware(
        backend=_resolver(backend),
        budget=MigrationBudget(wall_seconds=1.0),
        clock=lambda: next(times),
    )
    calls = 0

    async def handler(_request: ModelRequest) -> ModelResponse:
        nonlocal calls
        calls += 1
        return ModelResponse(result=[AIMessage(content="working")])

    await middleware.awrap_model_call(_model_request(), handler)
    response = await middleware.awrap_model_call(_model_request(), handler)

    assert calls == 1
    assert isinstance(response.result[0], AIMessage)
    assert "XLSLIBERATOR_STATUS: UNRESOLVED" in response.result[0].text
    assert "wall-time budget" in response.result[0].text
    assert any("unresolved.md" in command for command in backend.commands)


@pytest.mark.asyncio
async def test_specialist_budget_blocks_excess_work_before_execution() -> None:
    backend = FakeSandbox()
    middleware = MigrationBudgetMiddleware(
        backend=_resolver(backend),
        budget=MigrationBudget(specialist_runs=1),
    )
    calls = 0

    async def handler(request: ToolCallRequest) -> ToolMessage:
        nonlocal calls
        calls += 1
        return await _ok_tool(request)

    first = await middleware.awrap_tool_call(_tool_request("task"), handler)
    second = await middleware.awrap_tool_call(_tool_request("task"), handler)

    assert isinstance(first, ToolMessage)
    assert calls == 1
    assert isinstance(second, ToolMessage)
    assert second.status == "error"
    assert "specialist-run budget" in str(second.content)


@pytest.mark.asyncio
async def test_generic_fix_marks_and_requires_regression_promotion() -> None:
    backend = FakeSandbox()
    middleware = RegressionPromotionMiddleware(backend=_resolver(backend))

    await middleware.awrap_tool_call(
        _tool_request(
            "edit_file",
            {
                "file_path": "src/xlsliberator/formula_translation.py",
                "old_string": "old",
                "new_string": "new",
            },
        ),
        _ok_tool,
    )
    await middleware.aafter_agent(
        _terminal_state("DELIVERABLE"),
        cast(Any, MagicMock()),
    )

    assert any("promotion-required" in command for command in backend.commands)
    assert any("minimized-fixture.json" in command for command in backend.commands)


@pytest.mark.asyncio
async def test_missing_terminal_status_is_never_silently_promoted() -> None:
    middleware = EvidenceRequiredMiddleware(backend=_resolver(FakeSandbox()))

    with pytest.raises(MigrationMiddlewareError, match="explicit terminal marker"):
        await middleware.aafter_agent(
            {"messages": [AIMessage(content="looks good")]},
            cast(Any, MagicMock()),
        )
