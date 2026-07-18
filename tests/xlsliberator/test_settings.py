from __future__ import annotations

import pytest

from agent.xlsliberator.settings import (
    DEFAULT_ARTIFACT_ROOT,
    DEFAULT_CHECKOUT_PATH,
    DEFAULT_PRIMARY_MODEL,
    DEFAULT_REPO_NAME,
    DEFAULT_REPO_OWNER,
    DEFAULT_REVIEWER_MODEL,
    DEFAULT_SANDBOX_COMMAND_TIMEOUT_SECONDS,
    DEFAULT_SANDBOX_CPU_COUNT,
    DEFAULT_SANDBOX_DELETE_AFTER_STOP_SECONDS,
    DEFAULT_SANDBOX_DISK_BYTES,
    DEFAULT_SANDBOX_IDLE_TTL_SECONDS,
    DEFAULT_SANDBOX_IMAGE,
    DEFAULT_SANDBOX_IMAGE_VERSION,
    DEFAULT_SANDBOX_MEMORY_BYTES,
    DEFAULT_SANDBOX_PIDS_LIMIT,
    DEFAULT_SPECIALIST_MODEL,
    XLSLiberatorSettings,
    apply_environment_defaults,
)


def test_settings_have_deterministic_fork_defaults() -> None:
    settings = XLSLiberatorSettings.from_env({})

    assert settings.checkout_path == DEFAULT_CHECKOUT_PATH
    assert settings.artifact_root == DEFAULT_ARTIFACT_ROOT
    assert settings.libreoffice_mcp_endpoint is None
    assert settings.corpus_mcp_endpoint is None
    assert settings.build_farm_mcp_endpoint is None
    assert settings.primary_model == DEFAULT_PRIMARY_MODEL
    assert settings.reviewer_model == DEFAULT_REVIEWER_MODEL
    assert settings.specialist_model == DEFAULT_SPECIALIST_MODEL
    assert settings.sandbox_image == DEFAULT_SANDBOX_IMAGE
    assert settings.sandbox_image_digest is None
    assert settings.sandbox_image_version == DEFAULT_SANDBOX_IMAGE_VERSION
    assert settings.sandbox_cpu_count == DEFAULT_SANDBOX_CPU_COUNT
    assert settings.sandbox_memory_bytes == DEFAULT_SANDBOX_MEMORY_BYTES
    assert settings.sandbox_disk_bytes == DEFAULT_SANDBOX_DISK_BYTES
    assert settings.sandbox_pids_limit == DEFAULT_SANDBOX_PIDS_LIMIT
    assert settings.sandbox_command_timeout_seconds == DEFAULT_SANDBOX_COMMAND_TIMEOUT_SECONDS
    assert settings.sandbox_idle_ttl_seconds == DEFAULT_SANDBOX_IDLE_TTL_SECONDS
    assert settings.sandbox_delete_after_stop_seconds == DEFAULT_SANDBOX_DELETE_AFTER_STOP_SECONDS


