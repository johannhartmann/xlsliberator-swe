from __future__ import annotations

from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest
from deepagents.backends import CompositeBackend
from deepagents.backends.protocol import SandboxBackendProtocol
from deepagents.middleware.filesystem import FilesystemMiddleware, FilesystemPermission
from langchain_core.language_models import BaseChatModel

from agent.xlsliberator.skills import SPECIALIST_SKILL_NAMES, SPECIALIST_SKILLS_ROOT
from agent.xlsliberator.subagents import (
    SPECIALIST_BY_NAME,
    SPECIALIST_PROFILES,
    XLSLIBERATOR_SUBAGENTS,
    SpecialistResult,
    SpecialistTraceMiddleware,
    build_migration_subagents,
    candidate_tournament,
    specialist_trace_metadata,
    subagents_for_task_kind,
)


def _model() -> BaseChatModel:
    return cast(BaseChatModel, object())


def _tools(*names: str) -> list[dict[str, Any]]:
    return [{"name": name} for name in names]


def _tool_names(spec: dict[str, Any]) -> list[str]:
    return [tool["name"] for tool in cast(list[dict[str, str]], spec["tools"])]


def _filesystem_middleware(spec: dict[str, Any]) -> FilesystemMiddleware:
    middleware = cast(list[object], spec["middleware"])
    return next(item for item in middleware if isinstance(item, FilesystemMiddleware))


def _filesystem_permissions(spec: dict[str, Any]) -> list[FilesystemPermission]:
    return _filesystem_middleware(spec)._permissions


def test_specialist_catalog_has_required_roles_and_isolated_skill_views() -> None:
    assert XLSLIBERATOR_SUBAGENTS == (
        "workbook-forensics",
        "formula-engineer",
        "vba-liberation-engineer",
        "ui-migration-engineer",
        "dependency-liberation-engineer",
        "libreoffice-engineer",
        "test-adversary",
        "security-adversary",
        "failure-minimizer",
    )
    assert {profile.name: profile.skill_names for profile in SPECIALIST_PROFILES} == (
        SPECIALIST_SKILL_NAMES
    )

    specs = build_migration_subagents(_model(), [])

    for spec in specs:
        declarative = cast(dict[str, Any], spec)
        assert declarative.get("skills") == [
            f"{SPECIALIST_SKILLS_ROOT}/{declarative['name']}/"
        ]
        assert "must not certify or approve" in declarative["system_prompt"]
        assert "self_certified=false" in declarative["system_prompt"]
        assert declarative.get("response_format") is SpecialistResult
        middleware = declarative.get("middleware")
        assert middleware is not None
        assert isinstance(middleware[0], SpecialistTraceMiddleware)


def test_tool_allowlists_drop_unrelated_and_hidden_tools() -> None:
    specs = build_migration_subagents(
        _model(),
        _tools(
            "xlsliberator_runtime_inspect_document",
            "xlsliberator_runtime_build_application_candidate",
            "xlsliberator_runtime_run_application_scenario",
            "xlsliberator_runtime_bundle_application_replays",
            "xlsliberator_corpus_run_public_suite",
            "xlsliberator_corpus_run_hidden_acceptance",
            "xlsliberator_buildfarm_apply_patch",
        ),
    )
    by_name = {spec["name"]: spec for spec in specs}

    assert _tool_names(cast(dict[str, Any], by_name["workbook-forensics"])) == [
        "xlsliberator_runtime_inspect_document"
    ]
    assert _tool_names(cast(dict[str, Any], by_name["test-adversary"])) == [
        "xlsliberator_runtime_run_application_scenario",
        "xlsliberator_runtime_bundle_application_replays",
        "xlsliberator_corpus_run_public_suite",
    ]
    assert _tool_names(cast(dict[str, Any], by_name["security-adversary"])) == [
        "xlsliberator_runtime_inspect_document",
        "xlsliberator_corpus_run_public_suite",
    ]
    assert "xlsliberator_corpus_run_hidden_acceptance" not in {
        name for spec in specs for name in _tool_names(cast(dict[str, Any], spec))
    }
    assert _tool_names(cast(dict[str, Any], by_name["libreoffice-engineer"])) == [
        "xlsliberator_runtime_inspect_document",
        "xlsliberator_buildfarm_apply_patch",
    ]


def test_filesystem_policy_prevents_test_adversary_from_writing_candidates() -> None:
    test_adversary = next(
        spec for spec in build_migration_subagents(_model(), []) if spec["name"] == "test-adversary"
    )
    assert "permissions" not in test_adversary
    permissions = _filesystem_permissions(cast(dict[str, Any], test_adversary))

    assert permissions[0].operations == ["read"]
    assert permissions[0].paths == ["/**"]
    assert "/workspace/migration/acceptance/**" in permissions[1].paths
    assert all("/candidates/" not in path for path in permissions[1].paths)
    assert permissions[-1].operations == ["write"]
    assert permissions[-1].mode == "deny"


