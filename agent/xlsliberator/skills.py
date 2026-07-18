"""Trusted, progressively disclosed skills for workbook-migration runs."""

from __future__ import annotations

import logging
import posixpath
import re
import shlex
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

import yaml
from deepagents.backends.protocol import (
    BackendProtocol,
    FileDownloadResponse,
    LsResult,
    SandboxBackendProtocol,
)
from deepagents.middleware.skills import (
    SkillMetadata,
    SkillsMiddleware,
    SkillSource,
    SkillsState,
    SkillsStateUpdate,
)
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime

from .settings import DEFAULT_SKILLS_ROOT, XLSLiberatorSettings

logger = logging.getLogger(__name__)

BUILTIN_SKILLS_ROOT = f"{DEFAULT_SKILLS_ROOT}/builtin"
PROJECT_SKILLS_ROOT = f"{DEFAULT_SKILLS_ROOT}/project"
SPECIALIST_SKILLS_ROOT = f"{DEFAULT_SKILLS_ROOT}/specialists"
BUILTIN_SKILLS_PACKAGE = Path(__file__).resolve().parent.parent / "skills" / "xlsliberator"
SPECIALIST_SKILL_NAMES: dict[str, tuple[str, ...]] = {
    "workbook-forensics": ("workbook-forensics", "secure-workbook-execution"),
    "formula-engineer": ("formula-migration", "migration-test-design"),
    "vba-liberation-engineer": ("vba-to-python-uno", "migration-test-design"),
    "ui-migration-engineer": (
        "userform-to-uno",
        "activex-to-open-controls",
        "visual-validation",
    ),
    "dependency-liberation-engineer": (
        "windows-dependency-replacement",
        "open-service-adapter",
    ),
    "libreoffice-engineer": ("libreoffice-debugging", "libreoffice-core-patching"),
    "test-adversary": ("migration-test-design", "migration-mutation-testing"),
    "failure-minimizer": ("workbook-failure-minimization", "ods-package-surgery"),
}

MAX_SKILL_FILE_BYTES = 128 * 1024
MAX_BUNDLED_FILE_BYTES = 1024 * 1024
MAX_BUNDLED_SOURCE_BYTES = 4 * 1024 * 1024
MAX_SKILL_DESCRIPTION_LENGTH = 1024
MAX_COMPATIBILITY_LENGTH = 500
MATERIALIZATION_TIMEOUT_SECONDS = 240

_SKILL_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_TOOL_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,127}$")
_SPECIALIST_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class SkillValidationError(ValueError):
    """A trusted skill source violates the XLSLiberator skill contract."""


def migration_skill_sources(settings: XLSLiberatorSettings) -> list[SkillSource]:
    """Return main-agent sources in exact low-to-high precedence order."""

    sources: list[SkillSource] = [
        (f"{BUILTIN_SKILLS_ROOT}/", "Built-in XLSLiberator"),
        (f"{PROJECT_SKILLS_ROOT}/", "XLSLiberator project"),
    ]
    sources.extend((path, "XLSLiberator team") for path in settings.team_skill_sources)
    sources.extend((path, "XLSLiberator user") for path in settings.user_skill_sources)
    return sources


def specialist_skill_source(specialist_name: str) -> SkillSource:
    """Return one isolated source for a specialist without global inheritance."""

    if not _SPECIALIST_NAME.fullmatch(specialist_name):
        raise ValueError("specialist name must use lowercase-hyphen form")
    return (
        f"{SPECIALIST_SKILLS_ROOT}/{specialist_name}/",
        f"{specialist_name} specialist",
    )


def _frontmatter(content: str, skill_path: str) -> dict[str, Any]:
    if not content.startswith("---\n"):
        raise SkillValidationError(f"{skill_path}: missing YAML frontmatter")
    marker = content.find("\n---\n", 4)
    if marker < 0:
        raise SkillValidationError(f"{skill_path}: unterminated YAML frontmatter")
    try:
        parsed = yaml.safe_load(content[4:marker])
    except yaml.YAMLError as exc:
        raise SkillValidationError(f"{skill_path}: invalid YAML frontmatter") from exc
    if not isinstance(parsed, dict):
        raise SkillValidationError(f"{skill_path}: frontmatter must be a mapping")
    return cast(dict[str, Any], parsed)


