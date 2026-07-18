"""Independent migration reviewer graph policy tests."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from pydantic import ValidationError

from agent.xlsliberator.reviewer import (
    MIGRATION_REVIEW_TRACING_PROJECT,
    REVIEW_RESULT_PATH,
    REVIEWER_SYSTEM_PROMPT,
    HiddenAcceptanceSummary,
    LiberationReview,
    MigrationReviewerReadOnlyMiddleware,
    MigrationReviewResult,
    reviewer_prompt,
)


def _tool_request(name: str, args: dict[str, Any]) -> ToolCallRequest:
    return ToolCallRequest(
        tool_call={"name": name, "args": args, "id": "review-call"},
        tool=MagicMock(),
        state={},
        runtime=MagicMock(),
    )


async def _ok(_request: ToolCallRequest) -> ToolMessage:
    return ToolMessage(content="ok", tool_call_id="review-call")


def _liberated() -> LiberationReview:
    return LiberationReview(
        no_vba_project="PASS",
        no_basic_event_bindings="PASS",
        no_com_office_automation="PASS",
        no_windows_dll_dependency="PASS",
        no_excel_runtime="PASS",
        no_unresolved_proprietary_addin="PASS",
    )


def test_reviewer_prompt_covers_behavior_inputs_security_and_three_states() -> None:
    prompt = reviewer_prompt(reviewer_model="openai:reviewer", artifact_sha256="d" * 64)

    for fragment in (
        "original workbook",
        "complete VBA",
        "source behavior",
        "run_hidden_acceptance",
        "save/close/reopen",
        "no VBA project",
        "no Basic event binding",
        "no COM/Office automation",
        "no Windows DLL dependency",
        "no Excel runtime",
        "unresolved proprietary add-in",
        "APPROVE, REVISE, or BLOCK",
        "fresh reviewer context",
        "never hidden definitions",
    ):
        assert fragment in prompt
    assert MIGRATION_REVIEW_TRACING_PROJECT == "xlsliberator-migration-review"
    assert "d" * 64 in prompt


@pytest.mark.asyncio
async def test_reviewer_has_no_direct_write_access_even_to_result() -> None:
    middleware = MigrationReviewerReadOnlyMiddleware()

    denied = await middleware.awrap_tool_call(
        _tool_request(
            "write_file",
            {"file_path": "migration/output/target.ods", "content": "replacement"},
        ),
        _ok,
    )
    result_write = await middleware.awrap_tool_call(
        _tool_request(
            "write_file",
            {"file_path": REVIEW_RESULT_PATH, "content": "{}"},
        ),
        _ok,
    )

    assert isinstance(denied, ToolMessage)
    assert isinstance(result_write, ToolMessage)
    assert denied.status == "error"
    assert "read-only implementation access" in str(denied.content)
    assert result_write.status == "error"
    assert "submit_migration_review_result" in str(result_write.content)


def test_fake_reviewer_cannot_approve_without_hidden_and_liberation_gates() -> None:
    with pytest.raises(ValidationError, match="hidden acceptance"):
        MigrationReviewResult(
            state="APPROVE",
            reviewer_model="fake:reviewer",
            reviewed_artifact_sha256="e" * 64,
            summary="Plausible public behavior only.",
            hidden_acceptance=HiddenAcceptanceSummary(
                status="UNAVAILABLE",
                executed=0,
                passed=0,
                failed=0,
                result_evidence_path="migration/evidence/reviewer/hidden.json",
            ),
            save_reopen="PASS",
            visual_review="NOT_REQUIRED",
            source_behavior_tests="PASS",
            original_sources_reviewed="PASS",
            implementation_trace_reviewed="PASS",
            unresolved_findings_reviewed="PASS",
            liberation=_liberated(),
            evidence_paths=["migration/evidence/reviewer/summary.json"],
        )


def test_reviewer_prompt_never_authorizes_hidden_definition_export() -> None:
    assert "never quote, copy, summarize, write, or return them" in REVIEWER_SYSTEM_PROMPT
    assert "aggregate counts" in REVIEWER_SYSTEM_PROMPT