def test_settings_accept_deployment_overrides() -> None:
    settings = XLSLiberatorSettings.from_env(
        {
            "XLSLIBERATOR_CHECKOUT_PATH": "/job/source",
            "XLSLIBERATOR_ARTIFACT_ROOT": "s3://migration-artifacts/workbooks",
            "XLSLIBERATOR_LIBREOFFICE_MCP_ENDPOINT": "http://office:8000/mcp",
            "XLSLIBERATOR_CORPUS_MCP_ENDPOINT": "http://corpus:8000/mcp",
            "XLSLIBERATOR_BUILD_FARM_MCP_ENDPOINT": "http://build-farm:8000/mcp",
            "XLSLIBERATOR_PRIMARY_MODEL": "primary:model",
            "XLSLIBERATOR_REVIEWER_MODEL": "reviewer:model",
            "XLSLIBERATOR_SPECIALIST_MODEL": "specialist:model",
            "XLSLIBERATOR_SANDBOX_IMAGE": "registry.example/sandbox:v1",
            "XLSLIBERATOR_SANDBOX_IMAGE_DIGEST": "sha256:abc",
            "XLSLIBERATOR_SANDBOX_IMAGE_VERSION": "v1",
            "XLSLIBERATOR_SANDBOX_CPU_COUNT": "8",
            "XLSLIBERATOR_SANDBOX_MEMORY_BYTES": "1000",
            "XLSLIBERATOR_SANDBOX_DISK_BYTES": "2000",
            "XLSLIBERATOR_SANDBOX_PIDS_LIMIT": "3000",
            "XLSLIBERATOR_SANDBOX_COMMAND_TIMEOUT_SECONDS": "4000",
            "XLSLIBERATOR_SANDBOX_IDLE_TTL_SECONDS": "5000",
            "XLSLIBERATOR_SANDBOX_DELETE_AFTER_STOP_SECONDS": "6000",
        }
    )

    assert settings.checkout_path == "/job/source"
    assert settings.artifact_root == "s3://migration-artifacts/workbooks"
    assert settings.libreoffice_mcp_endpoint == "http://office:8000/mcp"
    assert settings.corpus_mcp_endpoint == "http://corpus:8000/mcp"
    assert settings.build_farm_mcp_endpoint == "http://build-farm:8000/mcp"
    assert settings.primary_model == "primary:model"
    assert settings.reviewer_model == "reviewer:model"
    assert settings.specialist_model == "specialist:model"
    assert settings.sandbox_image == "registry.example/sandbox:v1"
    assert settings.sandbox_image_digest == "sha256:abc"
    assert settings.sandbox_image_version == "v1"
    assert settings.sandbox_cpu_count == 8
    assert settings.sandbox_memory_bytes == 1000
    assert settings.sandbox_disk_bytes == 2000
    assert settings.sandbox_pids_limit == 3000
    assert settings.sandbox_command_timeout_seconds == 4000
    assert settings.sandbox_idle_ttl_seconds == 5000
    assert settings.sandbox_delete_after_stop_seconds == 6000


def test_environment_defaults_do_not_replace_explicit_values() -> None:
    env = {
        "DEFAULT_REPO_OWNER": "other-owner",
        "DEFAULT_REPO_NAME": "other-repository",
    }

    apply_environment_defaults(env)

    assert env == {
        "DEFAULT_REPO_OWNER": "other-owner",
        "DEFAULT_REPO_NAME": "other-repository",
        "DEFAULT_SANDBOX_SNAPSHOT_FS_CAPACITY_BYTES": str(DEFAULT_SANDBOX_DISK_BYTES),
        "DEFAULT_SANDBOX_VCPUS": str(DEFAULT_SANDBOX_CPU_COUNT),
        "DEFAULT_SANDBOX_MEM_BYTES": str(DEFAULT_SANDBOX_MEMORY_BYTES),
        "DEFAULT_SANDBOX_IDLE_TTL_SECONDS": str(DEFAULT_SANDBOX_IDLE_TTL_SECONDS),
        "DEFAULT_SANDBOX_DELETE_AFTER_STOP_SECONDS": str(DEFAULT_SANDBOX_DELETE_AFTER_STOP_SECONDS),
    }


def test_environment_defaults_select_xlsliberator_repository() -> None:
    env: dict[str, str] = {}

    apply_environment_defaults(env)

    assert env == {
        "DEFAULT_REPO_OWNER": DEFAULT_REPO_OWNER,
        "DEFAULT_REPO_NAME": DEFAULT_REPO_NAME,
        "DEFAULT_SANDBOX_SNAPSHOT_FS_CAPACITY_BYTES": str(DEFAULT_SANDBOX_DISK_BYTES),
        "DEFAULT_SANDBOX_VCPUS": str(DEFAULT_SANDBOX_CPU_COUNT),
        "DEFAULT_SANDBOX_MEM_BYTES": str(DEFAULT_SANDBOX_MEMORY_BYTES),
        "DEFAULT_SANDBOX_IDLE_TTL_SECONDS": str(DEFAULT_SANDBOX_IDLE_TTL_SECONDS),
        "DEFAULT_SANDBOX_DELETE_AFTER_STOP_SECONDS": str(DEFAULT_SANDBOX_DELETE_AFTER_STOP_SECONDS),
    }


def test_required_setting_rejects_explicit_empty_value() -> None:
    with pytest.raises(ValueError, match="XLSLIBERATOR_PRIMARY_MODEL must not be empty"):
        XLSLiberatorSettings.from_env({"XLSLIBERATOR_PRIMARY_MODEL": " "})


@pytest.mark.parametrize(
    "value, message",
    [
        ("0", "must be positive"),
        ("-1", "must be positive"),
        ("invalid", "must be an integer"),
    ],
)
def test_resource_setting_rejects_invalid_values(value: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        XLSLiberatorSettings.from_env({"XLSLIBERATOR_SANDBOX_CPU_COUNT": value})