def test_security_adversary_is_read_only_except_security_evidence() -> None:
    security_adversary = next(
        spec
        for spec in build_migration_subagents(_model(), [])
        if spec["name"] == "security-adversary"
    )
    assert "permissions" not in security_adversary
    permissions = _filesystem_permissions(cast(dict[str, Any], security_adversary))

    assert "/workspace/migration/evidence/security/**" in permissions[1].paths
    assert all("/candidates/" not in path for path in permissions[1].paths)
    assert all("/hidden/" not in path for path in permissions[1].paths)
    assert permissions[-1].mode == "deny"


def test_specialist_filesystem_cannot_execute_or_bypass_path_permissions() -> None:
    specs = build_migration_subagents(_model(), [])

    for spec in specs:
        filesystem = _filesystem_middleware(cast(dict[str, Any], spec))
        assert isinstance(filesystem.backend, CompositeBackend)
        assert not isinstance(filesystem.backend.default, SandboxBackendProtocol)
        assert filesystem._enabled_tools is not None
        assert "execute" not in filesystem._enabled_tools
        assert filesystem.backend.artifacts_root.startswith("/workspace/.deepagents/specialists/")


def test_domain_subagents_are_absent_for_ordinary_tasks() -> None:
    assert (
        subagents_for_task_kind(
            "coding",
            model=_model(),
            tools=[],
            migration_task_kind="workbook_migration",
        )
        == []
    )
    migration = subagents_for_task_kind(
        "workbook_migration",
        model=_model(),
        tools=[],
        migration_task_kind="workbook_migration",
    )
    assert [spec["name"] for spec in migration] == list(XLSLIBERATOR_SUBAGENTS)


def test_specialist_model_and_effort_routing_are_explicit() -> None:
    model = _model()

    specs = build_migration_subagents(model, [])

    assert all(spec.get("model") is model for spec in specs)
    assert all(SPECIALIST_BY_NAME[spec["name"]].effort == "high" for spec in specs)
    metadata = specialist_trace_metadata("formula-engineer")
    assert metadata["agent_role"] == "formula-engineer"
    assert metadata["preferred_effort"] == "high"
    assert "/workspace/migration/candidates/formula-engineer/**" in cast(
        tuple[str, ...], metadata["artifact_paths"]
    )


def test_compact_specialists_use_precompiled_minimal_agents() -> None:
    created: list[dict[str, Any]] = []

    def fake_create_agent(*args: object, **kwargs: Any) -> MagicMock:
        created.append({"args": args, **kwargs})
        return MagicMock()

    with patch("agent.xlsliberator.subagents.create_agent", side_effect=fake_create_agent):
        specs = build_migration_subagents(
            _model(),
            _tools(
                "xlsliberator_runtime_build_application_candidate",
                "xlsliberator_runtime_run_application_scenario",
                "xlsliberator_runtime_bundle_application_replays",
            ),
            compact=True,
        )

    assert len(created) == len(SPECIALIST_PROFILES)
    assert all("runnable" in spec for spec in specs)
    assert all("model" not in spec and "skills" not in spec for spec in specs)
    for call in created:
        assert call["response_format"] is SpecialistResult
        assert "Do not copy a demo or special-case a fixture." in call["system_prompt"]
        middleware = call["middleware"]
        filesystem = next(item for item in middleware if isinstance(item, FilesystemMiddleware))
        enabled_tools = set(filesystem._enabled_tools or ())
        assert enabled_tools == {
            "ls",
            "read_file",
            "write_file",
            "edit_file",
        }
        assert filesystem._custom_system_prompt == ""
        assert "execute" not in enabled_tools


def test_candidate_tournament_isolates_two_candidates_and_evaluator() -> None:
    tournament = candidate_tournament(
        "pricing/MonthEnd",
        ("formula-engineer", "vba-liberation-engineer"),
    )

    assert tournament.module_id == "pricing-MonthEnd"
    assert tournament.candidate_agents == (
        "formula-engineer",
        "vba-liberation-engineer",
    )
    assert tournament.candidate_paths[0] != tournament.candidate_paths[1]
    assert tournament.evaluator_agent == "test-adversary"
    assert tournament.evidence_path.endswith("/evaluation.json")


@pytest.mark.parametrize(
    ("agents", "evaluator"),
    [
        (("formula-engineer", "formula-engineer"), "test-adversary"),
        (("unknown", "formula-engineer"), "test-adversary"),
        (("formula-engineer", "vba-liberation-engineer"), "formula-engineer"),
    ],
)
def test_candidate_tournament_rejects_non_independent_roles(
    agents: tuple[str, str],
    evaluator: str,
) -> None:
    with pytest.raises(ValueError):
        candidate_tournament("module", agents, evaluator_agent=evaluator)
