from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest
from deepagents.backends.protocol import (
    FileDownloadResponse,
    FileUploadResponse,
    SandboxBackendProtocol,
)
from langchain_core.tools import StructuredTool

from agent.xlsliberator.integrations.mcp import (
    CuratedTool,
    MCPServiceHealth,
    MigrationMCPRegistry,
)
from agent.xlsliberator.integrations.mcp_bridge import (
    MCPBridgeError,
    bridge_migration_mcp_registry,
)


class _Backend:
    def __init__(self, files: dict[str, bytes]) -> None:
        self.files = files
        self.downloads: list[str] = []
        self.uploads: list[str] = []

    async def adownload_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        self.downloads.extend(paths)
        return [
            FileDownloadResponse(
                path=path,
                content=self.files.get(path),
                error=None if path in self.files else "file_not_found",
            )
            for path in paths
        ]

    async def aupload_files(
        self,
        files: list[tuple[str, bytes]],
    ) -> list[FileUploadResponse]:
        for path, content in files:
            self.files[path] = content
            self.uploads.append(path)
        return [FileUploadResponse(path=path) for path, _content in files]


def _registry(name: str, tool: StructuredTool) -> MigrationMCPRegistry:
    return MigrationMCPRegistry(
        (
            CuratedTool(
                service="runtime",
                original_name=name,
                tool=tool.model_copy(update={"name": f"xlsliberator_runtime_{name}"}),
            ),
        ),
        {"runtime": MCPServiceHealth("AVAILABLE", "runtime")},
    )


def _success(**extra: Any) -> dict[str, Any]:
    return {
        "success": True,
        "operation_status": "PASSED",
        **extra,
    }


@pytest.mark.asyncio
async def test_build_bridge_transfers_only_explicit_files(tmp_path: Path) -> None:
    observed: dict[str, str] = {}

    async def build(
        source_path: str,
        candidate_path: str,
        output_path: str,
    ) -> dict[str, Any]:
        observed["source_path"] = source_path
        observed["candidate_path"] = candidate_path
        observed["output_path"] = output_path
        assert Path(source_path).read_bytes() == b"original-xlsb"
        assert Path(candidate_path).read_bytes() == b"candidate-bundle"
        Path(output_path).write_bytes(b"native-ods")
        return _success(target_build="26.2.4.2")

    tool = StructuredTool.from_function(
        coroutine=build,
        name="build_application_candidate",
        description="Build target.",
    )
    backend = _Backend(
        {
            "/workspace/source/game.xlsb": b"original-xlsb",
            "/workspace/migration/generated/candidate.zip": b"candidate-bundle",
        }
    )
    registry = bridge_migration_mcp_registry(
        _registry("build_application_candidate", tool),
        backend=lambda: cast(SandboxBackendProtocol, backend),
        thread_id="private-thread",
        bridge_root=str(tmp_path),
    )

    result = await registry.curated[0].tool.ainvoke(
        {
            "source_path": "/workspace/source/game.xlsb",
            "candidate_path": "/workspace/migration/generated/candidate.zip",
            "output_path": "/workspace/migration/output/target.ods",
        }
    )

    assert result["success"] is True
    assert backend.downloads == [
        "/workspace/source/game.xlsb",
        "/workspace/migration/generated/candidate.zip",
    ]
    assert backend.uploads == ["/workspace/migration/output/target.ods"]
    assert backend.files["/workspace/migration/output/target.ods"] == b"native-ods"
    assert observed["source_path"].startswith(f"{tmp_path}/")
    assert observed["candidate_path"].startswith(f"{tmp_path}/")
    assert observed["output_path"].startswith(f"{tmp_path}/")
    assert list(tmp_path.iterdir()) == []


@pytest.mark.asyncio
async def test_bridge_rejects_paths_outside_sandbox_workspace(tmp_path: Path) -> None:
    async def build(
        source_path: str,
        candidate_path: str,
        output_path: str,
    ) -> dict[str, Any]:
        return _success(
            source_path=source_path,
            candidate_path=candidate_path,
            output_path=output_path,
        )

    tool = StructuredTool.from_function(
        coroutine=build,
        name="build_application_candidate",
        description="Build target.",
    )
    backend = _Backend({})
    registry = bridge_migration_mcp_registry(
        _registry("build_application_candidate", tool),
        backend=lambda: cast(SandboxBackendProtocol, backend),
        thread_id="private-thread",
        bridge_root=str(tmp_path),
    )

    with pytest.raises(MCPBridgeError, match="below /workspace"):
        await registry.curated[0].tool.ainvoke(
            {
                "source_path": "/etc/passwd",
                "candidate_path": "/workspace/migration/generated/candidate.zip",
                "output_path": "/workspace/migration/output/target.ods",
            }
        )

    assert backend.downloads == []
    assert backend.uploads == []


