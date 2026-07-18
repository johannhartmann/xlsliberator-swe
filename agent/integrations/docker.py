"""Hardened Docker sandbox backend for XLSLiberator migration jobs."""

from __future__ import annotations

import json
import re
import secrets
import subprocess
from collections.abc import Sequence
from typing import Any, Final

from deepagents.backends.protocol import (
    ExecuteResponse,
    FileDownloadResponse,
    FileUploadResponse,
)
from deepagents.backends.sandbox import BaseSandbox
from langsmith.sandbox import SandboxClientError

from agent.xlsliberator.settings import XLSLiberatorSettings

_CONTAINER_NAME: Final = re.compile(r"^xlsliberator-swe-[0-9a-f]{24}$")
_IMAGE_ID: Final = re.compile(r"^sha256:[0-9a-f]{64}$")
_SOURCE_REVISION: Final = re.compile(r"^[0-9a-f]{40}$")
_PROVIDER_LABEL: Final = "org.open-swe.sandbox.provider"
_IMAGE_LABEL: Final = "org.open-swe.sandbox.image-id"
_OFFICE_LABEL: Final = "org.xlsliberator.libreoffice.version"
_VERSION_LABEL: Final = "org.opencontainers.image.version"
_OPEN_SWE_REVISION_LABEL: Final = "org.opencontainers.image.revision"
_XLSLIBERATOR_REVISION_LABEL: Final = "org.xlsliberator.source.revision"
_EXPECTED_OFFICE_BUILD: Final = "26.2.4.2"
_MAX_EXECUTE_OUTPUT_BYTES: Final = 500 * 1024
_DOCKER_CONTROL_TIMEOUT_SECONDS: Final = 30
_TRANSFER_TIMEOUT_SECONDS: Final = 120

_EXECUTE_SCRIPT: Final = r"""
set -u
limit="$1"
duration="$2"
command="$3"
capture="$(mktemp /tmp/.open-swe-execute.XXXXXX)" || exit 74
trap 'rm -f "$capture"' EXIT HUP INT TERM
timeout --signal=KILL --kill-after=5s "$duration" /bin/sh -lc "$command" \
  >"$capture" 2>&1
status=$?
size="$(wc -c <"$capture")"
truncated=0
if [ "$size" -gt "$limit" ]; then
  truncated=1
fi
printf '__OPEN_SWE_DOCKER_EXEC__ %s %s\n' "$status" "$truncated"
if [ "$truncated" -eq 0 ]; then
  cat "$capture"
else
  half=$((limit / 2))
  head -c "$half" "$capture"
  printf '\n... output truncated by Docker sandbox ...\n'
  tail -c "$half" "$capture"
fi
"""

_UPLOAD_SCRIPT: Final = r"""
set -eu
path="$1"
case "$path" in
  /workspace/*|/tmp/*|/home/sandbox/*) ;;
  *) exit 64 ;;
esac
parent="$(dirname -- "$path")"
mkdir -p -- "$parent" || exit 73
resolved="$(readlink -f -- "$parent")" || exit 64
case "$resolved" in
  /workspace|/workspace/*|/tmp|/tmp/*|/home/sandbox|/home/sandbox/*) ;;
  *) exit 64 ;;
esac
temporary="$(mktemp "$parent/.open-swe-upload.XXXXXX")" || exit 73
trap 'rm -f "$temporary"' EXIT HUP INT TERM
cat >"$temporary" || exit 73
chmod 0600 "$temporary" || exit 73
mv -f -- "$temporary" "$path" || exit 73
trap - EXIT HUP INT TERM
"""

_DOWNLOAD_SCRIPT: Final = r"""
set -eu
path="$1"
case "$path" in
  /workspace/*|/tmp/*|/home/sandbox/*) ;;
  *) exit 64 ;;
esac
if [ -d "$path" ]; then
  exit 65
fi
if [ ! -f "$path" ]; then
  exit 66
fi
resolved="$(readlink -f -- "$path")" || exit 64
case "$resolved" in
  /workspace/*|/tmp/*|/home/sandbox/*) ;;
  *) exit 64 ;;
esac
cat -- "$path" || exit 73
"""


def _decode(value: bytes) -> str:
    return value.decode("utf-8", errors="replace")


