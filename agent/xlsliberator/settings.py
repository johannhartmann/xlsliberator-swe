"""Typed environment settings for XLSLiberator migration workflows."""

from __future__ import annotations

import os
import posixpath
import re
from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass

DEFAULT_REPO_OWNER = "johannhartmann"
DEFAULT_REPO_NAME = "xlsliberator"
DEFAULT_CHECKOUT_PATH = "/workspace/xlsliberator"
DEFAULT_ARTIFACT_ROOT = "/workspace/artifacts/workbooks"
DEFAULT_PRIMARY_MODEL = "openai:gpt-5.5"
DEFAULT_REVIEWER_MODEL = "openai:gpt-5.6-sol"
DEFAULT_SPECIALIST_MODEL = "openai:gpt-5.5"
DEFAULT_SANDBOX_IMAGE = "ghcr.io/johannhartmann/xlsliberator-swe-sandbox:2026.07.0"
DEFAULT_SANDBOX_IMAGE_VERSION = "2026.07.0"
DEFAULT_SANDBOX_CPU_COUNT = 2
DEFAULT_SANDBOX_MEMORY_BYTES = 7_936 * 1024**2
DEFAULT_SANDBOX_DISK_BYTES = 32 * 1024**3
DEFAULT_SANDBOX_PIDS_LIMIT = 1024
DEFAULT_SANDBOX_COMMAND_TIMEOUT_SECONDS = 30 * 60
DEFAULT_SANDBOX_IDLE_TTL_SECONDS = 2 * 60 * 60
DEFAULT_SANDBOX_DELETE_AFTER_STOP_SECONDS = 24 * 60 * 60
DEFAULT_SKILLS_REPO_OWNER = DEFAULT_REPO_OWNER
DEFAULT_SKILLS_REPO_NAME = DEFAULT_REPO_NAME
DEFAULT_SKILLS_REPO_REF = "main"
DEFAULT_SKILLS_ROOT = "/workspace/.xlsliberator-skills"
DEFAULT_SHOWCASE_MODE = False

_REPOSITORY_COMPONENT = re.compile(r"^[A-Za-z0-9_.-]+$")
_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off"})


def _value(env: Mapping[str, str], name: str, default: str) -> str:
    value = env.get(name, default).strip()
    if not value:
        raise ValueError(f"{name} must not be empty")
    return value


def _optional_value(env: Mapping[str, str], name: str) -> str | None:
    value = env.get(name, "").strip()
    return value or None


def _positive_int(env: Mapping[str, str], name: str, default: int) -> int:
    raw_value = env.get(name)
    if raw_value is None:
        return default
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def _boolean(env: Mapping[str, str], name: str, default: bool) -> bool:
    raw_value = env.get(name)
    if raw_value is None:
        return default
    normalized = raw_value.strip().lower()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    raise ValueError(f"{name} must be a boolean")


def _repository_component(env: Mapping[str, str], name: str, default: str) -> str:
    value = _value(env, name, default)
    if not _REPOSITORY_COMPONENT.fullmatch(value) or value in {".", ".."}:
        raise ValueError(f"{name} contains unsupported characters")
    return value


def _trusted_skill_paths(env: Mapping[str, str], name: str) -> tuple[str, ...]:
    raw_value = env.get(name, "")
    if not raw_value.strip():
        return ()
    paths: list[str] = []
    for raw_path in raw_value.split(","):
        path = posixpath.normpath(raw_path.strip())
        if path == DEFAULT_SKILLS_ROOT or not path.startswith(f"{DEFAULT_SKILLS_ROOT}/"):
            raise ValueError(f"{name} paths must be below {DEFAULT_SKILLS_ROOT}")
        paths.append(f"{path}/")
    return tuple(paths)


