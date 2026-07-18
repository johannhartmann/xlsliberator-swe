from __future__ import annotations

import asyncio
from typing import cast

import pytest
from langchain_core.tools import BaseTool, StructuredTool

from agent import server
from agent.xlsliberator.integrations.mcp import (
    MCPConfigurationError,
    MCPServiceConfig,
    load_migration_mcp_registry,
    validate_mcp_endpoint,
)
from agent.xlsliberator.settings import XLSLiberatorSettings


def _settings(**endpoints: str) -> XLSLiberatorSettings:
    env = {
        "XLSLIBERATOR_LIBREOFFICE_MCP_ENDPOINT": endpoints.get("runtime", ""),
        "XLSLIBERATOR_CORPUS_MCP_ENDPOINT": endpoints.get("corpus", ""),
        "XLSLIBERATOR_BUILD_FARM_MCP_ENDPOINT": endpoints.get("buildfarm", ""),
    }
    return XLSLiberatorSettings.from_env(env)


def _tool(name: str, *, failure: str | None = None) -> StructuredTool:
    async def operation(value: str = "ok") -> str:
        if failure is not None:
            raise RuntimeError(failure)
        return value

    return StructuredTool.from_function(
        coroutine=operation,
        name=name,
        description=f"Fake MCP operation {name}.",
    )


class _MalformedTool:
    name = "inspect_document"

    def get_input_schema(self) -> None:
        raise ValueError("invalid schema")


@pytest.mark.parametrize(
    "endpoint",
    [
        "ftp://runtime.internal/mcp",
        "http://public.example/mcp",
        "https://user:secret@runtime.example/mcp",
        "https://runtime.example/not-mcp",
        "https://runtime.example/mcp?token=secret",
        "https://runtime.example/mcp#fragment",
    ],
)
def test_url_policy_rejects_unsafe_endpoints(endpoint: str) -> None:
    with pytest.raises(MCPConfigurationError):
        validate_mcp_endpoint(endpoint, frozenset())


def test_url_policy_accepts_docker_http_and_allowlisted_https() -> None:
    assert validate_mcp_endpoint("http://libreoffice-runtime:8000/mcp", frozenset()) == (
        "libreoffice-runtime"
    )
    assert (
        validate_mcp_endpoint(
            "https://runtime.example/mcp",
            frozenset({"runtime.example"}),
        )
        == "runtime.example"
    )


def test_https_configuration_requires_server_side_token() -> None:
    settings = _settings(runtime="https://runtime.example/mcp")

    async def loader(config: MCPServiceConfig) -> list[BaseTool]:
        raise AssertionError(f"loader must not receive invalid config: {config.name}")

    registry = asyncio.run(load_migration_mcp_registry(settings, env={}, loader=loader))

    assert registry.curated == ()
    assert registry.health["runtime"].status == "UNAVAILABLE"
    assert "server-side bearer token" in (registry.health["runtime"].reason or "")


@pytest.mark.asyncio
async def test_discovery_timeout_is_bounded_and_explicit() -> None:
    async def blocked_loader(config: MCPServiceConfig) -> list[BaseTool]:
        del config
        await asyncio.Event().wait()
        return []

    registry = await load_migration_mcp_registry(
        _settings(runtime="http://runtime:8000/mcp"),
        env={},
        timeout_seconds=0.01,
        loader=blocked_loader,
    )

    assert registry.curated == ()
    assert registry.health["runtime"].status == "TIMEOUT"


@pytest.mark.asyncio
async def test_malformed_schema_is_rejected_without_partial_tools() -> None:
    async def malformed_loader(config: MCPServiceConfig) -> list[BaseTool]:
        del config
        return [cast(BaseTool, _MalformedTool())]

    registry = await load_migration_mcp_registry(
        _settings(runtime="http://runtime:8000/mcp"),
        env={},
        loader=malformed_loader,
    )

    assert registry.curated == ()
    assert registry.health["runtime"].status == "MALFORMED"
    assert "malformed schema" in (registry.health["runtime"].reason or "")


@pytest.mark.asyncio
async def test_unauthorized_server_tool_is_not_exposed() -> None:
    async def overbroad_loader(config: MCPServiceConfig) -> list[BaseTool]:
        del config
        return [_tool("inspect_document"), _tool("drop_database")]

    registry = await load_migration_mcp_registry(
        _settings(runtime="http://runtime:8000/mcp"),
        env={},
        loader=overbroad_loader,
    )

    assert [item.original_name for item in registry.curated] == ["inspect_document"]
    assert [tool.name for tool in registry.tools_for_role("workbook-forensics")] == [
        "xlsliberator_runtime_inspect_document"
    ]


@pytest.mark.asyncio
async def test_server_unavailable_has_no_callable_tools() -> None:
    async def unavailable_loader(config: MCPServiceConfig) -> list[BaseTool]:
        raise ConnectionError(f"{config.name} refused connection")

    registry = await load_migration_mcp_registry(
        _settings(runtime="http://runtime:8000/mcp"),
        env={},
        loader=unavailable_loader,
    )

    assert registry.curated == ()
    assert registry.health["runtime"].status == "UNAVAILABLE"
    assert "ConnectionError" in (registry.health["runtime"].reason or "")