def _docker_error(operation: str, result: subprocess.CompletedProcess[bytes]) -> SandboxClientError:
    detail = _decode(result.stderr or result.stdout).strip()
    return SandboxClientError(f"Docker sandbox {operation} failed: {detail or result.returncode}")


def _run_docker(
    arguments: Sequence[str],
    *,
    input_bytes: bytes | None = None,
    timeout: int = _DOCKER_CONTROL_TIMEOUT_SECONDS,
) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            ["docker", *arguments],
            input=input_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SandboxClientError(f"Docker sandbox control command failed: {exc}") from exc


def _inspect_one(kind: str, reference: str) -> dict[str, Any]:
    result = _run_docker([kind, "inspect", reference])
    if result.returncode != 0:
        raise _docker_error(f"{kind} inspect", result)
    try:
        payload = json.loads(result.stdout)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SandboxClientError(f"Docker {kind} inspect returned invalid JSON") from exc
    if not isinstance(payload, list) or len(payload) != 1 or not isinstance(payload[0], dict):
        raise SandboxClientError(f"Docker {kind} inspect returned an unexpected payload")
    return payload[0]


def _image_reference(settings: XLSLiberatorSettings) -> str:
    digest = settings.sandbox_image_digest
    if digest is None:
        return settings.sandbox_image
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise ValueError("XLSLIBERATOR_SANDBOX_IMAGE_DIGEST must be a sha256 digest")
    repository = settings.sandbox_image.split("@", 1)[0]
    last_slash = repository.rfind("/")
    last_colon = repository.rfind(":")
    if last_colon > last_slash:
        repository = repository[:last_colon]
    return f"{repository}@{digest}"


def _validated_image(settings: XLSLiberatorSettings) -> str:
    image = _inspect_one("image", _image_reference(settings))
    image_id = image.get("Id")
    config = image.get("Config")
    labels = config.get("Labels") if isinstance(config, dict) else None
    if not isinstance(image_id, str) or not _IMAGE_ID.fullmatch(image_id):
        raise SandboxClientError("Docker sandbox image has no immutable sha256 image ID")
    if not isinstance(labels, dict):
        raise SandboxClientError("Docker sandbox image has no identity labels")
    expected_labels = {
        _OFFICE_LABEL: _EXPECTED_OFFICE_BUILD,
        _VERSION_LABEL: settings.sandbox_image_version,
    }
    for name, expected in expected_labels.items():
        if labels.get(name) != expected:
            raise SandboxClientError(
                f"Docker sandbox image label {name} must equal {expected!r}"
            )
    for name in (_OPEN_SWE_REVISION_LABEL, _XLSLIBERATOR_REVISION_LABEL):
        value = labels.get(name)
        if not isinstance(value, str) or not _SOURCE_REVISION.fullmatch(value):
            raise SandboxClientError(f"Docker sandbox image label {name} must be a commit SHA")
    return image_id


def _container_labels(container: dict[str, Any]) -> dict[str, str]:
    config = container.get("Config")
    labels = config.get("Labels") if isinstance(config, dict) else None
    if not isinstance(labels, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in labels.items()
    ):
        raise SandboxClientError("Docker sandbox container has invalid labels")
    return labels


