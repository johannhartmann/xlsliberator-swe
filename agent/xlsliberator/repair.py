"""Fail-closed orchestration for promoting a workbook failure into a generic repair."""

from __future__ import annotations

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

RepairClassification = Literal[
    "workbook-specific",
    "xlsliberator-tool",
    "domain-skill",
    "open-service-adapter",
    "libreoffice",
    "test-validation",
]
RepairStageName = Literal[
    "reproduce",
    "minimize",
    "regression",
    "patch",
    "exact-scenario",
    "affected-corpus",
    "independent-review",
    "upstream-review",
]
RepairStatus = Literal["IN_PROGRESS", "READY_FOR_MERGE"]

REPAIR_STAGE_ORDER: tuple[RepairStageName, ...] = (
    "reproduce",
    "minimize",
    "regression",
    "patch",
    "exact-scenario",
    "affected-corpus",
    "independent-review",
    "upstream-review",
)


class RepairPromotionError(RuntimeError):
    """A repair attempted to bypass or contradict a promotion gate."""


class RepairStageEvidence(BaseModel):
    """Immutable evidence produced by one repair stage."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    stage: RepairStageName
    path: str = Field(pattern=r"^migration/repairs/[a-z0-9][a-z0-9-]+/.+")
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class LibreOfficeRepairIdentity(BaseModel):
    """Pinned identity required before Open-SWE may claim a LibreOffice repair."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    full_build: Literal["26.2.4.2"] = "26.2.4.2"
    source_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    source_archive_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    patch_set_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    stock_runtime_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    patched_runtime_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class IndependentRepairReview(BaseModel):
    """Reviewer-owned approval without private hidden-suite definitions."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    reviewer: str = Field(min_length=1, max_length=200)
    implementation_owner: str = Field(min_length=1, max_length=200)
    verdict: Literal["APPROVE"]
    evidence_path: str = Field(pattern=r"^migration/repairs/[a-z0-9][a-z0-9-]+/review/.+")
    hidden_definitions_included: Literal[False] = False

    @model_validator(mode="after")
    def reviewer_is_independent(self) -> Self:
        if self.reviewer == self.implementation_owner:
            raise ValueError("repair reviewer must be independent from implementation")
        return self


class RepairPromotionState(BaseModel):
    """Durable state for the exact generic-repair workflow."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0.0"] = "1.0.0"
    repair_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]+$")
    failure_signature: str = Field(min_length=1, max_length=500)
    classification: RepairClassification
    fixed_layer: RepairClassification
    implementation_owner: str = Field(min_length=1, max_length=200)
    validator_sha256_before: str = Field(pattern=r"^[0-9a-f]{64}$")
    validator_sha256_after: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    libreoffice: LibreOfficeRepairIdentity | None = None
    stages: list[RepairStageEvidence] = Field(default_factory=list, max_length=8)
    review: IndependentRepairReview | None = None
    focused_pr_url: str | None = None
    status: RepairStatus = "IN_PROGRESS"

    @model_validator(mode="after")
    def state_is_consistent(self) -> Self:
        if self.classification != self.fixed_layer:
            raise ValueError("repair must patch its classified owner layer")
        actual = tuple(stage.stage for stage in self.stages)
        if actual != REPAIR_STAGE_ORDER[: len(actual)]:
            raise ValueError("repair stages must be recorded exactly once and in order")
        if self.classification == "libreoffice" and len(self.stages) >= 4:
            if self.libreoffice is None:
                raise ValueError("LibreOffice patch stage requires pinned build identities")
        if self.status == "READY_FOR_MERGE":
            self._validate_completion()
        return self

    @property
    def next_stage(self) -> RepairStageName | None:
        """Return the only stage the workflow may execute next."""
        if len(self.stages) == len(REPAIR_STAGE_ORDER):
            return None
        return REPAIR_STAGE_ORDER[len(self.stages)]

    def _validate_completion(self) -> None:
        if tuple(stage.stage for stage in self.stages) != REPAIR_STAGE_ORDER:
            raise ValueError("all repair stages are required before merge")
        if (
            self.validator_sha256_after is None
            or self.validator_sha256_after != self.validator_sha256_before
        ):
            raise ValueError("validator weakening or drift blocks repair promotion")
        if self.review is None or self.review.implementation_owner != self.implementation_owner:
            raise ValueError("current independent approval is required")
        if self.focused_pr_url is None or not self.focused_pr_url.startswith("https://"):
            raise ValueError("a focused HTTPS pull request is required")


class RepairPromotionWorkflow:
    """Advance repair state only through the declared evidence-producing stages."""

    def begin(
        self,
        *,
        repair_id: str,
        failure_signature: str,
        classification: RepairClassification,
        implementation_owner: str,
        validator_sha256: str,
    ) -> RepairPromotionState:
        """Create a repair whose fixed layer cannot later be switched."""
        return RepairPromotionState(
            repair_id=repair_id,
            failure_signature=failure_signature,
            classification=classification,
            fixed_layer=classification,
            implementation_owner=implementation_owner,
            validator_sha256_before=validator_sha256,
        )

    def record_stage(
        self,
        state: RepairPromotionState,
        evidence: RepairStageEvidence,
        *,
        libreoffice: LibreOfficeRepairIdentity | None = None,
        review: IndependentRepairReview | None = None,
    ) -> RepairPromotionState:
        """Record the next stage while rejecting reordered or synthetic completion."""
        if state.status != "IN_PROGRESS" or state.next_stage is None:
            raise RepairPromotionError("completed repair cannot accept another stage")
        if evidence.stage != state.next_stage:
            raise RepairPromotionError(
                f"expected repair stage {state.next_stage}, received {evidence.stage}"
            )
        if evidence.stage == "patch" and state.classification == "libreoffice":
            if libreoffice is None:
                raise RepairPromotionError(
                    "LibreOffice repair requires source, patch, and runtime identities"
                )
        if evidence.stage == "independent-review":
            if review is None:
                raise RepairPromotionError("independent-review stage requires reviewer evidence")
            if review.implementation_owner != state.implementation_owner:
                raise RepairPromotionError("review does not identify the implementation owner")
        payload = state.model_dump(mode="json")
        return RepairPromotionState.model_validate(
            {
                **payload,
                "stages": [
                    *payload["stages"],
                    evidence.model_dump(mode="json"),
                ],
                "libreoffice": (
                    libreoffice.model_dump(mode="json")
                    if libreoffice is not None
                    else payload["libreoffice"]
                ),
                "review": review.model_dump(mode="json")
                if review is not None
                else payload["review"],
            }
        )

    def finish(
        self,
        state: RepairPromotionState,
        *,
        validator_sha256_after: str,
        focused_pr_url: str,
    ) -> RepairPromotionState:
        """Mark a repair ready only after exact execution, corpus, review, and PR gates."""
        try:
            return RepairPromotionState.model_validate(
                {
                    **state.model_dump(mode="json"),
                    "validator_sha256_after": validator_sha256_after,
                    "focused_pr_url": focused_pr_url,
                    "status": "READY_FOR_MERGE",
                }
            )
        except ValueError as exc:
            raise RepairPromotionError(str(exc)) from exc