@pytest.mark.asyncio
async def test_operation_failure_propagates_instead_of_returning_fake_success() -> None:
    async def failing_loader(config: MCPServiceConfig) -> list[BaseTool]:
        del config
        return [_tool("inspect_document", failure="runtime operation failed")]

    registry = await load_migration_mcp_registry(
        _settings(runtime="http://runtime:8000/mcp"),
        env={},
        loader=failing_loader,
    )
    tool = registry.tools_for_role("workbook-forensics")[0]

    with pytest.raises(RuntimeError, match="runtime operation failed"):
        await tool.ainvoke({"value": "source.xlsm"})


@pytest.mark.asyncio
async def test_duplicate_tool_name_marks_service_malformed() -> None:
    async def duplicate_loader(config: MCPServiceConfig) -> list[BaseTool]:
        del config
        return [_tool("inspect_document"), _tool("inspect_document")]

    registry = await load_migration_mcp_registry(
        _settings(runtime="http://runtime:8000/mcp"),
        env={},
        loader=duplicate_loader,
    )

    assert registry.curated == ()
    assert registry.health["runtime"].status == "MALFORMED"
    assert "duplicate MCP tool alias" in (registry.health["runtime"].reason or "")


@pytest.mark.asyncio
async def test_hidden_tool_is_reviewer_only_and_never_in_implementation_union() -> None:
    async def corpus_loader(config: MCPServiceConfig) -> list[BaseTool]:
        del config
        return [_tool("run_public_suite"), _tool("run_hidden_acceptance")]

    settings = _settings(corpus="http://corpus:8000/mcp")
    implementation_registry = await load_migration_mcp_registry(
        settings,
        env={},
        loader=corpus_loader,
    )
    reviewer_registry = await load_migration_mcp_registry(
        settings,
        env={},
        include_hidden=True,
        loader=corpus_loader,
    )

    assert "xlsliberator_corpus_run_hidden_acceptance" not in {
        tool.name for tool in implementation_registry.implementation_tools()
    }
    assert "xlsliberator_corpus_run_hidden_acceptance" not in {
        tool.name for tool in reviewer_registry.implementation_tools()
    }
    assert "xlsliberator_corpus_run_hidden_acceptance" in {
        tool.name for tool in reviewer_registry.tools_for_role("reviewer")
    }


@pytest.mark.asyncio
async def test_build_farm_tools_require_repair_flow_authority() -> None:
    async def build_loader(config: MCPServiceConfig) -> list[BaseTool]:
        del config
        return [_tool("apply_patch")]

    registry = await load_migration_mcp_registry(
        _settings(buildfarm="http://build-farm:8000/mcp"),
        env={},
        loader=build_loader,
    )

    assert registry.tools_for_role("lead") == []
    assert registry.tools_for_role("libreoffice-engineer") == []
    assert [
        tool.name
        for tool in registry.tools_for_role(
            "libreoffice-engineer",
            build_farm_authorized=True,
        )
    ] == ["xlsliberator_buildfarm_apply_patch"]
    assert [
        tool.name
        for tool in registry.tools_for_role(
            "lead",
            build_farm_authorized=True,
        )
    ] == ["xlsliberator_buildfarm_apply_patch"]


@pytest.mark.asyncio
async def test_discovery_is_namespaced_and_health_is_safe_for_thread_metadata() -> None:
    async def loader(config: MCPServiceConfig) -> list[BaseTool]:
        names = {
            "runtime": "inspect_document",
            "corpus": "capability_report",
            "buildfarm": "collect_build_logs",
        }
        return [_tool(names[config.name])]

    registry = await load_migration_mcp_registry(
        _settings(
            runtime="https://runtime.example/mcp",
            corpus="https://corpus.example/mcp",
            buildfarm="https://build.example/mcp",
        ),
        env={
            "XLSLIBERATOR_LIBREOFFICE_MCP_TOKEN": "runtime-secret",
            "XLSLIBERATOR_CORPUS_MCP_TOKEN": "corpus-secret",
            "XLSLIBERATOR_BUILD_FARM_MCP_TOKEN": "build-secret",
        },
        loader=loader,
    )
    metadata = registry.metadata()

    assert metadata["runtime"]["status"] == "AVAILABLE"
    assert metadata["runtime"]["endpoint_host"] == "runtime.example"
    assert metadata["runtime"]["capabilities"] == ["xlsliberator_runtime_inspect_document"]
    assert "secret" not in repr(metadata)


def test_build_farm_server_and_run_authority_are_both_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("XLSLIBERATOR_BUILD_FARM_MUTATION_ENABLED", raising=False)
    assert not server._build_farm_repair_authorized({"repair_flow_authorized": True})

    monkeypatch.setenv("XLSLIBERATOR_BUILD_FARM_MUTATION_ENABLED", "true")
    assert not server._build_farm_repair_authorized({})
    assert server._build_farm_repair_authorized({"repair_flow_authorized": True})