def _validate_container(
    container_name: str,
    *,
    expected_image_id: str | None = None,
    settings: XLSLiberatorSettings,
) -> str:
    if not _CONTAINER_NAME.fullmatch(container_name):
        raise ValueError("Docker sandbox ID has an invalid format")
    container = _inspect_one("container", container_name)
    labels = _container_labels(container)
    image_id = container.get("Image")
    state = container.get("State")
    host_config = container.get("HostConfig")
    config = container.get("Config")
    if not isinstance(image_id, str) or not _IMAGE_ID.fullmatch(image_id):
        raise SandboxClientError("Docker sandbox container has an invalid image ID")
    if expected_image_id is not None and image_id != expected_image_id:
        raise SandboxClientError("Docker sandbox container image does not match configured image")
    if labels.get(_PROVIDER_LABEL) != "docker" or labels.get(_IMAGE_LABEL) != image_id:
        raise SandboxClientError("Docker sandbox container identity labels do not match")
    if labels.get(_OFFICE_LABEL) != _EXPECTED_OFFICE_BUILD:
        raise SandboxClientError("Docker sandbox container LibreOffice build does not match")
    if not isinstance(state, dict) or state.get("Running") is not True:
        raise SandboxClientError("Docker sandbox container is not running")
    if not isinstance(host_config, dict) or not isinstance(config, dict):
        raise SandboxClientError("Docker sandbox container configuration is unavailable")
    security_opt = host_config.get("SecurityOpt")
    cap_drop = host_config.get("CapDrop")
    tmpfs = host_config.get("Tmpfs")
    environment = config.get("Env")
    forbidden_environment = {
        "ANTHROPIC_API_KEY",
        "DOCKER_HOST",
        "GH_TOKEN",
        "GITHUB_TOKEN",
        "LANGSMITH_API_KEY",
        "OPENAI_API_KEY",
    }
    environment_names = (
        {
            value.partition("=")[0]
            for value in environment
            if isinstance(value, str)
        }
        if isinstance(environment, list)
        else set()
    )
    workspace_tmpfs = tmpfs.get("/workspace") if isinstance(tmpfs, dict) else None
    if (
        host_config.get("NetworkMode") != "none"
        or host_config.get("ReadonlyRootfs") is not True
        or host_config.get("Privileged") is True
        or host_config.get("PidMode") == "host"
        or host_config.get("IpcMode") == "host"
        or not isinstance(cap_drop, list)
        or "ALL" not in cap_drop
        or not isinstance(security_opt, list)
        or not {"no-new-privileges", "no-new-privileges:true"}.intersection(security_opt)
        or host_config.get("PidsLimit") != settings.sandbox_pids_limit
        or host_config.get("Memory") != settings.sandbox_memory_bytes
        or host_config.get("NanoCpus") != settings.sandbox_cpu_count * 1_000_000_000
        or config.get("User") != "10001:10001"
        or not isinstance(workspace_tmpfs, str)
        or f"size={settings.sandbox_disk_bytes}" not in workspace_tmpfs
        or "uid=10001" not in workspace_tmpfs
        or "gid=10001" not in workspace_tmpfs
        or bool(forbidden_environment.intersection(environment_names))
    ):
        raise SandboxClientError("Docker sandbox container security policy does not match")
    return image_id


class DockerSandbox(BaseSandbox):
    """DeepAgents backend backed by a locked-down, per-thread Docker container."""

    enable_capture_offload = True

    def __init__(
        self,
        container_name: str,
        *,
        settings: XLSLiberatorSettings,
        image_id: str,
    ) -> None:
        self._container_name = container_name
        self._settings = settings
        self._image_id = image_id

    @property
    def id(self) -> str:
        return self._container_name

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        if not isinstance(command, str) or "\x00" in command:
            raise ValueError("Docker sandbox command must be a NUL-free string")
        if timeout is not None and timeout < 0:
            raise ValueError("Docker sandbox timeout must not be negative")
        requested_timeout = timeout or self._settings.sandbox_command_timeout_seconds
        effective_timeout = min(
            requested_timeout,
            self._settings.sandbox_command_timeout_seconds,
        )
        result = _run_docker(
            [
                "exec",
                self._container_name,
                "/bin/sh",
                "-c",
                _EXECUTE_SCRIPT,
                "open-swe-execute",
                str(_MAX_EXECUTE_OUTPUT_BYTES),
                f"{effective_timeout}s",
                command,
            ],
            timeout=effective_timeout + 15,
        )
        if result.returncode != 0:
            raise _docker_error("execute", result)
        header, separator, output = result.stdout.partition(b"\n")
        parts = _decode(header).split()
        if (
            not separator
            or len(parts) != 3
            or parts[0] != "__OPEN_SWE_DOCKER_EXEC__"
            or not parts[1].lstrip("-").isdigit()
            or parts[2] not in {"0", "1"}
        ):
            raise SandboxClientError("Docker sandbox execute returned an invalid envelope")
        return ExecuteResponse(
            output=_decode(output),
            exit_code=int(parts[1]),
            truncated=parts[2] == "1",
        )

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        responses: list[FileUploadResponse] = []
        for path, content in files:
            if not isinstance(path, str) or "\x00" in path:
                responses.append(FileUploadResponse(path=str(path), error="invalid_path"))
                continue
            result = _run_docker(
                [
                    "exec",
                    "--interactive",
                    "--user",
                    "10001:10001",
                    self._container_name,
                    "/bin/sh",
                    "-c",
                    _UPLOAD_SCRIPT,
                    "open-swe-upload",
                    path,
                ],
                input_bytes=content,
                timeout=_TRANSFER_TIMEOUT_SECONDS,
            )
            if result.returncode == 0:
                responses.append(FileUploadResponse(path=path))
            elif result.returncode == 64:
                responses.append(FileUploadResponse(path=path, error="invalid_path"))
            elif result.returncode == 73:
                responses.append(FileUploadResponse(path=path, error="permission_denied"))
            else:
                responses.append(
                    FileUploadResponse(
                        path=path,
                        error=_decode(result.stderr or result.stdout).strip()
                        or f"upload failed with exit code {result.returncode}",
                    )
                )
        return responses

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        responses: list[FileDownloadResponse] = []
        for path in paths:
            if not isinstance(path, str) or "\x00" in path:
                responses.append(FileDownloadResponse(path=str(path), error="invalid_path"))
                continue
            result = _run_docker(
                [
                    "exec",
                    "--user",
                    "10001:10001",
                    self._container_name,
                    "/bin/sh",
                    "-c",
                    _DOWNLOAD_SCRIPT,
                    "open-swe-download",
                    path,
                ],
                timeout=_TRANSFER_TIMEOUT_SECONDS,
            )
            if result.returncode == 0:
                responses.append(FileDownloadResponse(path=path, content=result.stdout))
            elif result.returncode == 64:
                responses.append(FileDownloadResponse(path=path, error="invalid_path"))
            elif result.returncode == 65:
                responses.append(FileDownloadResponse(path=path, error="is_directory"))
            elif result.returncode == 66:
                responses.append(FileDownloadResponse(path=path, error="file_not_found"))
            elif result.returncode == 73:
                responses.append(FileDownloadResponse(path=path, error="permission_denied"))
            else:
                responses.append(
                    FileDownloadResponse(
                        path=path,
                        error=_decode(result.stderr).strip()
                        or f"download failed with exit code {result.returncode}",
                    )
                )
        return responses


