from __future__ import annotations

import subprocess
from unittest.mock import patch

import pytest
from langsmith.sandbox import SandboxClientError

from agent.integrations import docker
from agent.xlsliberator.settings import XLSLiberatorSettings

IMAGE_ID = f"sha256:{'1' * 64}"
OPEN_SWE_REVISION = "2" * 40
XLSLIBERATOR_REVISION = "3" * 40


def _settings() -> XLSLiberatorSettings:
    return XLSLiberatorSettings.from_env(
        {
            "XLSLIBERATOR_SANDBOX_IMAGE": "example.invalid/sandbox:2026.07.0",
            "XLSLIBERATOR_SANDBOX_IMAGE_VERSION": "2026.07.0",
        }
    )


def _completed(
    returncode: int = 0,
    *,
    stdout: bytes = b"",
    stderr: bytes = b"",
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.CompletedProcess(
        args=["docker"],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


def _container_payload(*, running: bool = True) -> dict[str, object]:
    settings = _settings()
    return {
        "Image": IMAGE_ID,
        "State": {"Running": running},
        "Config": {
            "User": "10001:10001",
            "Env": [
                "PATH=/usr/local/bin:/usr/bin:/bin",
                "XLSLIBERATOR_JOB_WORKSPACE=/workspace",
            ],
            "Labels": {
                docker._PROVIDER_LABEL: "docker",
                docker._IMAGE_LABEL: IMAGE_ID,
                docker._OFFICE_LABEL: "26.2.4.2",
            },
        },
        "HostConfig": {
            "NetworkMode": "none",
            "ReadonlyRootfs": True,
            "CapDrop": ["ALL"],
            "SecurityOpt": ["no-new-privileges:true"],
            "Privileged": False,
            "PidMode": "",
            "IpcMode": "private",
            "PidsLimit": settings.sandbox_pids_limit,
            "Memory": settings.sandbox_memory_bytes,
            "NanoCpus": settings.sandbox_cpu_count * 1_000_000_000,
            "Tmpfs": {
                "/workspace": (
                    "rw,nosuid,nodev,"
                    f"size={settings.sandbox_disk_bytes},uid=10001,gid=10001,mode=0700"
                )
            },
        },
    }


def test_validated_image_resolves_to_immutable_id() -> None:
    image = {
        "Id": IMAGE_ID,
        "Config": {
            "Labels": {
                docker._OFFICE_LABEL: "26.2.4.2",
                docker._VERSION_LABEL: "2026.07.0",
                docker._OPEN_SWE_REVISION_LABEL: OPEN_SWE_REVISION,
                docker._XLSLIBERATOR_REVISION_LABEL: XLSLIBERATOR_REVISION,
            }
        },
    }
    with patch("agent.integrations.docker._inspect_one", return_value=image):
        assert docker._validated_image(_settings()) == IMAGE_ID


def test_validated_image_rejects_wrong_libreoffice_build() -> None:
    image = {
        "Id": IMAGE_ID,
        "Config": {
            "Labels": {
                docker._OFFICE_LABEL: "25.2.7.2",
                docker._VERSION_LABEL: "2026.07.0",
                docker._OPEN_SWE_REVISION_LABEL: OPEN_SWE_REVISION,
                docker._XLSLIBERATOR_REVISION_LABEL: XLSLIBERATOR_REVISION,
            }
        },
    }
    with (
        patch("agent.integrations.docker._inspect_one", return_value=image),
        pytest.raises(SandboxClientError, match="26.2.4.2"),
    ):
        docker._validated_image(_settings())


def test_validate_container_enforces_security_policy() -> None:
    with patch(
        "agent.integrations.docker._inspect_one",
        return_value=_container_payload(),
    ):
        assert (
            docker._validate_container(
                f"xlsliberator-swe-{'a' * 24}",
                expected_image_id=IMAGE_ID,
                settings=_settings(),
            )
            == IMAGE_ID
        )


def test_validate_container_rejects_network_access() -> None:
    payload = _container_payload()
    host_config = payload["HostConfig"]
    assert isinstance(host_config, dict)
    host_config["NetworkMode"] = "bridge"
    with (
        patch("agent.integrations.docker._inspect_one", return_value=payload),
        pytest.raises(SandboxClientError, match="security policy"),
    ):
        docker._validate_container(
            f"xlsliberator-swe-{'a' * 24}",
            expected_image_id=IMAGE_ID,
            settings=_settings(),
        )


def test_execute_passes_untrusted_command_as_docker_argv() -> None:
    command = "printf '%s' '$HOME;$(touch /escaped)'"
    completed = _completed(stdout=b"__OPEN_SWE_DOCKER_EXEC__ 0 0\nliteral")
    backend = docker.DockerSandbox(
        f"xlsliberator-swe-{'a' * 24}",
        settings=_settings(),
        image_id=IMAGE_ID,
    )
    with patch("agent.integrations.docker._run_docker", return_value=completed) as run:
        response = backend.execute(command, timeout=15)

    assert response.output == "literal"
    assert response.exit_code == 0
    assert response.truncated is False
    arguments = run.call_args.args[0]
    assert arguments[-1] == command
    assert arguments[-2] == "15s"
    assert run.call_args.kwargs["timeout"] == 30


def test_execute_preserves_truncation_and_exit_code() -> None:
    backend = docker.DockerSandbox(
        f"xlsliberator-swe-{'a' * 24}",
        settings=_settings(),
        image_id=IMAGE_ID,
    )
    with patch(
        "agent.integrations.docker._run_docker",
        return_value=_completed(stdout=b"__OPEN_SWE_DOCKER_EXEC__ 124 1\npreview"),
    ):
        response = backend.execute("long-command")

    assert response.output == "preview"
    assert response.exit_code == 124
    assert response.truncated is True


def test_execute_rejects_invalid_envelope() -> None:
    backend = docker.DockerSandbox(
        f"xlsliberator-swe-{'a' * 24}",
        settings=_settings(),
        image_id=IMAGE_ID,
    )
    with (
        patch(
            "agent.integrations.docker._run_docker",
            return_value=_completed(stdout=b"untrusted output"),
        ),
        pytest.raises(SandboxClientError, match="invalid envelope"),
    ):
        backend.execute("echo unsafe")


def test_upload_files_returns_partial_results() -> None:
    backend = docker.DockerSandbox(
        f"xlsliberator-swe-{'a' * 24}",
        settings=_settings(),
        image_id=IMAGE_ID,
    )
    with patch(
        "agent.integrations.docker._run_docker",
        side_effect=[_completed(), _completed(64), _completed(73)],
    ) as run:
        responses = backend.upload_files(
            [
                ("/workspace/ok.bin", b"\x00\xff"),
                ("/etc/no", b"x"),
                ("/workspace/denied", b"x"),
            ]
        )

    assert [response.error for response in responses] == [
        None,
        "invalid_path",
        "permission_denied",
    ]
    assert run.call_args_list[0].kwargs["input_bytes"] == b"\x00\xff"


def test_download_files_returns_binary_and_normalized_errors() -> None:
    backend = docker.DockerSandbox(
        f"xlsliberator-swe-{'a' * 24}",
        settings=_settings(),
        image_id=IMAGE_ID,
    )
    with patch(
        "agent.integrations.docker._run_docker",
        side_effect=[
            _completed(stdout=b"\x00\xff"),
            _completed(65),
            _completed(66),
            _completed(64),
        ],
    ):
        responses = backend.download_files(
            [
                "/workspace/ok.bin",
                "/workspace/folder",
                "/workspace/missing",
                "/etc/passwd",
            ]
        )

    assert responses[0].content == b"\x00\xff"
    assert [response.error for response in responses] == [
        None,
        "is_directory",
        "file_not_found",
        "invalid_path",
    ]


def test_create_docker_sandbox_creates_and_validates_container() -> None:
    name = f"xlsliberator-swe-{'a' * 24}"
    with (
        patch("agent.integrations.docker._validated_image", return_value=IMAGE_ID),
        patch("agent.integrations.docker._create_container", return_value=name) as create,
        patch("agent.integrations.docker._validate_container") as validate,
    ):
        backend = docker.create_docker_sandbox()

    assert backend.id == name
    create.assert_called_once_with(_settings(), IMAGE_ID)
    validate.assert_called_once_with(
        name,
        expected_image_id=IMAGE_ID,
        settings=_settings(),
    )


def test_create_docker_sandbox_reconnects_without_new_container() -> None:
    name = f"xlsliberator-swe-{'a' * 24}"
    with (
        patch("agent.integrations.docker._validated_image", return_value=IMAGE_ID),
        patch("agent.integrations.docker._create_container") as create,
        patch("agent.integrations.docker._validate_container") as validate,
    ):
        backend = docker.create_docker_sandbox(name)

    assert backend.id == name
    create.assert_not_called()
    validate.assert_called_once()