def _required_string(metadata: dict[str, Any], key: str, skill_path: str) -> str:
    value = metadata.get(key)
    if not isinstance(value, str) or not value.strip():
        raise SkillValidationError(f"{skill_path}: {key} must be a non-empty string")
    return value.strip()


def _declared_tools(metadata: dict[str, Any], skill_path: str) -> list[str]:
    raw_tools = metadata.get("allowed-tools", metadata.get("recommended-tools"))
    if isinstance(raw_tools, str):
        tools = [tool for tool in re.split(r"[\s,]+", raw_tools) if tool]
    elif isinstance(raw_tools, list) and all(isinstance(tool, str) for tool in raw_tools):
        tools = [tool.strip() for tool in raw_tools if tool.strip()]
    else:
        raise SkillValidationError(
            f"{skill_path}: allowed-tools or recommended-tools must declare tools"
        )
    if not tools or any(not _TOOL_NAME.fullmatch(tool) for tool in tools):
        raise SkillValidationError(f"{skill_path}: tool declarations contain invalid names")
    return tools


def parse_skill_metadata(
    content: bytes,
    *,
    skill_path: str,
    directory_name: str,
) -> SkillMetadata:
    """Strictly parse one metadata header without placing the body in a prompt."""

    if len(content) > MAX_SKILL_FILE_BYTES:
        raise SkillValidationError(f"{skill_path}: SKILL.md exceeds {MAX_SKILL_FILE_BYTES} bytes")
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SkillValidationError(f"{skill_path}: SKILL.md must be UTF-8") from exc
    metadata = _frontmatter(text, skill_path)

    name = _required_string(metadata, "name", skill_path)
    if not _SKILL_NAME.fullmatch(name) or name != directory_name:
        raise SkillValidationError(f"{skill_path}: name must match its lowercase-hyphen directory")

    description = _required_string(metadata, "description", skill_path)
    if (
        len(description) > MAX_SKILL_DESCRIPTION_LENGTH
        or len(description.split()) < 6  # noqa: PLR2004
        or not re.search(r"\b(?:use|when)\b", description, flags=re.IGNORECASE)
    ):
        raise SkillValidationError(
            f"{skill_path}: description must explain what the skill does and when to use it"
        )

    compatibility = _required_string(metadata, "compatibility", skill_path)
    if len(compatibility) > MAX_COMPATIBILITY_LENGTH:
        raise SkillValidationError(
            f"{skill_path}: compatibility exceeds {MAX_COMPATIBILITY_LENGTH} characters"
        )

    license_value = metadata.get("license")
    if license_value is not None and not isinstance(license_value, str):
        raise SkillValidationError(f"{skill_path}: license must be a string")
    arbitrary_metadata = metadata.get("metadata", {})
    if not isinstance(arbitrary_metadata, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in arbitrary_metadata.items()
    ):
        raise SkillValidationError(f"{skill_path}: metadata values must be strings")

    return SkillMetadata(
        path=skill_path,
        name=name,
        description=description,
        license=license_value,
        compatibility=compatibility,
        metadata=cast(dict[str, str], arbitrary_metadata),
        allowed_tools=_declared_tools(metadata, skill_path),
    )