def _create_container(settings: XLSLiberatorSettings, image_id: str) -> str:
    container_name = f"xlsliberator-swe-{secrets.token_hex(12)}"
    result = _run_docker(
        [
            "run",
            "--detach",
            "--name",
            container_name,
            "--label",
            f"{_PROVIDER_LABEL}=docker",
            "--label",
            f"{_IMAGE_LABEL}={image_id}",
            "--label",
            f"{_OFFICE_LABEL}={_EXPECTED_OFFICE_BUILD}",
            "--network",
            "none",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges:true",
            "--cpus",
            str(settings.sandbox_cpu_count),
            "--memory",
            str(settings.sandbox_memory_bytes),
            "--pids-limit",
            str(settings.sandbox_pids_limit),
            "--tmpfs",
            (
                "/workspace:rw,nosuid,nodev,"
                f"size={settings.sandbox_disk_bytes},uid=10001,gid=10001,mode=0700"
            ),
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,nodev,size=2g,uid=10001,gid=10001,mode=1777",
            "--tmpfs",
            "/home/sandbox:rw,nosuid,nodev,size=512m,uid=10001,gid=10001,mode=0700",
            "--env",
            "XLSLIBERATOR_JOB_WORKSPACE=/workspace",
            "--env",
            (
                "XLSLIBERATOR_SANDBOX_COMMAND_TIMEOUT_SECONDS="
                f"{settings.sandbox_command_timeout_seconds}"
            ),
            image_id,
            "sleep",
            "infinity",
        ],
        timeout=120,
    )
    if result.returncode != 0:
        _run_docker(["rm", "--force", container_name])
        raise _docker_error("container creation", result)
    return container_name


def create_docker_sandbox(sandbox_id: str | None = None) -> DockerSandbox:
    """Create or reconnect to a Docker sandbox without forwarding host credentials."""

    settings = XLSLiberatorSettings.from_env()
    image_id = _validated_image(settings)
    if sandbox_id is None:
        container_name = _create_container(settings, image_id)
    else:
        container_name = sandbox_id
    _validate_container(
        container_name,
        expected_image_id=image_id,
        settings=settings,
    )
    return DockerSandbox(container_name, settings=settings, image_id=image_id)


def validate_docker_startup_config() -> None:
    """Fail server startup when the configured sandbox image is not immutable and exact."""

    _validated_image(XLSLiberatorSettings.from_env())
