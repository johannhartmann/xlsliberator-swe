from __future__ import annotations

import base64
import hashlib
import io
import json
import zipfile
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from agent.api import xlsliberator as migration_api
from agent.xlsliberator import migrations
from agent.xlsliberator.migrations import (
    HydratedWorkbook,
    MigrationArtifact,
    WorkbookArtifactError,
    WorkbookFollowUpRequest,
    WorkbookMigrationRequest,
)


def _zip_bytes(content: bytes = b"<workbook/>") -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", b"<Types/>")
        archive.writestr("xl/workbook.xml", content)
    return output.getvalue()


def _request(data: bytes, **overrides: Any) -> WorkbookMigrationRequest:
    owner_id = overrides.pop("owner_id", "tenant-1")
    artifact = {
        "original_filename": "book.xlsx",
        "sha256": hashlib.sha256(data).hexdigest(),
        "media_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "artifact_base64": base64.b64encode(data).decode(),
    }
    artifact.update(overrides.pop("artifact", {}))
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
    async def list(self, _thread_id: str) -> list[dict[str, Any]]:
        return []

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
    result = await migration_api.create_workbook_migration(body, "Bearer secret")
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

    result = await migration_api.create_workbook_migration(body, "Bearer secret")
    assert result.duplicate is False
    assert result.run_id == "run-2"
    assert result.artifact_locations["source"] == "source/book.xlsx"
    assert all(not path.startswith("/") for path in result.artifact_locations.values())
    assert "artifact_base64" not in json.dumps(fake.threads.metadata)


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
        dependency={
            "original_filename": "dependency.xlsx",
            "sha256": hashlib.sha256(data).hexdigest(),
            "media_type": "application/octet-stream",
            "artifact_base64": base64.b64encode(data).decode(),
        },
    )
    fake = _FakeClient(
        {
            "task_kind": migrations.TASK_KIND,
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
    result = await migration_api.add_workbook_follow_up("thread-1", body, "Bearer secret")
    assert result.thread_id == "thread-1"
    assert result.run_id == "run-follow-up"
    assert backend.uploaded[0][0].startswith("/workspace/dependencies/")
    assert fake.threads.metadata["follow_up_requirements"] == [
        "Preserve the monthly import behavior."
    ]
