from __future__ import annotations

import base64
import hashlib
import io
import json
import zipfile
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from fastapi import HTTPException

from agent.api import xlsliberator as migration_api
from agent.xlsliberator import migrations
from agent.xlsliberator.migrations import (
    FollowUpArtifact,
    HydratedWorkbook,
    MigrationArtifact,
    WorkbookArtifactError,
    WorkbookFollowUpRequest,
    WorkbookMigrationRequest,
)
from agent.xlsliberator.security import CapabilityName


def _zip_bytes(content: bytes = b"<workbook/>") -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", b"<Types/>")
        archive.writestr("xl/workbook.xml", content)
    return output.getvalue()


def _request(data: bytes, **overrides: Any) -> WorkbookMigrationRequest:
    owner_id = overrides.pop("owner_id", "tenant-1")
    artifact = MigrationArtifact.model_validate(
        {
            "original_filename": "book.xlsx",
            "sha256": hashlib.sha256(data).hexdigest(),
            "media_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "artifact_base64": base64.b64encode(data).decode(),
            **overrides.pop("artifact", {}),
        }
    )
    return WorkbookMigrationRequest(owner_id=owner_id, artifact=artifact, **overrides)


def test_validate_artifact_rejects_invalid_hash() -> None:
    data = _zip_bytes()
    with pytest.raises(WorkbookArtifactError, match="sha256"):
        migrations.validate_artifact(
            data=data,
            original_filename="book.xlsx",
            expected_sha256="0" * 64,
            declared_media_type=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
        )


def test_validate_artifact_rejects_huge_file(monkeypatch: pytest.MonkeyPatch) -> None:
    data = _zip_bytes()
    monkeypatch.setattr(migrations, "MAX_WORKBOOK_BYTES", len(data) - 1)
    with pytest.raises(WorkbookArtifactError, match="size limit"):
        migrations.validate_artifact(
            data=data,
            original_filename="book.xlsx",
            expected_sha256=hashlib.sha256(data).hexdigest(),
            declared_media_type=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
        )


def test_validate_artifact_rejects_zip_bomb_ratio() -> None:
    data = _zip_bytes(b"A" * 1_000_000)
    with pytest.raises(WorkbookArtifactError, match="compression ratio"):
        migrations.validate_artifact(
            data=data,
            original_filename="book.xlsx",
            expected_sha256=hashlib.sha256(data).hexdigest(),
            declared_media_type=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
        )


def test_validate_artifact_rejects_unsupported_media_type() -> None:
    data = _zip_bytes()
    with pytest.raises(WorkbookArtifactError, match="unsupported media type"):
        migrations.validate_artifact(
            data=data,
            original_filename="book.xlsx",
            expected_sha256=hashlib.sha256(data).hexdigest(),
            declared_media_type="text/html",
        )


@pytest.mark.asyncio
async def test_interrupted_download_is_reported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def interrupted(*_args: Any, **_kwargs: Any) -> Any:
        raise httpx.ReadError("connection reset")

    monkeypatch.setattr(migrations, "_stream_safe_download", interrupted)
    with pytest.raises(WorkbookArtifactError, match="interrupted"):
        await migrations.download_artifact("https://files.example.test/book.xlsx")


def test_thread_id_is_stable_and_tenant_scoped() -> None:
    data = _zip_bytes()
    first = _request(data)
    duplicate = _request(data)
    other_tenant = _request(data, owner_id="tenant-2")
    assert migrations.deterministic_thread_id(first) == migrations.deterministic_thread_id(
        duplicate
    )
    assert migrations.deterministic_thread_id(first) != migrations.deterministic_thread_id(
        other_tenant
    )


class _FakeThreads:
    def __init__(self, metadata: dict[str, Any] | None = None) -> None:
        self.metadata = dict(metadata or {})
        self.updates: list[dict[str, Any]] = []

    async def create(
        self,
        *,
        thread_id: str,
        metadata: dict[str, Any],
        if_exists: str,
    ) -> dict[str, Any]:
        assert thread_id
        assert if_exists == "do_nothing"
        if not self.metadata:
            self.metadata.update(metadata)
        return {"thread_id": thread_id}

    async def get(self, thread_id: str) -> dict[str, Any]:
        return {"thread_id": thread_id, "metadata": dict(self.metadata)}

    async def update(self, *, thread_id: str, metadata: dict[str, Any]) -> None:
        assert thread_id
        self.metadata.update(metadata)
        self.updates.append(metadata)


