"""Typed environment settings for XLSLiberator migration workflows."""

from __future__ import annotations

import os
from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass

DEFAULT_REPO_OWNER = "johannhartmann"
DEFAULT_REPO_NAME = "xlsliberator"
DEFAULT_CHECKOUT_PATH = "/workspace/xlsliberator"
DEFAULT_ARTIFACT_ROOT = "/workspace/artifacts/workbooks"
DEFAULT_PRIMARY_MODEL = "openai:gpt-5.5"
DEFAULT_REVIEWER_MODEL = "openai:gpt-5.6-sol"
DEFAULT_SPECIALIST_MODEL = "openai:gpt-5.5"


def _value(env: Mapping[str, str], name: str, default: str) -> str:
    value = env.get(name, default).strip()
    if not value:
        raise ValueError(f"{name} must not be empty")
    return value


def _optional_value(env: Mapping[str, str], name: str) -> str | None:
    value = env.get(name, "").strip()
    return value or None


@dataclass(frozen=True, slots=True)
class XLSLiberatorSettings:
    """Configuration owned by the XLSLiberator customization namespace."""

    checkout_path: str
    artifact_root: str
    libreoffice_mcp_endpoint: str | None
    corpus_mcp_endpoint: str | None
    build_farm_mcp_endpoint: str | None
    primary_model: str
    reviewer_model: str
    specialist_model: str

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> XLSLiberatorSettings:
        source = os.environ if env is None else env
        return cls(
            checkout_path=_value(
                source,
                "XLSLIBERATOR_CHECKOUT_PATH",
                DEFAULT_CHECKOUT_PATH,
            ),
            artifact_root=_value(
                source,
                "XLSLIBERATOR_ARTIFACT_ROOT",
                DEFAULT_ARTIFACT_ROOT,
            ),
            libreoffice_mcp_endpoint=_optional_value(
                source,
                "XLSLIBERATOR_LIBREOFFICE_MCP_ENDPOINT",
            ),
            corpus_mcp_endpoint=_optional_value(
                source,
                "XLSLIBERATOR_CORPUS_MCP_ENDPOINT",
            ),
            build_farm_mcp_endpoint=_optional_value(
                source,
                "XLSLIBERATOR_BUILD_FARM_MCP_ENDPOINT",
            ),
            primary_model=_value(
                source,
                "XLSLIBERATOR_PRIMARY_MODEL",
                DEFAULT_PRIMARY_MODEL,
            ),
            reviewer_model=_value(
                source,
                "XLSLIBERATOR_REVIEWER_MODEL",
                DEFAULT_REVIEWER_MODEL,
            ),
            specialist_model=_value(
                source,
                "XLSLIBERATOR_SPECIALIST_MODEL",
                DEFAULT_SPECIALIST_MODEL,
            ),
        )


def apply_environment_defaults(env: MutableMapping[str, str] | None = None) -> None:
    """Apply fork defaults without replacing deployment-specific configuration."""

    target = os.environ if env is None else env
    target.setdefault("DEFAULT_REPO_OWNER", DEFAULT_REPO_OWNER)
    target.setdefault("DEFAULT_REPO_NAME", DEFAULT_REPO_NAME)
