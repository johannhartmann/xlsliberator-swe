"""Curated server-side MCP integrations for workbook migration agents."""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import os
import re
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Literal, cast
from urllib.parse import urlparse

from langchain_core.tools import BaseTool

from ..settings import XLSLiberatorSettings

logger = logging.getLogger(__name__)

ServiceName = Literal["runtime", "corpus", "buildfarm"]
ServiceStatus = Literal[
    "AVAILABLE",
    "UNCONFIGURED",
    "UNAVAILABLE",
    "TIMEOUT",
    "MALFORMED",
]

DEFAULT_DISCOVERY_TIMEOUT_SECONDS = 4.0
_TOOL_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,127}$")
_MCP_PATH = "/mcp"

RUNTIME_TOOLS = frozenset(
    {
        "create_session",
        "open_document",
        "inspect_document",
        "list_sheets",
        "read_cells",
        "write_cells",
        "list_formulas",
        "recalculate",
        "list_controls",
        "dispatch_control_event",
        "send_keyboard_event",
        "execute_python_macro",
        "capture_screenshot",
        "export_pdf",
        "save",
        "close",
        "reopen",
        "collect_logs",
        "destroy_session",
    }
)
CORPUS_PUBLIC_TOOLS = frozenset(
    {
        "search_public_fixtures",
        "search_prior_failures",
        "run_public_suite",
        "register_minimized_failure",
        "compare_runs",
        "capability_report",
    }
)
CORPUS_HIDDEN_TOOLS = frozenset({"run_hidden_acceptance"})
BUILD_FARM_TOOLS = frozenset(
    {
        "create_source_worktree",
        "apply_patch",
        "build_component",
        "run_upstream_tests",
        "publish_test_artifact",
        "compare_stock_patched",
        "collect_build_logs",
    }
)

ROLE_ALLOWLISTS: Mapping[str, Mapping[ServiceName, frozenset[str]]] = {
    "lead": {
        "runtime": RUNTIME_TOOLS,
        "corpus": CORPUS_PUBLIC_TOOLS,
        "buildfarm": frozenset(),
    },
    "workbook-forensics": {
        "runtime": frozenset(
            {
                "create_session",
                "open_document",
                "inspect_document",
                "list_sheets",
                "read_cells",
                "list_formulas",
                "list_controls",
                "collect_logs",
                "destroy_session",
            }
        ),
        "corpus": frozenset({"search_public_fixtures", "search_prior_failures"}),
        "buildfarm": frozenset(),
    },
    "formula-engineer": {
        "runtime": frozenset(
            {
                "create_session",
                "open_document",
                "read_cells",
                "write_cells",
                "list_formulas",
                "recalculate",
                "save",
                "close",
                "reopen",
                "collect_logs",
                "destroy_session",
            }
        ),
        "corpus": frozenset({"search_public_fixtures", "run_public_suite"}),
        "buildfarm": frozenset(),
    },
    "vba-liberation-engineer": {
        "runtime": frozenset(
            {
                "create_session",
                "open_document",
                "inspect_document",
                "read_cells",
                "write_cells",
                "list_controls",
                "dispatch_control_event",
                "send_keyboard_event",
                "execute_python_macro",
                "save",
                "close",
                "reopen",
                "collect_logs",
                "destroy_session",
            }
        ),
        "corpus": frozenset({"search_public_fixtures", "run_public_suite"}),
        "buildfarm": frozenset(),
    },
    "ui-migration-engineer": {
        "runtime": frozenset(
            {
                "create_session",
                "open_document",
                "inspect_document",
                "list_controls",
                "dispatch_control_event",
                "send_keyboard_event",
                "capture_screenshot",
                "save",
                "close",
                "reopen",
                "collect_logs",
                "destroy_session",
            }
        ),
        "corpus": frozenset({"search_public_fixtures", "run_public_suite"}),
        "buildfarm": frozenset(),
    },
    "dependency-liberation-engineer": {
        "runtime": frozenset(
            {
                "create_session",
                "open_document",
                "inspect_document",
                "execute_python_macro",
                "export_pdf",
                "collect_logs",
                "destroy_session",
            }
        ),
        "corpus": frozenset({"search_public_fixtures", "run_public_suite"}),
        "buildfarm": frozenset(),
    },
    "libreoffice-engineer": {
        "runtime": RUNTIME_TOOLS,
        "corpus": frozenset(
            {
                "search_public_fixtures",
                "search_prior_failures",
                "run_public_suite",
                "compare_runs",
            }
        ),
        "buildfarm": BUILD_FARM_TOOLS,
    },
    "test-adversary": {
        "runtime": RUNTIME_TOOLS,
        "corpus": frozenset(
            {
                "search_public_fixtures",
                "search_prior_failures",
                "run_public_suite",
                "compare_runs",
            }
        ),
        "buildfarm": frozenset(),
    },
    "failure-minimizer": {
        "runtime": RUNTIME_TOOLS,
        "corpus": frozenset(
            {
                "search_prior_failures",
                "run_public_suite",
                "register_minimized_failure",
                "compare_runs",
            }
        ),
        "buildfarm": frozenset(),
    },
    "reviewer": {
        "runtime": RUNTIME_TOOLS,
        "corpus": CORPUS_PUBLIC_TOOLS | CORPUS_HIDDEN_TOOLS,
        "buildfarm": frozenset(),
    },
}