async def load_validated_skills(
    backend: BackendProtocol,
    sources: Sequence[SkillSource],
) -> list[SkillMetadata]:
    """Load strict metadata with deterministic last-source-wins precedence."""

    skills: dict[str, SkillMetadata] = {}
    for source in sources:
        source_path = source if isinstance(source, str) else source[0]
        listing = await backend.als(source_path)
        if not isinstance(listing, LsResult) or listing.error:
            detail = listing.error if isinstance(listing, LsResult) else "invalid listing"
            raise SkillValidationError(f"{source_path}: inaccessible skill source ({detail})")
        directories = sorted(
            entry["path"]
            for entry in listing.entries or []
            if entry.get("is_dir") and isinstance(entry.get("path"), str)
        )
        skill_paths = [posixpath.join(directory, "SKILL.md") for directory in directories]
        if not skill_paths:
            continue
        responses = await backend.adownload_files(skill_paths)
        if len(responses) != len(skill_paths):
            raise SkillValidationError(f"{source_path}: incomplete skill metadata response")
        for directory, skill_path, response in zip(
            directories, skill_paths, responses, strict=True
        ):
            if not isinstance(response, FileDownloadResponse) or response.error:
                detail = response.error if isinstance(response, FileDownloadResponse) else "error"
                raise SkillValidationError(f"{skill_path}: inaccessible ({detail})")
            if response.content is None:
                raise SkillValidationError(f"{skill_path}: empty download response")
            skill = parse_skill_metadata(
                response.content,
                skill_path=skill_path,
                directory_name=posixpath.basename(directory.rstrip("/")),
            )
            skills[skill["name"]] = skill
    return list(skills.values())


def lint_skill_root(root: Path) -> list[str]:
    """Return deterministic validation errors for a repository skill root."""

    if not root.is_dir():
        return [f"{root}: skill root is inaccessible"]
    errors: list[str] = []
    for skill_path in sorted(root.glob("*/SKILL.md")):
        try:
            if skill_path.is_symlink() or skill_path.parent.is_symlink():
                raise SkillValidationError(f"{skill_path}: symbolic links are forbidden")
            parse_skill_metadata(
                skill_path.read_bytes(),
                skill_path=str(skill_path),
                directory_name=skill_path.parent.name,
            )
        except (OSError, SkillValidationError) as exc:
            errors.append(str(exc))
    return errors


async def _materialize_builtin_skills(backend: SandboxBackendProtocol) -> None:
    files: list[tuple[str, bytes]] = []
    total_bytes = 0
    for path in sorted(BUILTIN_SKILLS_PACKAGE.rglob("*")):
        if path.is_symlink():
            raise SkillValidationError(f"{path}: symbolic links are forbidden")
        if not path.is_file():
            continue
        content = path.read_bytes()
        if len(content) > MAX_BUNDLED_FILE_BYTES:
            raise SkillValidationError(f"{path}: bundled skill file is oversized")
        total_bytes += len(content)
        relative_path = path.relative_to(BUILTIN_SKILLS_PACKAGE).as_posix()
        files.append((f"{BUILTIN_SKILLS_ROOT}/{relative_path}", content))
    if total_bytes > MAX_BUNDLED_SOURCE_BYTES:
        raise SkillValidationError("built-in skill source exceeds its total size limit")
    result = await backend.aexecute(
        f"rm -rf {shlex.quote(BUILTIN_SKILLS_ROOT)} && mkdir -p {shlex.quote(BUILTIN_SKILLS_ROOT)}"
    )
    if result.exit_code not in (0, None):
        raise RuntimeError("failed to prepare the built-in skill destination")
    responses = await backend.aupload_files(files)
    failures = [response for response in responses if response.error]
    if failures:
        raise RuntimeError(f"failed to upload {len(failures)} built-in skill file(s)")


