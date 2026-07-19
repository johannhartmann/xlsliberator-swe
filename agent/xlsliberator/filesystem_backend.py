"""Filesystem-only view of an executable migration sandbox.

DeepAgents deliberately refuses to combine filesystem permissions with an
execution-capable backend: an unrestricted shell command could bypass the
tool-level path rules. Migration specialists do not need a shell. This adapter
delegates every file operation to the live sandbox while intentionally not
implementing ``SandboxBackendProtocol`` or exposing ``execute``.
"""

from __future__ import annotations

from collections.abc import Callable

from deepagents.backends.protocol import (
    BackendProtocol,
    DeleteResult,
    EditResult,
    FileDownloadResponse,
    FileUploadResponse,
    GlobResult,
    GrepResult,
    LsResult,
    ReadResult,
    WriteResult,
)

BackendResolver = Callable[[], BackendProtocol]


class FilesystemOnlyBackend(BackendProtocol):
    """Delegate sandbox file operations without granting command execution."""

    def __init__(self, resolver: BackendResolver) -> None:
        self._resolver = resolver

    def _backend(self) -> BackendProtocol:
        return self._resolver()

    def ls(self, path: str) -> LsResult:
        return self._backend().ls(path)

    async def als(self, path: str) -> LsResult:
        return await self._backend().als(path)

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> ReadResult:
        return self._backend().read(file_path, offset, limit)

    async def aread(
        self,
        file_path: str,
        offset: int = 0,
        limit: int = 2000,
    ) -> ReadResult:
        return await self._backend().aread(file_path, offset, limit)

    def grep(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
        *,
        max_count: int | None = None,
    ) -> GrepResult:
        return self._backend().grep(pattern, path, glob, max_count=max_count)

    async def agrep(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
        *,
        max_count: int | None = None,
    ) -> GrepResult:
        return await self._backend().agrep(
            pattern,
            path,
            glob,
            max_count=max_count,
        )

    def glob(self, pattern: str, path: str | None = None) -> GlobResult:
        return self._backend().glob(pattern, path)

    async def aglob(self, pattern: str, path: str | None = None) -> GlobResult:
        return await self._backend().aglob(pattern, path)

    def write(self, file_path: str, content: str) -> WriteResult:
        return self._backend().write(file_path, content)

    async def awrite(self, file_path: str, content: str) -> WriteResult:
        return await self._backend().awrite(file_path, content)

    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,  # noqa: FBT001, FBT002
    ) -> EditResult:
        return self._backend().edit(
            file_path,
            old_string,
            new_string,
            replace_all,
        )

    async def aedit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,  # noqa: FBT001, FBT002
    ) -> EditResult:
        return await self._backend().aedit(
            file_path,
            old_string,
            new_string,
            replace_all,
        )

    def delete(self, file_path: str) -> DeleteResult:
        return self._backend().delete(file_path)

    async def adelete(self, file_path: str) -> DeleteResult:
        return await self._backend().adelete(file_path)

    def upload_files(
        self,
        files: list[tuple[str, bytes]],
    ) -> list[FileUploadResponse]:
        return self._backend().upload_files(files)

    async def aupload_files(
        self,
        files: list[tuple[str, bytes]],
    ) -> list[FileUploadResponse]:
        return await self._backend().aupload_files(files)

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        return self._backend().download_files(paths)

    async def adownload_files(
        self,
        paths: list[str],
    ) -> list[FileDownloadResponse]:
        return await self._backend().adownload_files(paths)