class MCPConfigurationError(ValueError):
    """An MCP endpoint violates the server-side transport policy."""


class MCPDiscoveryError(RuntimeError):
    """A server returned malformed or conflicting tool metadata."""


@dataclass(frozen=True)
class MCPServiceConfig:
    """Validated server-side connection details."""

    name: ServiceName
    endpoint: str
    token: str = field(repr=False)


@dataclass(frozen=True)
class MCPServiceHealth:
    """Bounded discovery result persisted in migration metadata."""

    status: ServiceStatus
    endpoint_host: str | None
    capabilities: tuple[str, ...] = ()
    reason: str | None = None


@dataclass(frozen=True)
class CuratedTool:
    """One namespaced tool and its unambiguous service identity."""

    service: ServiceName
    original_name: str
    tool: BaseTool


@dataclass
class MigrationMCPRegistry:
    """Role-aware view over safely discovered MCP tools."""

    curated: tuple[CuratedTool, ...]
    health: Mapping[ServiceName, MCPServiceHealth]

    def tools_for_role(
        self,
        role: str,
        *,
        build_farm_authorized: bool = False,
    ) -> list[BaseTool]:
        if role not in ROLE_ALLOWLISTS:
            raise ValueError(f"unknown migration role: {role}")
        tools: list[BaseTool] = []
        for item in self.curated:
            allowed = ROLE_ALLOWLISTS[role][item.service]
            if item.service == "buildfarm":
                if not build_farm_authorized:
                    continue
                if role == "lead":
                    allowed = BUILD_FARM_TOOLS
            if item.original_name in allowed:
                tools.append(item.tool)
        return tools

    def implementation_tools(
        self,
        *,
        build_farm_authorized: bool = False,
    ) -> list[BaseTool]:
        """Return union for subagent assembly without reviewer-hidden operations."""

        names: set[str] = set()
        tools: list[BaseTool] = []
        for role in ROLE_ALLOWLISTS:
            if role == "reviewer":
                continue
            for tool in self.tools_for_role(
                role,
                build_farm_authorized=build_farm_authorized,
            ):
                if tool.name not in names:
                    tools.append(tool)
                    names.add(tool.name)
        return tools

    def metadata(self) -> dict[str, dict[str, object]]:
        return {
            service: {
                "status": health.status,
                "endpoint_host": health.endpoint_host,
                "capabilities": list(health.capabilities),
                "reason": health.reason,
            }
            for service, health in self.health.items()
        }


def _is_local_http_host(host: str) -> bool:
    if host in {"localhost", "::1"} or "." not in host:
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return host.endswith(".internal")
    return address.is_loopback or address.is_private