async def _materialize_project_skills(
    backend: SandboxBackendProtocol,
    settings: XLSLiberatorSettings,
) -> str:
    repository = f"{settings.skills_repo_owner}/{settings.skills_repo_name}"
    repository_url = f"https://github.com/{repository}.git"
    repository_dir = f"{DEFAULT_SKILLS_ROOT}/project-repository"
    quoted_repository_dir = shlex.quote(repository_dir)
    quoted_destination = shlex.quote(PROJECT_SKILLS_ROOT)
    quoted_url = shlex.quote(repository_url)
    quoted_ref = shlex.quote(settings.skills_repo_ref)
    command = "\n".join(
        [
            "set -eu",
            f"rm -rf {quoted_repository_dir} {quoted_destination}",
            f"mkdir -p {quoted_repository_dir} {quoted_destination}",
            f"git -C {quoted_repository_dir} init --quiet",
            f"git -C {quoted_repository_dir} remote add origin {quoted_url}",
            f"git -C {quoted_repository_dir} fetch --quiet --depth=1 origin -- {quoted_ref}",
            f"git -C {quoted_repository_dir} archive FETCH_HEAD skills/ "
            f"| tar -x --strip-components=1 -C {quoted_destination}",
            f"if find {quoted_destination} -type l -print -quit | grep -q .; then exit 43; fi",
            f"if find {quoted_destination} -type f -size +1M -print -quit | grep -q .; "
            "then exit 44; fi",
            f'test "$(du -sk {quoted_destination} | cut -f1)" -le 4096',
            f'printf "trusted_skills_sha=%s\\n" '
            f'"$(git -C {quoted_repository_dir} rev-parse FETCH_HEAD)"',
        ]
    )
    result = await backend.aexecute(command, timeout=MATERIALIZATION_TIMEOUT_SECONDS)
    if result.exit_code not in (0, None):
        raise RuntimeError(f"trusted skill materialization failed for {repository}")
    identity = next(
        (
            line.removeprefix("trusted_skills_sha=")
            for line in result.output.splitlines()
            if line.startswith("trusted_skills_sha=")
        ),
        "",
    )
    if not re.fullmatch(r"[0-9a-f]{40,64}", identity):
        raise RuntimeError("trusted skill materialization returned no commit identity")
    return identity


async def _materialize_specialist_skills(backend: SandboxBackendProtocol) -> None:
    quoted_root = shlex.quote(SPECIALIST_SKILLS_ROOT)
    commands = ["set -eu", f"rm -rf {quoted_root}", f"mkdir -p {quoted_root}"]
    for specialist_name, skill_names in SPECIALIST_SKILL_NAMES.items():
        destination = f"{SPECIALIST_SKILLS_ROOT}/{specialist_name}"
        commands.append(f"mkdir -p {shlex.quote(destination)}")
        for skill_name in skill_names:
            source = f"{PROJECT_SKILLS_ROOT}/{skill_name}"
            commands.append(
                f"test -f {shlex.quote(f'{source}/SKILL.md')} && "
                f"cp -R {shlex.quote(source)} {shlex.quote(destination)}/"
            )
    commands.append(f'if find {quoted_root} -type l -print -quit | grep -q .; then exit 45; fi')
    result = await backend.aexecute(
        "\n".join(commands),
        timeout=MATERIALIZATION_TIMEOUT_SECONDS,
    )
    if result.exit_code not in (0, None):
        raise RuntimeError("failed to materialize isolated specialist skills")


class MigrationSkillsMiddleware(SkillsMiddleware):
    """Materialize trusted sources, then expose only their strict metadata."""

    def __init__(
        self,
        *,
        backend: Any,
        settings: XLSLiberatorSettings,
    ) -> None:
        self._xlsliberator_settings = settings
        super().__init__(
            backend=backend,
            sources=migration_skill_sources(settings),
        )

    async def abefore_agent(
        self,
        state: SkillsState,
        runtime: Runtime,
        config: RunnableConfig,
    ) -> SkillsStateUpdate | None:
        if "skills_metadata" in state:
            return None
        resolved_backend = self._get_backend(state, runtime, config)
        if not isinstance(resolved_backend, SandboxBackendProtocol):
            raise RuntimeError("workbook migration skills require an executable sandbox backend")
        await _materialize_builtin_skills(resolved_backend)
        identity = await _materialize_project_skills(
            resolved_backend,
            self._xlsliberator_settings,
        )
        await _materialize_specialist_skills(resolved_backend)
        skills = await load_validated_skills(
            resolved_backend,
            migration_skill_sources(self._xlsliberator_settings),
        )
        logger.info(
            "Loaded %d workbook-migration skill(s) from trusted project commit %s",
            len(skills),
            identity,
        )
        return SkillsStateUpdate(skills_metadata=skills)