def test_path_bearing_tools_are_hidden_without_configured_bridge() -> None:
    async def build(
        source_path: str,
        candidate_path: str,
        output_path: str,
    ) -> dict[str, Any]:
        return _success(
            source_path=source_path,
            candidate_path=candidate_path,
            output_path=output_path,
        )

    tool = StructuredTool.from_function(
        coroutine=build,
        name="build_application_candidate",
        description="Build target.",
    )

    registry = bridge_migration_mcp_registry(
        _registry("build_application_candidate", tool),
        backend=lambda: cast(SandboxBackendProtocol, _Backend({})),
        thread_id="private-thread",
        bridge_root=None,
    )

    assert registry.curated == ()
    runtime_health = registry.health["runtime"]
    assert runtime_health.capabilities == ()
    assert runtime_health.reason == "path-bearing tools withheld: secure bridge not configured"


def test_bridge_preserves_mcp_json_schema_without_root_wrapper(tmp_path: Path) -> None:
    async def build(
        source_path: str,
        candidate_path: str,
        output_path: str,
    ) -> dict[str, Any]:
        return _success(
            source_path=source_path,
            candidate_path=candidate_path,
            output_path=output_path,
        )

    schema = {
        "type": "object",
        "properties": {
            "source_path": {"type": "string"},
            "candidate_path": {"type": "string"},
            "output_path": {"type": "string"},
        },
        "required": ["source_path", "candidate_path", "output_path"],
        "additionalProperties": False,
    }
    tool = StructuredTool(
        name="build_application_candidate",
        description="Build target.",
        args_schema=schema,
        coroutine=build,
    )

    registry = bridge_migration_mcp_registry(
        _registry("build_application_candidate", tool),
        backend=lambda: cast(SandboxBackendProtocol, _Backend({})),
        thread_id="private-thread",
        bridge_root=str(tmp_path),
    )

    bridged = registry.curated[0].tool
    tool_call_schema = bridged.tool_call_schema
    assert bridged.args_schema == schema
    assert tool_call_schema == {
        **schema,
        "description": "Build target.",
    }
    assert isinstance(tool_call_schema, dict)
    assert "root" not in tool_call_schema["properties"]


@pytest.mark.asyncio
async def test_scenario_bridge_binds_target_candidate_and_evidence(tmp_path: Path) -> None:
    async def run_scenario(
        target_path: str,
        candidate_path: str,
        evidence_path: str,
        scenario_id: str,
        actions: list[dict[str, Any]],
        adapter_config: dict[str, Any],
    ) -> dict[str, Any]:
        assert Path(target_path).read_bytes() == b"native-ods"
        assert Path(candidate_path).read_bytes() == b"candidate-bundle"
        assert scenario_id == "keyboard-control"
        assert actions == [{"kind": "key", "value": "LEFT"}]
        assert adapter_config == {"sheet": "Game"}
        Path(evidence_path).write_bytes(b"real-gui-evidence")
        return _success(
            target_build="26.2.4.2",
            candidate_bundle_sha256="a" * 64,
        )

    tool = StructuredTool.from_function(
        coroutine=run_scenario,
        name="run_application_scenario",
        description="Run application scenario.",
    )
    backend = _Backend(
        {
            "/workspace/migration/output/target.ods": b"native-ods",
            "/workspace/migration/generated/candidate.zip": b"candidate-bundle",
        }
    )
    registry = bridge_migration_mcp_registry(
        _registry("run_application_scenario", tool),
        backend=lambda: cast(SandboxBackendProtocol, backend),
        thread_id="private-thread",
        bridge_root=str(tmp_path),
    )

    result = await registry.curated[0].tool.ainvoke(
        {
            "target_path": "/workspace/migration/output/target.ods",
            "candidate_path": "/workspace/migration/generated/candidate.zip",
            "evidence_path": "/workspace/migration/evidence/keyboard-control.zip",
            "scenario_id": "keyboard-control",
            "actions": [{"kind": "key", "value": "LEFT"}],
            "adapter_config": {"sheet": "Game"},
        }
    )

    assert result["success"] is True
    assert backend.downloads == [
        "/workspace/migration/output/target.ods",
        "/workspace/migration/generated/candidate.zip",
    ]
    assert backend.uploads == ["/workspace/migration/evidence/keyboard-control.zip"]
    assert backend.files["/workspace/migration/evidence/keyboard-control.zip"] == b"real-gui-evidence"
    assert list(tmp_path.iterdir()) == []