def validate_mcp_endpoint(endpoint: str, allowed_hosts: frozenset[str]) -> str:
    """Validate HTTPS production or private Docker/loopback HTTP MCP URL."""

    parsed = urlparse(endpoint)
    host = parsed.hostname
    if (
        not host
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path.rstrip("/") != _MCP_PATH
    ):
        raise MCPConfigurationError("MCP URL must be a credential-free /mcp endpoint")
    if parsed.scheme == "http":
        if not _is_local_http_host(host):
            raise MCPConfigurationError("plaintext MCP is limited to private local services")
    elif parsed.scheme != "https":
        raise MCPConfigurationError("MCP URL must use HTTPS outside local Docker networking")
    if allowed_hosts and host not in allowed_hosts:
        raise MCPConfigurationError(f"MCP host is not allowed: {host}")
    return host


def _allowed_hosts(env: Mapping[str, str]) -> frozenset[str]:
    return frozenset(
        host.strip().lower()
        for host in env.get("XLSLIBERATOR_MCP_ALLOWED_HOSTS", "").split(",")
        if host.strip()
    )


def load_service_configs(
    settings: XLSLiberatorSettings,
    env: Mapping[str, str] | None = None,
) -> tuple[dict[ServiceName, MCPServiceConfig], dict[ServiceName, MCPServiceHealth]]:
    """Load endpoints and credentials without exposing secrets to sandbox state."""

    source = os.environ if env is None else env
    hosts = _allowed_hosts(source)
    endpoints: dict[ServiceName, str | None] = {
        "runtime": settings.libreoffice_mcp_endpoint,
        "corpus": settings.corpus_mcp_endpoint,
        "buildfarm": settings.build_farm_mcp_endpoint,
    }
    token_names: dict[ServiceName, str] = {
        "runtime": "XLSLIBERATOR_LIBREOFFICE_MCP_TOKEN",
        "corpus": "XLSLIBERATOR_CORPUS_MCP_TOKEN",
        "buildfarm": "XLSLIBERATOR_BUILD_FARM_MCP_TOKEN",
    }
    configs: dict[ServiceName, MCPServiceConfig] = {}
    health: dict[ServiceName, MCPServiceHealth] = {}
    for name, endpoint in endpoints.items():
        if endpoint is None:
            health[name] = MCPServiceHealth("UNCONFIGURED", None, reason="endpoint not configured")
            continue
        try:
            host = validate_mcp_endpoint(endpoint, hosts)
        except MCPConfigurationError as exc:
            health[name] = MCPServiceHealth("UNAVAILABLE", None, reason=str(exc))
            continue
        token = source.get(token_names[name], "").strip()
        if endpoint.startswith("https://") and not token:
            health[name] = MCPServiceHealth(
                "UNAVAILABLE",
                host,
                reason="HTTPS MCP endpoint requires a server-side bearer token",
            )
            continue
        configs[name] = MCPServiceConfig(name, endpoint, token)
    return configs, health


async def _build_mcp_tools(config: MCPServiceConfig) -> list[BaseTool]:
    from langchain_mcp_adapters.client import MultiServerMCPClient

    headers = {"Authorization": f"Bearer {config.token}"} if config.token else {}
    client = MultiServerMCPClient(
        cast(
            Any,
            {
                config.name: {
                    "transport": "streamable_http",
                    "url": config.endpoint,
                    "headers": headers,
                    "timeout": timedelta(seconds=DEFAULT_DISCOVERY_TIMEOUT_SECONDS),
                }
            },
        )
    )
    return await client.get_tools()


def _service_public_allowlist(
    service: ServiceName,
    *,
    include_hidden: bool,
) -> frozenset[str]:
    if service == "runtime":
        return RUNTIME_TOOLS
    if service == "buildfarm":
        return BUILD_FARM_TOOLS
    if include_hidden:
        return CORPUS_PUBLIC_TOOLS | CORPUS_HIDDEN_TOOLS
    return CORPUS_PUBLIC_TOOLS


