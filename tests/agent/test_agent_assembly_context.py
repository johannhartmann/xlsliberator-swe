"""Assembly contract for the main agent's context-management + middleware wiring.

Locks in that `get_agent` hands an executable composite sandbox backend with a
writable artifact root to `create_deep_agent`. This makes DeepAgents auto-wire
filesystem eviction and summarization without trying to write below the
container's read-only root. The built-in `PatchToolCallsMiddleware` covers
orphaned tool-call repair.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from deepagents.backends import CompositeBackend
from deepagents.backends.protocol import SandboxBackendProtocol
from deepagents.middleware.filesystem import FilesystemMiddleware
from langgraph.graph.state import RunnableConfig

from agent.server import DEEPAGENT_ARTIFACT_ROOT, _resolve_agent_github_token, get_agent
from agent.xlsliberator.integrations.mcp import MigrationMCPRegistry


class _DummyAgent:
    def with_config(self, config: RunnableConfig) -> _DummyAgent:
        self.config = config
        return self


def _base_config() -> RunnableConfig:
    return {
        "configurable": {
            "__is_for_execution__": True,
            "thread_id": "thread-ctx",
            "github_login": "octocat",
        },
        "metadata": {},
    }


@pytest.mark.asyncio
async def test_migration_agent_does_not_resolve_github_credentials() -> None:
    resolver = AsyncMock(side_effect=AssertionError("migration requested GitHub credentials"))

    with patch("agent.server.resolve_github_token", resolver):
        token = await _resolve_agent_github_token(
            _base_config(),
            "thread-migration",
            {"runtime": {"status": "AVAILABLE"}},
        )

    assert token is None
    resolver.assert_not_awaited()


@pytest.mark.asyncio
async def test_repository_agent_keeps_github_authentication() -> None:
    resolver = AsyncMock(return_value=("ghp_user", None))

    with patch("agent.server.resolve_github_token", resolver):
        token = await _resolve_agent_github_token(
            _base_config(),
            "thread-repository",
            None,
        )

    assert token == "ghp_user"
    resolver.assert_awaited_once_with(_base_config(), "thread-repository")


async def _capture_create_deep_agent_kwargs(
    config: RunnableConfig | None = None,
) -> dict[str, object]:
    captured: dict[str, object] = {}

    def fake_create_deep_agent(**kwargs: object) -> _DummyAgent:
        captured.update(kwargs)
        return _DummyAgent()

    def fake_make_model(model_id: str, **kwargs: object) -> MagicMock:
        calls = captured.setdefault("model_calls", [])
        assert isinstance(calls, list)
        calls.append((model_id, kwargs))
        return MagicMock(name=f"model-{len(calls)}")

    registry = MigrationMCPRegistry((), {})
    register_showcase_profile = MagicMock()
    with (
        patch(
            "agent.server.resolve_github_token",
            new_callable=AsyncMock,
            return_value=("ghp", None),
        ),
        patch("agent.server.resolve_triggering_user_identity", return_value=None),
        patch(
            "agent.server.ensure_sandbox_for_thread",
            new_callable=AsyncMock,
            return_value=MagicMock(),
        ),
        patch(
            "agent.server.aresolve_sandbox_work_dir",
            new_callable=AsyncMock,
            return_value="/workspace",
        ),
        patch(
            "agent.server.get_team_default_model_pair",
            new_callable=AsyncMock,
            return_value=(("openai:gpt-5.6-sol", "medium"), ("openai:gpt-5.6-sol", "low")),
        ),
        patch("agent.server.load_profile", new_callable=AsyncMock, return_value=None),
        patch("agent.server.fallback_model_id_for", return_value=None),
        patch("agent.server.make_model", side_effect=fake_make_model),
        patch(
            "agent.server.load_migration_mcp_registry",
            new_callable=AsyncMock,
            return_value=registry,
        ),
        patch(
            "agent.server.register_showcase_harness_profile",
            register_showcase_profile,
        ),
        patch("agent.server.construct_system_prompt", return_value="prompt"),
        patch("agent.server.create_deep_agent", side_effect=fake_create_deep_agent),
    ):
        await get_agent(config or _base_config())

    captured["register_showcase_profile_calls"] = register_showcase_profile.call_count
    return captured


@pytest.mark.asyncio
async def test_agent_uses_writable_sandbox_artifact_root_for_context_management() -> None:
    captured = await _capture_create_deep_agent_kwargs()
    backend = captured["backend"]
    assert isinstance(backend, CompositeBackend)
    assert backend.artifacts_root == DEEPAGENT_ARTIFACT_ROOT
    assert backend.routes == {}
    assert isinstance(backend.default, SandboxBackendProtocol)


@pytest.mark.asyncio
async def test_migration_specialists_use_permissioned_filesystem_without_execution() -> None:
    config = _base_config()
    configurable = config.setdefault("configurable", {})
    assert isinstance(configurable, dict)
    configurable["task_kind"] = "workbook_migration"

    captured = await _capture_create_deep_agent_kwargs(config)
    subagents = captured["subagents"]
    assert isinstance(subagents, list)
    assert subagents

    migration_subagents = [subagent for subagent in subagents if "middleware" in subagent]
    assert migration_subagents
    for subagent in migration_subagents:
        middleware = subagent["middleware"]
        filesystem = next(item for item in middleware if isinstance(item, FilesystemMiddleware))
        assert isinstance(filesystem.backend, CompositeBackend)
        assert not isinstance(filesystem.backend.default, SandboxBackendProtocol)
        assert filesystem._permissions
        assert filesystem._enabled_tools is not None
        assert "execute" not in filesystem._enabled_tools


@pytest.mark.asyncio
async def test_agent_does_not_add_custom_repair_middleware() -> None:
    captured = await _capture_create_deep_agent_kwargs()
    middleware = captured["middleware"]
    assert isinstance(middleware, list)
    names = {type(m).__name__ for m in middleware}
    # Built-in PatchToolCallsMiddleware (added by create_deep_agent) replaces it.
    assert "RepairOrphanedToolCallsMiddleware" not in names
    assert "SanitizeOpenAIResponsesMiddleware" not in names


@pytest.mark.asyncio
async def test_agent_keeps_message_queue_and_step_limit_middleware() -> None:
    captured = await _capture_create_deep_agent_kwargs()
    middleware = captured["middleware"]
    assert isinstance(middleware, list)
    # The dashboard depends on check_message_queue_before_model; the step-limit
    # notifier must still fire when the lowered run budget is hit.
    present = {type(m).__name__ for m in middleware}
    assert "check_message_queue_before_model" in present
    assert "notify_step_limit_reached" in present


@pytest.mark.asyncio
async def test_agent_includes_report_platform_issue_tool() -> None:
    from agent.tools import report_platform_issue

    captured = await _capture_create_deep_agent_kwargs()
    tools = captured["tools"]
    assert isinstance(tools, list)
    assert report_platform_issue in tools


@pytest.mark.asyncio
async def test_task_retry_wraps_inside_tool_error_middleware() -> None:
    captured = await _capture_create_deep_agent_kwargs()
    middleware = captured["middleware"]
    assert isinstance(middleware, list)
    names = [type(m).__name__ for m in middleware]

    assert names.index("ToolErrorMiddleware") < names.index("ToolRetryMiddleware")


@pytest.mark.asyncio
async def test_migration_uses_explicit_primary_and_specialist_models(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("XLSLIBERATOR_PRIMARY_MODEL", "openai:openai/gpt-4.1-mini")
    monkeypatch.setenv("XLSLIBERATOR_SPECIALIST_MODEL", "openai:openai/gpt-4.1-mini")
    config = _base_config()
    configurable = config.setdefault("configurable", {})
    assert isinstance(configurable, dict)
    configurable["task_kind"] = "workbook_migration"

    captured = await _capture_create_deep_agent_kwargs(config)

    calls = captured["model_calls"]
    assert isinstance(calls, list)
    assert [call[0] for call in calls] == [
        "openai:openai/gpt-4.1-mini",
        "openai:openai/gpt-4.1-mini",
    ]
    assert calls[0][1]["max_tokens"] > 0
    assert "reasoning" not in calls[0][1]
    assert "reasoning" not in calls[1][1]


@pytest.mark.asyncio
async def test_showcase_agent_has_only_required_specialists_and_bounded_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("XLSLIBERATOR_SHOWCASE_MODE", "true")
    monkeypatch.setenv("XLSLIBERATOR_PRIMARY_MODEL", "openai:openai/gpt-4.1-mini")
    monkeypatch.setenv("XLSLIBERATOR_SPECIALIST_MODEL", "openai:openai/gpt-4.1-mini")
    config = _base_config()
    configurable = config.setdefault("configurable", {})
    assert isinstance(configurable, dict)
    configurable["task_kind"] = "workbook_migration"

    captured = await _capture_create_deep_agent_kwargs(config)

    tools = captured["tools"]
    subagents = captured["subagents"]
    calls = captured["model_calls"]
    assert isinstance(tools, list)
    assert isinstance(subagents, list)
    assert isinstance(calls, list)
    assert [subagent["name"] for subagent in subagents] == [
        "workbook-forensics",
        "vba-liberation-engineer",
        "ui-migration-engineer",
        "test-adversary",
    ]
    assert all("runnable" in subagent for subagent in subagents)
    assert all("skills" not in subagent for subagent in subagents)
    assert all("middleware" not in subagent for subagent in subagents)
    assert {getattr(tool, "name", getattr(tool, "__name__", "")) for tool in tools} == {
        "request_independent_migration_review"
    }
    assert calls[0][1]["max_tokens"] == 768
    assert calls[1][1]["max_tokens"] == 768
    assert calls[0][1]["profile"]["max_input_tokens"] == 7_232
    assert calls[1][1]["profile"]["max_input_tokens"] == 7_232
    assert captured["register_showcase_profile_calls"] == 1
    assert captured["system_prompt"] == {"base": None}
    middleware = captured["middleware"]
    assert isinstance(middleware, list)
    workbook_context = next(
        item for item in middleware if type(item).__name__ == "WorkbookAttachmentMiddleware"
    )
    assert workbook_context._include_requirements is False
    exclusions = [item for item in middleware if type(item).__name__ == "ExcludeToolsMiddleware"]
    assert len(exclusions) == 1
