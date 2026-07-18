"""Tests for the generic repair promotion state machine."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agent.xlsliberator.repair import (
    REPAIR_STAGE_ORDER,
    IndependentRepairReview,
    LibreOfficeRepairIdentity,
    RepairPromotionError,
    RepairPromotionState,
    RepairPromotionWorkflow,
    RepairStageEvidence,
)

SHA = "a" * 64
SOURCE = "b" * 40


def _evidence(stage: str) -> RepairStageEvidence:
    return RepairStageEvidence.model_validate(
        {
            "stage": stage,
            "path": f"migration/repairs/tdf-172479/{stage}/evidence.json",
            "sha256": SHA,
        }
    )


def _identity() -> LibreOfficeRepairIdentity:
    return LibreOfficeRepairIdentity(
        source_commit=SOURCE,
        source_archive_sha256="c" * 64,
        patch_set_sha256="d" * 64,
        stock_runtime_digest=f"sha256:{'e' * 64}",
        patched_runtime_digest=f"sha256:{'f' * 64}",
    )


def _review() -> IndependentRepairReview:
    return IndependentRepairReview(
        reviewer="reviewer-graph",
        implementation_owner="libreoffice-engineer",
        verdict="APPROVE",
        evidence_path="migration/repairs/tdf-172479/review/verdict.json",
    )


def _complete_workflow() -> tuple[RepairPromotionWorkflow, RepairPromotionState]:
    workflow = RepairPromotionWorkflow()
    state = workflow.begin(
        repair_id="tdf-172479",
        failure_signature="formula-textafter-match-end",
        classification="libreoffice",
        implementation_owner="libreoffice-engineer",
        validator_sha256=SHA,
    )
    for stage in REPAIR_STAGE_ORDER:
        state = workflow.record_stage(
            state,
            _evidence(stage),
            libreoffice=_identity() if stage == "patch" else None,
            review=_review() if stage == "independent-review" else None,
        )
    return workflow, state


def test_real_repair_path_requires_every_stage_and_finishes_ready() -> None:
    workflow, state = _complete_workflow()

    completed = workflow.finish(
        state,
        validator_sha256_after=SHA,
        focused_pr_url="https://gerrit.libreoffice.org/c/core/+/206776",
    )

    assert completed.status == "READY_FOR_MERGE"
    assert completed.next_stage is None
    assert completed.libreoffice is not None
    assert completed.review is not None
    assert completed.review.hidden_definitions_included is False


def test_reordered_stage_and_missing_libreoffice_identity_fail_closed() -> None:
    workflow = RepairPromotionWorkflow()
    state = workflow.begin(
        repair_id="failure",
        failure_signature="stable-signature",
        classification="libreoffice",
        implementation_owner="engineer",
        validator_sha256=SHA,
    )

    with pytest.raises(RepairPromotionError, match="expected repair stage reproduce"):
        workflow.record_stage(state, _evidence("minimize"))

    for stage in ("reproduce", "minimize", "regression"):
        state = workflow.record_stage(state, _evidence(stage))
    with pytest.raises(RepairPromotionError, match="requires source, patch"):
        workflow.record_stage(state, _evidence("patch"))


def test_layer_switch_validator_weakening_and_self_review_are_rejected() -> None:
    workflow, state = _complete_workflow()
    payload = state.model_dump(mode="json")
    payload["fixed_layer"] = "test-validation"
    with pytest.raises(ValidationError, match="classified owner layer"):
        RepairPromotionState.model_validate(payload)

    with pytest.raises(RepairPromotionError, match="validator weakening"):
        workflow.finish(
            state,
            validator_sha256_after="0" * 64,
            focused_pr_url="https://example.test/repair/1",
        )

    with pytest.raises(ValidationError, match="reviewer must be independent"):
        IndependentRepairReview(
            reviewer="same-owner",
            implementation_owner="same-owner",
            verdict="APPROVE",
            evidence_path="migration/repairs/failure/review/verdict.json",
        )


def test_partial_record_cannot_claim_ready_for_merge() -> None:
    workflow = RepairPromotionWorkflow()
    state = workflow.begin(
        repair_id="failure",
        failure_signature="stable-signature",
        classification="xlsliberator-tool",
        implementation_owner="tool-engineer",
        validator_sha256=SHA,
    )

    with pytest.raises(RepairPromotionError, match="all repair stages"):
        workflow.finish(
            state,
            validator_sha256_after=SHA,
            focused_pr_url="https://example.test/repair/1",
        )