def _validate_and_namespace(
    service: ServiceName,
    tools: Sequence[BaseTool],
    *,
    include_hidden: bool,
) -> tuple[CuratedTool, ...]:
    allowed = _service_public_allowlist(service, include_hidden=include_hidden)
    curated: list[CuratedTool] = []
    aliases: set[str] = set()
    for tool in tools:
        original_name = tool.name
        if original_name not in allowed:
            continue
        if not _TOOL_NAME.fullmatch(original_name):
            raise MCPDiscoveryError(f"{service} returned an invalid tool name")
        try:
            tool.get_input_schema().model_json_schema()
        except Exception as exc:  # noqa: BLE001
            raise MCPDiscoveryError(f"{service}.{original_name} has a malformed schema") from exc
        alias = f"xlsliberator_{service}_{original_name}"
        if alias in aliases:
            raise MCPDiscoveryError(f"duplicate MCP tool alias: {alias}")
        aliases.add(alias)
        curated.append(
            CuratedTool(
                service=service,
                original_name=original_name,
                tool=tool.model_copy(update={"name": alias}),
            )
        )
    return tuple(curated)


async def _discover(
    config: MCPServiceConfig,
    *,
    include_hidden: bool,
    timeout_seconds: float,
    loader: Callable[[MCPServiceConfig], Awaitable[list[BaseTool]]],
) -> tuple[tuple[CuratedTool, ...], MCPServiceHealth]:
    host = urlparse(config.endpoint).hostname
    try:
        discovered = await asyncio.wait_for(loader(config), timeout=timeout_seconds)
        curated = _validate_and_namespace(
            config.name,
            discovered,
            include_hidden=include_hidden,
        )
    except TimeoutError:
        return (), MCPServiceHealth("TIMEOUT", host, reason="bounded discovery timed out")
    except MCPDiscoveryError as exc:
        return (), MCPServiceHealth("MALFORMED", host, reason=str(exc))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Migration MCP discovery failed for %s", config.name, exc_info=True)
        return (), MCPServiceHealth(
            "UNAVAILABLE",
            host,
            reason=f"{type(exc).__name__}: {exc}",
        )
    return (
        curated,
        MCPServiceHealth(
            "AVAILABLE",
            host,
            capabilities=tuple(item.tool.name for item in curated),
        ),
    )


async def load_migration_mcp_registry(
    settings: XLSLiberatorSettings,
    *,
    env: Mapping[str, str] | None = None,
    include_hidden: bool = False,
    timeout_seconds: float = DEFAULT_DISCOVERY_TIMEOUT_SECONDS,
    loader: Callable[[MCPServiceConfig], Awaitable[list[BaseTool]]] = _build_mcp_tools,
) -> MigrationMCPRegistry:
    """Discover configured services concurrently and return a role-aware registry."""

    configs, initial_health = load_service_configs(settings, env)
    names = tuple(configs)
    results = await asyncio.gather(
        *(
            _discover(
                configs[name],
                include_hidden=include_hidden,
                timeout_seconds=timeout_seconds,
                loader=loader,
            )
            for name in names
        )
    )
    curated: list[CuratedTool] = []
    health: dict[ServiceName, MCPServiceHealth] = dict(initial_health)
    aliases: set[str] = set()
    for name, (service_tools, service_health) in zip(names, results, strict=True):
        collision: str | None = None
        for item in service_tools:
            if item.tool.name in aliases:
                collision = item.tool.name
                break
        if collision is not None:
            health[name] = MCPServiceHealth(
                "MALFORMED",
                service_health.endpoint_host,
                reason=f"cross-service tool-name collision: {collision}",
            )
            continue
        aliases.update(item.tool.name for item in service_tools)
        curated.extend(service_tools)
        health[name] = service_health
    for service in ("runtime", "corpus", "buildfarm"):
        if service not in health:
            health[cast(ServiceName, service)] = MCPServiceHealth(
                "UNCONFIGURED",
                None,
                reason="endpoint not configured",
            )
    return MigrationMCPRegistry(tuple(curated), health)
