from __future__ import annotations

from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from deepagents.backends.protocol import (
    BackendProtocol,
    ExecuteResponse,
    FileDownloadResponse,
    LsResult,
    SandboxBackendProtocol,
)

from agent.xlsliberator.settings import XLSLiberatorSettings
from agent.xlsliberator.skills import (
    BUILTIN_SKILLS_ROOT,
    EMBEDDED_PROJECT_SKILLS_ROOT,
    MAX_SKILL_FILE_BYTES,
    PROJECT_SKILLS_ROOT,
    SANDBOX_IDENTITY_PATH,
    SkillValidationError,
    _materialize_project_skills,
    lint_skill_root,
    load_validated_skills,
    migration_skill_sources,
    parse_skill_metadata,
    specialist_skill_source,
)


def _skill(name: str, description: str = "") -> bytes:
    useful_description = description or (
        "Use this skill when deterministic workbook migration checks need reusable guidance."
    )
    return (
        "---\n"
        f"name: {name}\n"
        f"description: {useful_description}\n"
        "compatibility: Docker-only XLSLiberator migration sandbox.\n"
        "allowed-tools: read_file execute\n"
        "---\n\n"
        "# Instructions\n"
    ).encode()


class FakeBackend(BackendProtocol):
    def __init__(
        self,
        sources: dict[str, list[str]],
        files: dict[str, bytes],
        *,
        inaccessible: set[str] | None = None,
    ) -> None:
        self.sources = sources
        self.files = files
        self.inaccessible = inaccessible or set()

    async def als(self, path: str) -> LsResult:
        if path in self.inaccessible:
            return LsResult(error="permission_denied")
        return LsResult(
            entries=[
                {"path": directory, "is_dir": True, "size": 0, "modified_at": ""}
                for directory in self.sources.get(path, [])
            ]
        )

    async def adownload_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        return [
            FileDownloadResponse(
                path=path,
                content=self.files.get(path),
                error=None if path in self.files else "file_not_found",
            )
            for path in paths
        ]


def test_parse_skill_metadata_accepts_strict_contract() -> None:
    metadata = parse_skill_metadata(
        _skill("formula-migration"),
        skill_path="/skills/formula-migration/SKILL.md",
        directory_name="formula-migration",
    )

    assert metadata["name"] == "formula-migration"
    assert metadata["compatibility"] == "Docker-only XLSLiberator migration sandbox."
    assert metadata["allowed_tools"] == ["read_file", "execute"]


@pytest.mark.parametrize(
    ("content", "directory", "message"),
    [
        (_skill("wrong-name"), "formula-migration", "name must match"),
        (b"# no frontmatter\n", "formula-migration", "missing YAML frontmatter"),
        (
            _skill("formula-migration", "Too short"),
            "formula-migration",
            "description must explain",
        ),
    ],
)
def test_parse_skill_metadata_rejects_invalid_contract(
    content: bytes,
    directory: str,
    message: str,
) -> None:
    with pytest.raises(SkillValidationError, match=message):
        parse_skill_metadata(
            content,
            skill_path=f"/skills/{directory}/SKILL.md",
            directory_name=directory,
        )


def test_parse_skill_metadata_rejects_oversized_file() -> None:
    content = _skill("formula-migration") + b"x" * MAX_SKILL_FILE_BYTES

    with pytest.raises(SkillValidationError, match="exceeds"):
        parse_skill_metadata(
            content,
            skill_path="/skills/formula-migration/SKILL.md",
            directory_name="formula-migration",
        )


async def test_load_validated_skills_uses_last_source_precedence() -> None:
    built_in = "/skills/builtin/"
    project = "/skills/project/"
    built_in_dir = "/skills/builtin/formula-migration"
    project_dir = "/skills/project/formula-migration"
    backend = FakeBackend(
        {built_in: [built_in_dir], project: [project_dir]},
        {
            f"{built_in_dir}/SKILL.md": _skill(
                "formula-migration",
                "Use this skill when built-in formula migration guidance is needed.",
            ),
            f"{project_dir}/SKILL.md": _skill(
                "formula-migration",
                "Use this skill when project formula migration guidance is needed.",
            ),
        },
    )

    skills = await load_validated_skills(
        cast(BackendProtocol, backend),
        [(built_in, "Built-in"), (project, "Project")],
    )

    assert len(skills) == 1
    assert skills[0]["path"] == f"{project_dir}/SKILL.md"
    assert skills[0]["description"].startswith("Use this skill when project")


async def test_load_validated_skills_rejects_inaccessible_source() -> None:
    backend = FakeBackend({}, {}, inaccessible={"/skills/team/"})

    with pytest.raises(SkillValidationError, match="inaccessible skill source"):
        await load_validated_skills(
            cast(BackendProtocol, backend),
            [("/skills/team/", "Team")],
        )


def test_main_sources_are_ordered_and_specialists_are_isolated() -> None:
    settings = XLSLiberatorSettings.from_env(
        {
            "XLSLIBERATOR_TEAM_SKILL_SOURCES": ("/workspace/.xlsliberator-skills/team/primary"),
            "XLSLIBERATOR_USER_SKILL_SOURCES": ("/workspace/.xlsliberator-skills/user/johann"),
        }
    )

    sources = migration_skill_sources(settings)
    specialist = specialist_skill_source("formula-specialist")

    assert [source[0] for source in cast(list[tuple[str, str]], sources)] == [
        f"{BUILTIN_SKILLS_ROOT}/",
        f"{PROJECT_SKILLS_ROOT}/",
        "/workspace/.xlsliberator-skills/team/primary/",
        "/workspace/.xlsliberator-skills/user/johann/",
    ]
    assert specialist[0].endswith("/specialists/formula-specialist/")
    assert specialist not in sources
    assert all(source[0] not in specialist[0] for source in cast(list[tuple[str, str]], sources))


def test_lint_skill_root_reports_invalid_frontmatter(tmp_path: Path) -> None:
    skill_dir = tmp_path / "invalid-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: [invalid\n", encoding="utf-8")

    errors = lint_skill_root(tmp_path)

    assert len(errors) == 1
    assert "unterminated YAML frontmatter" in errors[0]


@pytest.mark.asyncio
async def test_project_skills_materialize_from_pinned_networkless_image() -> None:
    identity = "a" * 40
    backend = MagicMock(spec=SandboxBackendProtocol)
    backend.aexecute = AsyncMock(
        return_value=ExecuteResponse(
            output=f"trusted_skills_sha={identity}\n",
            exit_code=0,
        )
    )
    settings = XLSLiberatorSettings.from_env({"XLSLIBERATOR_SKILLS_REPO_REF": identity})

    actual = await _materialize_project_skills(
        cast(SandboxBackendProtocol, backend),
        settings,
    )

    assert actual == identity
    command = backend.aexecute.await_args.args[0]
    assert EMBEDDED_PROJECT_SKILLS_ROOT in command
    assert SANDBOX_IDENTITY_PATH in command
    assert "git fetch" not in command
    assert "https://" not in command
    assert 'test "$identity" = "$expected_ref"' in command