@pytest.mark.asyncio
async def test_replay_bridge_forwards_declared_replay_id(tmp_path: Path) -> None:
    async def bundle_replays(
        evidence_paths: dict[str, str],
        output_path: str,
        replay_id: str,
    ) -> dict[str, Any]:
        assert replay_id == "interactive-game"
        assert set(evidence_paths) == {"keyboard-control", "timer-tick"}
        assert {
            scenario: Path(path).read_bytes() for scenario, path in evidence_paths.items()
        } == {
            "keyboard-control": b"keyboard-evidence",
            "timer-tick": b"timer-evidence",
        }
        Path(output_path).write_bytes(b"replay-bundle")
        return _success(target_build="26.2.4.2")

    tool = StructuredTool.from_function(
        coroutine=bundle_replays,
        name="bundle_application_replays",
        description="Bundle replay.",
    )
    backend = _Backend(
        {
            "/workspace/migration/evidence/keyboard-control.zip": b"keyboard-evidence",
            "/workspace/migration/evidence/timer-tick.zip": b"timer-evidence",
        }
    )
    registry = bridge_migration_mcp_registry(
        _registry("bundle_application_replays", tool),
        backend=lambda: cast(SandboxBackendProtocol, backend),
        thread_id="private-thread",
        bridge_root=str(tmp_path),
    )

    result = await registry.curated[0].tool.ainvoke(
        {
            "evidence_paths": {
                "keyboard-control": "/workspace/migration/evidence/keyboard-control.zip",
                "timer-tick": "/workspace/migration/evidence/timer-tick.zip",
            },
            "output_path": "/workspace/migration/public/replay.zip",
            "replay_id": "interactive-game",
        }
    )

    assert result["success"] is True
    assert backend.uploads == ["/workspace/migration/public/replay.zip"]
    assert backend.files["/workspace/migration/public/replay.zip"] == b"replay-bundle"
    assert list(tmp_path.iterdir()) == []


@pytest.mark.asyncio
async def test_failed_open_removes_private_document_copy(tmp_path: Path) -> None:
    async def open_document(session_id: str, document_path: str) -> dict[str, Any]:
        assert session_id == "runtime-session"
        assert Path(document_path).read_bytes() == b"private-input"
        return {
            "success": False,
            "operation_status": "FAILED",
            "error": {"message": "office rejected document"},
        }

    tool = StructuredTool.from_function(
        coroutine=open_document,
        name="open_document",
        description="Open target.",
    )
    backend = _Backend({"/workspace/migration/input.ods": b"private-input"})
    registry = bridge_migration_mcp_registry(
        _registry("open_document", tool),
        backend=lambda: cast(SandboxBackendProtocol, backend),
        thread_id="private-thread",
        bridge_root=str(tmp_path),
    )

    with pytest.raises(MCPBridgeError, match="office rejected document"):
        await registry.curated[0].tool.ainvoke(
            {
                "session_id": "runtime-session",
                "document_path": "/workspace/migration/input.ods",
            }
        )

    assert backend.downloads == ["/workspace/migration/input.ods"]
    assert list((tmp_path / "sessions").iterdir()) == []


@pytest.mark.asyncio
async def test_session_save_returns_output_to_same_private_sandbox(tmp_path: Path) -> None:
    async def open_document(session_id: str, document_path: str) -> dict[str, Any]:
        assert session_id == "runtime-session"
        assert Path(document_path).read_bytes() == b"source-ods"
        return _success(session_id=session_id)

    async def save(session_id: str, output_path: str | None = None) -> dict[str, Any]:
        assert session_id == "runtime-session"
        assert output_path is not None
        Path(output_path).write_bytes(b"saved-ods")
        return _success(session_id=session_id)

    open_tool = StructuredTool.from_function(
        coroutine=open_document,
        name="open_document",
        description="Open target.",
    )
    save_tool = StructuredTool.from_function(
        coroutine=save,
        name="save",
        description="Save target.",
    )
    backend = _Backend({"/workspace/migration/output/target.ods": b"source-ods"})
    open_registry = bridge_migration_mcp_registry(
        _registry("open_document", open_tool),
        backend=lambda: cast(SandboxBackendProtocol, backend),
        thread_id="private-thread",
        bridge_root=str(tmp_path),
    )
    save_registry = bridge_migration_mcp_registry(
        _registry("save", save_tool),
        backend=lambda: cast(SandboxBackendProtocol, backend),
        thread_id="private-thread",
        bridge_root=str(tmp_path),
    )

    await open_registry.curated[0].tool.ainvoke(
        {
            "session_id": "runtime-session",
            "document_path": "/workspace/migration/output/target.ods",
        }
    )
    result = await save_registry.curated[0].tool.ainvoke(
        {
            "session_id": "runtime-session",
            "output_path": "/workspace/migration/evidence/saved.ods",
        }
    )

    assert result["success"] is True
    assert backend.files["/workspace/migration/evidence/saved.ods"] == b"saved-ods"
    assert backend.uploads == ["/workspace/migration/evidence/saved.ods"]