class _FakeRuns:
    def __init__(self, statuses: list[dict[str, Any]] | None = None) -> None:
        self.statuses = statuses or []

    async def list(self, _thread_id: str) -> list[dict[str, Any]]:
        return self.statuses

    async def cancel_many(self, *, thread_id: str, run_ids: list[str]) -> None:
        assert thread_id
        assert run_ids


class _FakeClient:
    def __init__(self, metadata: dict[str, Any] | None = None) -> None:
        self.threads = _FakeThreads(metadata)
        self.runs = _FakeRuns()


@pytest.mark.asyncio
async def test_duplicate_delivery_does_not_start_another_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = _zip_bytes()
    body = _request(data)
    current_delivery = migrations.delivery_id(body)
    fake = _FakeClient(
        {
            "task_kind": migrations.TASK_KIND,
            "migration_delivery_id": current_delivery,
            "migration_status": "running",
            "migration_run_id": "run-1",
            "artifact_locations": {"source": "source/book.xlsx", "dossier": "migration/"},
        }
    )
    monkeypatch.setenv("XLSLIBERATOR_TRIGGER_TOKEN", "secret")
    monkeypatch.setattr(migration_api, "langgraph_client", lambda: fake)

    async def must_not_dispatch(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("duplicate delivery dispatched a second run")

    monkeypatch.setattr(migration_api, "dispatch_agent_run", must_not_dispatch)
    result = await migration_api.create_workbook_migration(body, "Bearer secret", "tenant-1")
    assert result.duplicate is True
    assert result.run_id == "run-1"


@pytest.mark.asyncio
async def test_trigger_hydrates_and_persists_sandbox_relative_locations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = _zip_bytes()
    body = _request(data)
    fake = _FakeClient()
    monkeypatch.setenv("XLSLIBERATOR_TRIGGER_TOKEN", "secret")
    monkeypatch.setattr(migration_api, "langgraph_client", lambda: fake)

    async def resolved(_artifact: MigrationArtifact) -> bytes:
        return data

    async def backend(_thread_id: str) -> object:
        return object()

    async def hydrated(
        _backend: object,
        _body: WorkbookMigrationRequest,
        _data: bytes,
    ) -> HydratedWorkbook:
        return HydratedWorkbook(
            source_path="/workspace/source/book.xlsx",
            dossier_path="/workspace/migration",
            metadata_path="/workspace/source/source-metadata.json",
            bounded_context={"task_kind": migrations.TASK_KIND, "summary": {"sheet_count": 1}},
        )

    async def dispatch(*_args: Any, **_kwargs: Any) -> dict[str, str]:
        return {"run_id": "run-2"}

    monkeypatch.setattr(migration_api, "resolve_artifact", resolved)
    monkeypatch.setattr(migration_api, "_migration_backend", backend)
    monkeypatch.setattr(migration_api, "hydrate_workbook", hydrated)
    monkeypatch.setattr(migration_api, "dispatch_agent_run", dispatch)

    result = await migration_api.create_workbook_migration(body, "Bearer secret", "tenant-1")
    assert result.duplicate is False
    assert result.run_id == "run-2"
    assert result.artifact_locations == {}
    assert fake.threads.metadata["artifact_locations"]["source"] == "source/book.xlsx"
    assert all(
        not path.startswith("/") for path in fake.threads.metadata["artifact_locations"].values()
    )
    assert "artifact_base64" not in json.dumps(fake.threads.metadata)


@pytest.mark.asyncio
async def test_trigger_missing_secure_capability_is_unavailable_before_hydration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = _zip_bytes()
    body = _request(data, required_capabilities=[CapabilityName.HTTP])
    fake = _FakeClient()
    monkeypatch.setenv("XLSLIBERATOR_TRIGGER_TOKEN", "secret")
    monkeypatch.setenv("XLSLIBERATOR_CAPABILITY_GRANTS_JSON", "[]")
    monkeypatch.setattr(migration_api, "langgraph_client", lambda: fake)

    async def must_not_hydrate(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("unavailable capability reached workbook hydration")

    monkeypatch.setattr(migration_api, "hydrate_workbook", must_not_hydrate)

    with pytest.raises(HTTPException) as error:
        await migration_api.create_workbook_migration(body, "Bearer secret", "tenant-1")

    assert error.value.status_code == 503
    assert fake.threads.metadata["migration_status"] == "unavailable"
    assert fake.threads.metadata["xlsliberator_security"]["status"] == "UNAVAILABLE"
    assert fake.threads.metadata["xlsliberator_security"]["missing"] == ["http"]


class _FollowUpBackend:
    def __init__(self) -> None:
        self.uploaded: list[tuple[str, bytes]] = []

    async def aexecute(self, command: str, *, timeout: int) -> SimpleNamespace:
        assert command == "mkdir -p /workspace/dependencies"
        assert timeout == 30
        return SimpleNamespace(exit_code=0)

    async def aupload_files(self, files: list[tuple[str, bytes]]) -> list[dict[str, Any]]:
        self.uploaded.extend(files)
        return [{"path": files[0][0], "error": None}]


@pytest.mark.asyncio
async def test_follow_up_attachment_resumes_same_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = _zip_bytes()
    body = WorkbookFollowUpRequest(
        requirements="Preserve the monthly import behavior.",
        dependency=FollowUpArtifact(
            original_filename="dependency.xlsx",
            sha256=hashlib.sha256(data).hexdigest(),
            media_type="application/octet-stream",
            artifact_base64=base64.b64encode(data).decode(),
        ),
    )
    fake = _FakeClient(
        {
            "task_kind": migrations.TASK_KIND,
            "owner_id": "tenant-1",
            "artifact_locations": {"dossier": "migration/"},
        }
    )
    backend = _FollowUpBackend()
    monkeypatch.setenv("XLSLIBERATOR_TRIGGER_TOKEN", "secret")
    monkeypatch.setattr(migration_api, "langgraph_client", lambda: fake)

    async def resolved(_artifact: object) -> bytes:
        return data

    async def dispatch(*args: Any, **_kwargs: Any) -> dict[str, str]:
        assert args[0] == "thread-1"
        return {"run_id": "run-follow-up"}

    async def async_backend(_thread_id: str) -> _FollowUpBackend:
        return backend

    monkeypatch.setattr(migration_api, "resolve_dependency_artifact", resolved)
    monkeypatch.setattr(migration_api, "_migration_backend", async_backend)
    monkeypatch.setattr(migration_api, "dispatch_agent_run", dispatch)
    result = await migration_api.add_workbook_follow_up(
        "thread-1", body, "Bearer secret", "tenant-1"
    )
    assert result.thread_id == "thread-1"
    assert result.run_id == "run-follow-up"
    assert backend.uploaded[0][0].startswith("/workspace/dependencies/")
    assert fake.threads.metadata["follow_up_requirements"] == [
        "Preserve the monthly import behavior."
    ]


class _DeliveryBackend:
    def __init__(self) -> None:
        self.files = {
            "dossier.md": b"# Dossier\n",
            "plan.md": b"# Plan\n",
            "output/target.ods": b"ods",
            "acceptance/scenarios.json": b'{"scenarios":[]}',
            "generated/bridge.py": b"def run(): return 1\n",
            "evidence/libreoffice-execution.json": b'{"status":"passed"}',
            "evidence/save-reopen.json": b'{"status":"passed"}',
            "evidence/trajectories/formula.json": b'{"status":"complete"}',
            "evidence/hidden/cases.json": b'{"secret":"hidden"}',
            "logs/runtime.log": b"completed\n",
            "unresolved.md": b"# Unresolved\n\nNone.\n",
            "reviewer/result.json": b'{"verdict":"APPROVE"}',
        }
        self.commands: list[str] = []

    async def aexecute(self, command: str, *, timeout: int) -> SimpleNamespace:
        self.commands.append(command)
        if command.startswith("find /workspace/migration"):
            assert timeout == 30
            output = "\n".join(f"{path}\t{len(content)}" for path, content in self.files.items())
            return SimpleNamespace(exit_code=0, output=output)
        assert command == "rm -rf /workspace/source /workspace/dependencies"
        assert timeout == 30
        return SimpleNamespace(exit_code=0, output="")

    async def adownload_files(self, paths: list[str]) -> list[dict[str, Any]]:
        relative = paths[0].removeprefix("/workspace/migration/")
        return [{"content": self.files[relative], "error": None}]


@pytest.mark.asyncio
async def test_status_events_and_artifacts_are_owner_scoped_and_sanitized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeClient(
        {
            "task_kind": migrations.TASK_KIND,
            "owner_id": "tenant-1",
            "migration_status": "running",
            "migration_run_id": "run-1",
        }
    )
    fake.runs.statuses = [{"run_id": "run-1", "status": "success"}]
    backend = _DeliveryBackend()
    monkeypatch.setenv("XLSLIBERATOR_TRIGGER_TOKEN", "secret")
    monkeypatch.setattr(migration_api, "langgraph_client", lambda: fake)

    async def delivery_backend(_thread_id: str) -> _DeliveryBackend:
        return backend

    monkeypatch.setattr(migration_api, "_migration_backend", delivery_backend)

    result = await migration_api.get_workbook_migration("thread-1", "Bearer secret", "tenant-1")
    assert result.status == "complete"
    assert {artifact.name for artifact in result.artifacts} == {
        "dossier.md",
        "plan.md",
        "target.ods",
        "scenarios.json",
        "bridge.py",
        "libreoffice-execution.json",
        "save-reopen.json",
        "formula.json",
        "runtime.log",
        "unresolved.md",
        "result.json",
    }
    assert all("/workspace/" not in artifact.name for artifact in result.artifacts)

    events = await migration_api.get_workbook_migration_events(
        "thread-1", 0, "Bearer secret", "tenant-1"
    )
    assert events.events[-1].stage == "final"
    assert all("path" not in event.message.lower() for event in events.events)

    with pytest.raises(HTTPException) as exc_info:
        await migration_api.get_workbook_migration("thread-1", "Bearer secret", "tenant-2")
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_publication_check_blocks_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = _DeliveryBackend()
    backend.files["logs/runtime.log"] = b"Authorization: Bearer secret-token"

    async def delivery_backend(_thread_id: str) -> _DeliveryBackend:
        return backend

    monkeypatch.setattr(migration_api, "_migration_backend", delivery_backend)
    artifact = next(
        candidate
        for candidate in await migration_api._public_artifacts("thread-1")
        if candidate.summary.name == "runtime.log"
    )
    with pytest.raises(HTTPException) as exc_info:
        await migration_api._artifact_bytes("thread-1", artifact)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_publication_redacts_internal_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = _DeliveryBackend()
    backend.files["logs/runtime.log"] = b"opened /workspace/migration/output/target.ods\n"

    async def delivery_backend(_thread_id: str) -> _DeliveryBackend:
        return backend

    monkeypatch.setattr(migration_api, "_migration_backend", delivery_backend)
    artifact = next(
        candidate
        for candidate in await migration_api._public_artifacts("thread-1")
        if candidate.summary.name == "runtime.log"
    )

    content = await migration_api._artifact_bytes("thread-1", artifact)

    assert b"/workspace/" not in content
    assert b"[internal-path]" in content


@pytest.mark.asyncio
async def test_completion_deletes_private_sources_before_public_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeClient(
        {
            "task_kind": migrations.TASK_KIND,
            "owner_id": "tenant-1",
            "migration_status": "running",
            "migration_run_id": "run-1",
            "privacy_retention": {
                "classification": "private",
                "retain_days": 14,
                "delete_source_after_completion": True,
            },
        }
    )
    fake.runs.statuses = [{"run_id": "run-1", "status": "success"}]
    backend = _DeliveryBackend()
    monkeypatch.setenv("XLSLIBERATOR_TRIGGER_TOKEN", "secret")
    monkeypatch.setattr(migration_api, "langgraph_client", lambda: fake)

    async def delivery_backend(_thread_id: str) -> _DeliveryBackend:
        return backend

    monkeypatch.setattr(migration_api, "_migration_backend", delivery_backend)

    result = await migration_api.get_workbook_migration("thread-1", "Bearer secret", "tenant-1")

    assert result.status == "complete"
    assert "rm -rf /workspace/source /workspace/dependencies" in backend.commands
    assert isinstance(fake.threads.metadata.get("source_deleted_at"), str)


@pytest.mark.asyncio
async def test_expired_migration_is_cleaned_and_returns_gone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeClient(
        {
            "task_kind": migrations.TASK_KIND,
            "owner_id": "tenant-1",
            "migration_status": "running",
            "retention_expires_at": (datetime.now(UTC) - timedelta(seconds=1)).isoformat(),
        }
    )
    monkeypatch.setenv("XLSLIBERATOR_TRIGGER_TOKEN", "secret")
    monkeypatch.setattr(migration_api, "langgraph_client", lambda: fake)
    cleaned: list[str] = []

    async def backend(_thread_id: str) -> object:
        return object()

    async def cleanup(_backend: object) -> None:
        cleaned.append("yes")

    monkeypatch.setattr(migration_api, "_migration_backend", backend)
    monkeypatch.setattr(migration_api, "cleanup_migration_workspace", cleanup)

    with pytest.raises(HTTPException) as exc_info:
        await migration_api.get_workbook_migration("thread-1", "Bearer secret", "tenant-1")

    assert exc_info.value.status_code == 410
    assert cleaned == ["yes"]
    assert fake.threads.metadata["migration_status"] == "cleaned"
