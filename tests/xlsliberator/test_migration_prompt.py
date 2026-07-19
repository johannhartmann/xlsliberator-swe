"""Workbook-migration lead prompt and scenario trajectory contract."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

from agent.xlsliberator.migrations import TASK_KIND
from agent.xlsliberator.prompt import (
    FEATURE_TRAJECTORY_REQUIREMENTS,
    GOLDEN_MIGRATION_PATHS,
    MIGRATION_LEAD_PROMPT,
    MIGRATION_LEAD_STAGES,
    SHOWCASE_MCP_TOOL_NAMES,
    SHOWCASE_SPECIALIST_NAMES,
    MigrationFeature,
    prompt_for_task,
    showcase_prompt,
    trajectory_for,
)


def test_ordinary_coding_prompt_is_preserved_exactly() -> None:
    base = "ordinary Open SWE prompt\nwith exact spacing\n"

    assert prompt_for_task(base, task_kind="coding") == base
    assert prompt_for_task(base, task_kind=None) == base


def test_migration_prompt_is_injected_only_for_server_task_kind() -> None:
    rendered = prompt_for_task("ordinary Open SWE prompt", task_kind=TASK_KIND)

    assert rendered.startswith("ordinary Open SWE prompt\n\n")
    assert "XLSLiberator workbook-migration lead" in rendered
    assert "XLSLIBERATOR_STATUS: DELIVERABLE" in rendered
    assert "XLSLIBERATOR_STATUS: UNRESOLVED" in rendered


def test_lead_prompt_contains_ordered_fourteen_stage_loop() -> None:
    positions = [MIGRATION_LEAD_PROMPT.index(stage) for stage in MIGRATION_LEAD_STAGES]

    assert len(MIGRATION_LEAD_STAGES) == 14
    assert positions == sorted(positions)
    assert "full source files" in MIGRATION_LEAD_PROMPT
    assert "Do not request or depend on a compiler IR" in MIGRATION_LEAD_PROMPT
    assert "originating UI or channel" in MIGRATION_LEAD_PROMPT
    assert "candidate tournament" in MIGRATION_LEAD_PROMPT
    assert "Treat outputs as private" in MIGRATION_LEAD_PROMPT
    assert "interactive-game" not in MIGRATION_LEAD_PROMPT
    assert "da1bddc2" not in MIGRATION_LEAD_PROMPT


def test_showcase_prompt_is_bounded_and_preserves_every_acceptance_gate() -> None:
    rendered = showcase_prompt("/workspace")

    assert "/workspace" in rendered
    assert len(rendered) < 6_000
    assert set(SHOWCASE_SPECIALIST_NAMES) == {
        "workbook-forensics",
        "vba-liberation-engineer",
        "ui-migration-engineer",
        "test-adversary",
    }
    assert SHOWCASE_MCP_TOOL_NAMES == {
        "xlsliberator_runtime_build_application_candidate",
        "xlsliberator_runtime_run_application_scenario",
        "xlsliberator_runtime_bundle_application_replays",
    }
    for specialist in SHOWCASE_SPECIALIST_NAMES:
        assert specialist in rendered
    for tool in SHOWCASE_MCP_TOOL_NAMES:
        assert tool in rendered
    for scenario in (
        "keyboard-control",
        "timer-tick",
        "native-controls",
        "document-events",
        "line-collapse",
    ):
        assert scenario in rendered
    for requirement in (
        "LibreOffice full build `26.2.4.2`",
        "source-derived mutations",
        "migration/generated/candidate.zip",
        "xlsliberator candidate-package",
        "does not open a workbook or execute candidate code",
        "at least two isolated",
        "does not know this workbook",
        "Do not copy a repository demo candidate",
        "same candidate digest",
        "save, close, reopen",
        "public-showcase.zip",
        "request_independent_migration_review",
        "APPROVE",
        "XLSLIBERATOR_STATUS: DELIVERABLE",
    ):
        assert requirement in rendered


@pytest.mark.parametrize(
    ("feature", "required_fragments"),
    [
        (
            "formula-only",
            ("formula-engineer", "recalculation evidence", "precedent-value mutation"),
        ),
        (
            "vba-project",
            ("complete VBA project", "direct Python/UNO", "cross-module state"),
        ),
        (
            "userform",
            ("ui-migration-engineer", "native LibreOffice UI", "visual evidence"),
        ),
        (
            "proprietary-dependency",
            ("open provider-neutral", "deterministic mock", "authorized open capability"),
        ),
        (
            "libreoffice-defect",
            ("minimized stock LibreOffice", "stock-versus-patched", "workbook repair"),
        ),
        (
            "prompt-injection",
            ("untrusted data", "blocked attempt", "trusted user and server instructions"),
        ),
        (
            "budget-exhaustion",
            ("meaningful checkpoint", "remaining acceptance gaps", "UNRESOLVED"),
        ),
    ],
)
def test_feature_trajectory_covers_required_scenario(
    feature: MigrationFeature,
    required_fragments: tuple[str, ...],
) -> None:
    trajectory = "\n".join(trajectory_for([feature]))

    assert len(trajectory_for([feature])) == 14 + len(FEATURE_TRAJECTORY_REQUIREMENTS[feature])
    for fragment in required_fragments:
        assert fragment in trajectory


def test_combined_trajectory_is_deterministic_and_deduplicated() -> None:
    first = trajectory_for(["userform", "vba-project", "userform"])
    second = trajectory_for(["vba-project", "userform"])

    assert first == second
    assert first[:14] == MIGRATION_LEAD_STAGES


def test_unknown_trajectory_feature_is_rejected() -> None:
    with pytest.raises(ValueError, match="unsupported migration features"):
        trajectory_for(cast(list[MigrationFeature], ["excel-runtime"]))


def test_golden_directory_manifest_matches_prompt_policy() -> None:
    manifest_path = (
        Path(__file__).parents[2] / "agent" / "xlsliberator" / "golden_migration" / "structure.json"
    )
    manifest = json.loads(manifest_path.read_text())

    assert manifest["schema_version"] == 1
    assert manifest["privacy"] == "private"
    assert tuple(manifest["required_paths"]) == GOLDEN_MIGRATION_PATHS
    for path in GOLDEN_MIGRATION_PATHS:
        assert f"`{path}`" in MIGRATION_LEAD_PROMPT