@dataclass(frozen=True, slots=True)
class XLSLiberatorSettings:
    """Configuration owned by the XLSLiberator customization namespace."""

    checkout_path: str
    artifact_root: str
    libreoffice_mcp_endpoint: str | None
    corpus_mcp_endpoint: str | None
    build_farm_mcp_endpoint: str | None
    mcp_bridge_root: str | None
    primary_model: str
    reviewer_model: str
    specialist_model: str
    sandbox_image: str
    sandbox_image_digest: str | None
    sandbox_image_version: str
    sandbox_cpu_count: int
    sandbox_memory_bytes: int
    sandbox_disk_bytes: int
    sandbox_pids_limit: int
    sandbox_command_timeout_seconds: int
    sandbox_idle_ttl_seconds: int
    sandbox_delete_after_stop_seconds: int
    skills_repo_owner: str
    skills_repo_name: str
    skills_repo_ref: str
    team_skill_sources: tuple[str, ...]
    user_skill_sources: tuple[str, ...]
    showcase_mode: bool

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
            mcp_bridge_root=_optional_value(
                source,
                "XLSLIBERATOR_MCP_BRIDGE_ROOT",
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
            sandbox_image=_value(
                source,
                "XLSLIBERATOR_SANDBOX_IMAGE",
                DEFAULT_SANDBOX_IMAGE,
            ),
            sandbox_image_digest=_optional_value(
                source,
                "XLSLIBERATOR_SANDBOX_IMAGE_DIGEST",
            ),
            sandbox_image_version=_value(
                source,
                "XLSLIBERATOR_SANDBOX_IMAGE_VERSION",
                DEFAULT_SANDBOX_IMAGE_VERSION,
            ),
            sandbox_cpu_count=_positive_int(
                source,
                "XLSLIBERATOR_SANDBOX_CPU_COUNT",
                DEFAULT_SANDBOX_CPU_COUNT,
            ),
            sandbox_memory_bytes=_positive_int(
                source,
                "XLSLIBERATOR_SANDBOX_MEMORY_BYTES",
                DEFAULT_SANDBOX_MEMORY_BYTES,
            ),
            sandbox_disk_bytes=_positive_int(
                source,
                "XLSLIBERATOR_SANDBOX_DISK_BYTES",
                DEFAULT_SANDBOX_DISK_BYTES,
            ),
            sandbox_pids_limit=_positive_int(
                source,
                "XLSLIBERATOR_SANDBOX_PIDS_LIMIT",
                DEFAULT_SANDBOX_PIDS_LIMIT,
            ),
            sandbox_command_timeout_seconds=_positive_int(
                source,
                "XLSLIBERATOR_SANDBOX_COMMAND_TIMEOUT_SECONDS",
                DEFAULT_SANDBOX_COMMAND_TIMEOUT_SECONDS,
            ),
            sandbox_idle_ttl_seconds=_positive_int(
                source,
                "XLSLIBERATOR_SANDBOX_IDLE_TTL_SECONDS",
                DEFAULT_SANDBOX_IDLE_TTL_SECONDS,
            ),
            sandbox_delete_after_stop_seconds=_positive_int(
                source,
                "XLSLIBERATOR_SANDBOX_DELETE_AFTER_STOP_SECONDS",
                DEFAULT_SANDBOX_DELETE_AFTER_STOP_SECONDS,
            ),
            skills_repo_owner=_repository_component(
                source,
                "XLSLIBERATOR_SKILLS_REPO_OWNER",
                DEFAULT_SKILLS_REPO_OWNER,
            ),
            skills_repo_name=_repository_component(
                source,
                "XLSLIBERATOR_SKILLS_REPO_NAME",
                DEFAULT_SKILLS_REPO_NAME,
            ),
            skills_repo_ref=_value(
                source,
                "XLSLIBERATOR_SKILLS_REPO_REF",
                DEFAULT_SKILLS_REPO_REF,
            ),
            team_skill_sources=_trusted_skill_paths(
                source,
                "XLSLIBERATOR_TEAM_SKILL_SOURCES",
            ),
            user_skill_sources=_trusted_skill_paths(
                source,
                "XLSLIBERATOR_USER_SKILL_SOURCES",
            ),
            showcase_mode=_boolean(
                source,
                "XLSLIBERATOR_SHOWCASE_MODE",
                DEFAULT_SHOWCASE_MODE,
            ),
        )


def apply_environment_defaults(env: MutableMapping[str, str] | None = None) -> None:
    """Apply fork defaults without replacing deployment-specific configuration."""

    target = os.environ if env is None else env
    target.setdefault("DEFAULT_REPO_OWNER", DEFAULT_REPO_OWNER)
    target.setdefault("DEFAULT_REPO_NAME", DEFAULT_REPO_NAME)
    target.setdefault(
        "DEFAULT_SANDBOX_SNAPSHOT_FS_CAPACITY_BYTES",
        str(DEFAULT_SANDBOX_DISK_BYTES),
    )
    target.setdefault("DEFAULT_SANDBOX_VCPUS", str(DEFAULT_SANDBOX_CPU_COUNT))
    target.setdefault("DEFAULT_SANDBOX_MEM_BYTES", str(DEFAULT_SANDBOX_MEMORY_BYTES))
    target.setdefault(
        "DEFAULT_SANDBOX_IDLE_TTL_SECONDS",
        str(DEFAULT_SANDBOX_IDLE_TTL_SECONDS),
    )
    target.setdefault(
        "DEFAULT_SANDBOX_DELETE_AFTER_STOP_SECONDS",
        str(DEFAULT_SANDBOX_DELETE_AFTER_STOP_SECONDS),
    )
