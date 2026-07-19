"""Server-owned file bridge between private sandboxes and trusted MCP services.

The migration sandbox never receives this directory, the Docker socket, or an
MCP credential. Only the Open-SWE server copies explicitly named files between
the sandbox backend and one per-call bridge directory.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from deepagents.backends.protocol import SandboxBackendProtocol
from langchain_core.tools import BaseTool, StructuredTool
from .mcp import CuratedTool, MCPServiceHealth, MigrationMCPRegistry

_SHOWCASE_TOOLS = frozenset(
    {
        "build_interactive_game_target",
        "run_interactive_game_scenario",
        "bundle_interactive_game_replays",
    }
)
_BRIDGED_SESSION_TOOLS = frozenset(
    {
        "open_document",
        "save",
        "export_pdf",
        "destroy_session",
    }
)
_MAX_BRIDGE_FILE_BYTES = 64 * 1024 * 1024
_MCP_SUCCESS = frozenset({"PASSED", "passed"})


class MCPBridgeError(RuntimeError):
    """A bridge transfer or trusted MCP operation failed closed."""


BackendResolver = Callable[[], SandboxBackendProtocol]


def bridge_migration_mcp_registry(
    registry: MigrationMCPRegistry,
    *,
    backend: BackendResolver,
    thread_id: str,
    bridge_root: str | None,
) -> MigrationMCPRegistry:
    """Wrap path-bearing runtime tools and suppress them without a secure bridge."""

    root = _validated_root(bridge_root) if bridge_root is not None else None
    curated: list[CuratedTool] = []
    for item in registry.curated:
        if item.service != "runtime" or (
            item.original_name not in _SHOWCASE_TOOLS
            and item.original_name not in _BRIDGED_SESSION_TOOLS
        ):
            curated.append(item)
            continue
        if root is None:
            continue
        curated.append(
            CuratedTool(
                service=item.service,
                original_name=item.original_name,
                tool=_bridged_tool(
                    item,
                    backend=backend,
                    thread_id=thread_id,
                    root=root,
                ),
            )
        )
    health = dict(registry.health)
    runtime_health = health.get("runtime")
    if runtime_health is not None:
        capabilities = tuple(item.tool.name for item in curated if item.service == "runtime")
        reason = runtime_health.reason
        if root is None and any(
            item.service == "runtime"
            and (
                item.original_name in _SHOWCASE_TOOLS
                or item.original_name in _BRIDGED_SESSION_TOOLS
            )
            for item in registry.curated
        ):
            bridge_reason = "path-bearing tools withheld: secure bridge not configured"
            reason = f"{reason}; {bridge_reason}" if reason else bridge_reason
        health["runtime"] = MCPServiceHealth(
            status=runtime_health.status,
            endpoint_host=runtime_health.endpoint_host,
            capabilities=capabilities,
            reason=reason,
        )
    return MigrationMCPRegistry(tuple(curated), health)


def _validated_root(raw_root: str) -> Path:
    root = Path(raw_root)
    if not root.is_absolute():
        raise ValueError("XLSLIBERATOR_MCP_BRIDGE_ROOT must be absolute")
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if root.is_symlink():
        raise ValueError("XLSLIBERATOR_MCP_BRIDGE_ROOT cannot be a symlink")
    resolved = root.resolve(strict=True)
    if not resolved.is_dir():
        raise ValueError("XLSLIBERATOR_MCP_BRIDGE_ROOT must be a directory")
    os.chmod(resolved, 0o700)
    return resolved


def _bridged_tool(
    item: CuratedTool,
    *,
    backend: BackendResolver,
    thread_id: str,
    root: Path,
) -> BaseTool:
    handler = _handler_for(
        item,
        backend=backend,
        thread_id=thread_id,
        root=root,
    )
    # MCP adapters expose their authoritative input schema as a JSON-schema
    # dict. Calling ``get_input_schema()`` on that dict asks LangChain to model
    # the tool's entire Runnable input union and creates an unrelated
    # ``root.anyOf`` schema. Strict OpenAI-compatible providers reject that
    # wrapper before any tool can run, so preserve the MCP schema verbatim.
    input_schema = item.tool.args_schema
    if input_schema is None:
        input_schema = item.tool.get_input_schema()
    return StructuredTool.from_function(
        coroutine=handler,
        name=item.tool.name,
        description=item.tool.description,
        args_schema=input_schema,
    )


def _handler_for(
    item: CuratedTool,
    *,
    backend: BackendResolver,
    thread_id: str,
    root: Path,
) -> Callable[..., Awaitable[dict[str, Any]]]:
    original_name = item.original_name

    async def handler(**arguments: Any) -> dict[str, Any]:
        sandbox = backend()
        if original_name == "build_interactive_game_target":
            return await _bridge_build(item.tool, sandbox, thread_id, root, arguments)
        if original_name == "run_interactive_game_scenario":
            return await _bridge_scenario(item.tool, sandbox, thread_id, root, arguments)
        if original_name == "bundle_interactive_game_replays":
            return await _bridge_bundle(item.tool, sandbox, thread_id, root, arguments)
        if original_name == "open_document":
            return await _bridge_open(item.tool, sandbox, thread_id, root, arguments)
        if original_name in {"save", "export_pdf"}:
            return await _bridge_session_output(
                item.tool,
                sandbox,
                thread_id,
                root,
                arguments,
                original_name,
            )
        if original_name == "destroy_session":
            return await _bridge_destroy(item.tool, thread_id, root, arguments)
        raise MCPBridgeError(f"unsupported bridged runtime operation: {original_name}")

    return handler


async def _bridge_build(
    tool: BaseTool,
    backend: SandboxBackendProtocol,
    thread_id: str,
    root: Path,
    arguments: Mapping[str, Any],
) -> dict[str, Any]:
    source_path = _sandbox_file(arguments, "source_path")
    output_path = _sandbox_file(arguments, "output_path")
    directory = _call_directory(root, thread_id, "build")
    try:
        local_source = directory / "source.xlsb"
        local_output = directory / "target.ods"
        _write_private(local_source, await _download(backend, source_path))
        result = await _invoke(
            tool,
            {
                "source_path": str(local_source),
                "output_path": str(local_output),
            },
        )
        _require_success(result)
        await _upload(backend, output_path, _read_private(local_output))
        return result
    finally:
        _remove_directory(directory, root)


async def _bridge_scenario(
    tool: BaseTool,
    backend: SandboxBackendProtocol,
    thread_id: str,
    root: Path,
    arguments: Mapping[str, Any],
) -> dict[str, Any]:
    target_path = _sandbox_file(arguments, "target_path")
    evidence_path = _sandbox_file(arguments, "evidence_path")
    directory = _call_directory(root, thread_id, "scenario")
    try:
        local_target = directory / "target.ods"
        local_evidence = directory / "evidence.zip"
        _write_private(local_target, await _download(backend, target_path))
        forwarded = dict(arguments)
        forwarded["target_path"] = str(local_target)
        forwarded["evidence_path"] = str(local_evidence)
        result = await _invoke(tool, forwarded)
        _require_success(result)
        await _upload(backend, evidence_path, _read_private(local_evidence))
        return result
    finally:
        _remove_directory(directory, root)


async def _bridge_bundle(
    tool: BaseTool,
    backend: SandboxBackendProtocol,
    thread_id: str,
    root: Path,
    arguments: Mapping[str, Any],
) -> dict[str, Any]:
    raw_paths = arguments.get("evidence_paths")
    if not isinstance(raw_paths, Mapping) or not raw_paths:
        raise MCPBridgeError("evidence_paths must be a non-empty object")
    output_path = _sandbox_file(arguments, "output_path")
    directory = _call_directory(root, thread_id, "bundle")
    try:
        local_paths: dict[str, str] = {}
        for scenario_id, raw_path in raw_paths.items():
            if not isinstance(scenario_id, str) or not isinstance(raw_path, str):
                raise MCPBridgeError("evidence_paths must map strings to strings")
            sandbox_path = _sandbox_path(raw_path)
            local_path = directory / f"{_safe_component(scenario_id)}.zip"
            _write_private(local_path, await _download(backend, sandbox_path))
            local_paths[scenario_id] = str(local_path)
        local_output = directory / "public-replay.zip"
        result = await _invoke(
            tool,
            {
                "evidence_paths": local_paths,
                "output_path": str(local_output),
            },
        )
        _require_success(result)
        await _upload(backend, output_path, _read_private(local_output))
        return result
    finally:
        _remove_directory(directory, root)


async def _bridge_open(
    tool: BaseTool,
    backend: SandboxBackendProtocol,
    thread_id: str,
    root: Path,
    arguments: Mapping[str, Any],
) -> dict[str, Any]:
    session_id = _required_string(arguments, "session_id")
    document_path = _sandbox_file(arguments, "document_path")
    directory = _session_directory(root, thread_id, session_id)
    if directory is None:
        raise MCPBridgeError("failed to create private runtime session directory")
    try:
        local_document = directory / "input.ods"
        _write_private(local_document, await _download(backend, document_path))
        result = await _invoke(
            tool,
            {
                "session_id": session_id,
                "document_path": str(local_document),
            },
        )
        _require_success(result)
        return result
    except Exception:
        _remove_directory(directory, root)
        raise


async def _bridge_session_output(
    tool: BaseTool,
    backend: SandboxBackendProtocol,
    thread_id: str,
    root: Path,
    arguments: Mapping[str, Any],
    operation: str,
) -> dict[str, Any]:
    session_id = _required_string(arguments, "session_id")
    raw_output = arguments.get("output_path")
    if operation == "save" and raw_output is None:
        return await _invoke(tool, {"session_id": session_id, "output_path": None})
    output_path = _sandbox_path(_required_string(arguments, "output_path"))
    directory = _session_directory(root, thread_id, session_id, create=False)
    if directory is None:
        raise MCPBridgeError("runtime session has no private bridge directory")
    suffix = ".pdf" if operation == "export_pdf" else ".ods"
    local_output = directory / f"{operation}{suffix}"
    result = await _invoke(
        tool,
        {
            "session_id": session_id,
            "output_path": str(local_output),
        },
    )
    _require_success(result)
    await _upload(backend, output_path, _read_private(local_output))
    return result


async def _bridge_destroy(
    tool: BaseTool,
    thread_id: str,
    root: Path,
    arguments: Mapping[str, Any],
) -> dict[str, Any]:
    session_id = _required_string(arguments, "session_id")
    try:
        return await _invoke(tool, {"session_id": session_id})
    finally:
        directory = _session_directory(root, thread_id, session_id, create=False)
        if directory is not None:
            _remove_directory(directory, root)


async def _invoke(tool: BaseTool, arguments: Mapping[str, Any]) -> dict[str, Any]:
    result = await tool.ainvoke(dict(arguments))
    if not isinstance(result, Mapping):
        raise MCPBridgeError("trusted MCP returned a non-object response")
    return dict(result)


def _require_success(result: Mapping[str, Any]) -> None:
    status = result.get("operation_status")
    if result.get("success") is not True or status not in _MCP_SUCCESS:
        error = result.get("error")
        detail = error.get("message") if isinstance(error, Mapping) else None
        raise MCPBridgeError(str(detail or "trusted MCP operation failed"))


async def _download(backend: SandboxBackendProtocol, path: str) -> bytes:
    responses = await backend.adownload_files([path])
    if len(responses) != 1:
        raise MCPBridgeError("sandbox download returned an unexpected response count")
    response = responses[0]
    content = response.get("content") if isinstance(response, Mapping) else response.content
    error = response.get("error") if isinstance(response, Mapping) else response.error
    if error or not isinstance(content, bytes):
        raise MCPBridgeError(f"sandbox download failed: {error or 'missing content'}")
    if len(content) > _MAX_BRIDGE_FILE_BYTES:
        raise MCPBridgeError("sandbox file exceeds the bridge size limit")
    return content


async def _upload(backend: SandboxBackendProtocol, path: str, content: bytes) -> None:
    responses = await backend.aupload_files([(path, content)])
    if len(responses) != 1:
        raise MCPBridgeError("sandbox upload returned an unexpected response count")
    response = responses[0]
    error = response.get("error") if isinstance(response, Mapping) else response.error
    if error:
        raise MCPBridgeError(f"sandbox upload failed: {error}")


def _write_private(path: Path, content: bytes) -> None:
    if len(content) > _MAX_BRIDGE_FILE_BYTES:
        raise MCPBridgeError("bridge input exceeds the size limit")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
    except Exception:
        path.unlink(missing_ok=True)
        raise


def _read_private(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise MCPBridgeError("trusted MCP did not produce a regular output file")
    size = path.stat().st_size
    if size > _MAX_BRIDGE_FILE_BYTES:
        raise MCPBridgeError("trusted MCP output exceeds the bridge size limit")
    return path.read_bytes()


def _call_directory(root: Path, thread_id: str, operation: str) -> Path:
    prefix = f"{_digest(thread_id)}-{_safe_component(operation)}-"
    directory = Path(tempfile.mkdtemp(prefix=prefix, dir=root))
    os.chmod(directory, 0o700)
    return directory


def _session_directory(
    root: Path,
    thread_id: str,
    session_id: str,
    *,
    create: bool = True,
) -> Path | None:
    sessions = root / "sessions"
    if create:
        sessions.mkdir(mode=0o700, exist_ok=True)
    elif not sessions.is_dir():
        return None
    if sessions.is_symlink():
        raise MCPBridgeError("bridge sessions directory cannot be a symlink")
    resolved_sessions = sessions.resolve(strict=True)
    if not resolved_sessions.is_relative_to(root):
        raise MCPBridgeError("bridge sessions directory escaped the private root")
    directory = resolved_sessions / f"{_digest(thread_id)}-{_digest(session_id)}"
    if create:
        directory.mkdir(mode=0o700, exist_ok=True)
    elif not directory.is_dir():
        return None
    if directory.is_symlink():
        raise MCPBridgeError("runtime session directory cannot be a symlink")
    resolved = directory.resolve(strict=True)
    if not resolved.is_relative_to(resolved_sessions):
        raise MCPBridgeError("runtime session directory escaped the private root")
    os.chmod(resolved, 0o700)
    return resolved


def _remove_directory(directory: Path, root: Path) -> None:
    resolved = directory.resolve(strict=False)
    if resolved == root or not resolved.is_relative_to(root):
        raise MCPBridgeError("refusing to clean a path outside the bridge root")
    shutil.rmtree(resolved, ignore_errors=True)


def _sandbox_file(arguments: Mapping[str, Any], name: str) -> str:
    return _sandbox_path(_required_string(arguments, name))


def _sandbox_path(path: str) -> str:
    pure = PurePosixPath(path)
    if (
        not pure.is_absolute()
        or not pure.is_relative_to("/workspace")
        or pure == PurePosixPath("/workspace")
        or ".." in pure.parts
    ):
        raise MCPBridgeError("bridged files must be below /workspace")
    return str(pure)


def _required_string(arguments: Mapping[str, Any], name: str) -> str:
    value = arguments.get(name)
    if not isinstance(value, str) or not value or "\x00" in value:
        raise MCPBridgeError(f"{name} must be a non-empty NUL-free string")
    return value


def _safe_component(value: str) -> str:
    if not value or len(value) > 128:
        raise MCPBridgeError("bridge component has an invalid length")
    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
    if any(character not in allowed for character in value):
        raise MCPBridgeError("bridge component contains unsupported characters")
    return value


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:24]


__all__ = [
    "MCPBridgeError",
    "bridge_migration_mcp_registry",
]
