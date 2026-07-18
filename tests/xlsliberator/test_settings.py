from __future__ import annotations

import pytest

from agent.xlsliberator.settings import (
    DEFAULT_ARTIFACT_ROOT,
    DEFAULT_CHECKOUT_PATH,
    DEFAULT_PRIMARY_MODEL,
    DEFAULT_REPO_NAME,
    DEFAULT_REPO_OWNER,
    DEFAULT_REVIEWER_MODEL,
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


def test_environment_defaults_do_not_replace_explicit_values() -> None:
    env = {
        "DEFAULT_REPO_OWNER": "other-owner",
        "DEFAULT_REPO_NAME": "other-repository",
    }

    apply_environment_defaults(env)

    assert env == {
        "DEFAULT_REPO_OWNER": "other-owner",
        "DEFAULT_REPO_NAME": "other-repository",
    }


def test_environment_defaults_select_xlsliberator_repository() -> None:
    env: dict[str, str] = {}

    apply_environment_defaults(env)

    assert env == {
        "DEFAULT_REPO_OWNER": DEFAULT_REPO_OWNER,
        "DEFAULT_REPO_NAME": DEFAULT_REPO_NAME,
    }


def test_required_setting_rejects_explicit_empty_value() -> None:
    with pytest.raises(ValueError, match="XLSLIBERATOR_PRIMARY_MODEL must not be empty"):
        XLSLiberatorSettings.from_env({"XLSLIBERATOR_PRIMARY_MODEL": " "})
