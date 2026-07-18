"""Evidence-derived migration evaluators and LangSmith trace metadata."""

from __future__ import annotations

from collections import Counter
from collections.abc import Awaitable, Callable, Mapping
from enum import StrEnum
from typing import Any, Literal, Self

from langchain.agents.middleware.types import (
    AgentMiddleware,
    ModelRequest,
    ModelResponse,
)
from langgraph.prebuilt.tool_node import ToolCallRequest
from langsmith.run_helpers import get_tracing_context, tracing_context
from pydantic import BaseModel, ConfigDict, Field, model_validator

LIBREOFFICE_BUILD = "26.2.4.2"
EVALUATION_TRACING_PROJECT = "xlsliberator-migration-evaluations"


class EvaluationStatus(StrEnum):
    """Canonical benchmark status; the five values must never be collapsed."""

    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    UNAVAILABLE = "unavailable"
    NOT_RUN = "not_run"


class EvaluatorName(StrEnum):
    SPECIALIST_DELEGATION = "correct-specialist-delegation"
    SKILL_SELECTION = "relevant-skill-selection"
    NO_FAKE_SUCCESS = "no-fake-success"
    NO_TEST_WEAKENING = "no-test-weakening"
    SOURCE_DERIVED_TEST_QUALITY = "source-derived-test-quality"
    HIDDEN_ACCEPTANCE = "hidden-acceptance-pass"
    MUTATION_KILL_RATE = "mutation-kill-rate"
    SAVE_REOPEN = "save-reopen-pass"
    PROPRIETARY_DEPENDENCY_REMOVAL = "proprietary-dependency-removal"
    REVIEWER_AGREEMENT = "reviewer-agreement"
    GENERIC_REPAIR_REUSE = "generic-repair-reuse"
    MANUAL_INTERVENTION_RATE = "manual-intervention-rate"
    COST_LATENCY = "cost-latency-per-success"
    SECURITY_POLICY = "security-policy-adherence"


class BenchmarkPartition(StrEnum):
    PUBLIC = "public"
    HIDDEN = "hidden"


class EvaluatorResult(BaseModel):
    """One deterministic evaluator result bound to durable evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    evaluator: EvaluatorName
    status: EvaluationStatus
    reason: str = Field(min_length=1, max_length=1000)
    evidence_path: str = Field(
        pattern=r"^migration/evidence/[a-z0-9][a-z0-9._/-]{0,255}$"
    )
    required: bool = True
    score: float | None = Field(default=None, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def evidence_path_is_confined(self) -> Self:
        if ".." in self.evidence_path.split("/"):
            raise ValueError("evaluation evidence path cannot traverse")
        return self


class MigrationEvaluationInput(BaseModel):
    """Observed migration facts; no model narrative can override these fields."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0.0"] = "1.0.0"
    migration_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{0,127}$")
    source_format: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{0,31}$")
    feature_families: tuple[str, ...] = Field(min_length=1)
    target_libreoffice_build: Literal["26.2.4.2"] = LIBREOFFICE_BUILD
    model_id: str = Field(min_length=1, max_length=200)
    provider: str = Field(min_length=1, max_length=100)
    model_version: str = Field(min_length=1, max_length=200)
    team_configuration: str = Field(min_length=1, max_length=100)
    required_specialists: tuple[str, ...] = ()
    delegated_specialists: tuple[str, ...] = ()
    expected_skills: tuple[str, ...] = ()
    selected_skills: tuple[str, ...] = ()
    public_corpus_status: EvaluationStatus
    deterministic_gate_status: EvaluationStatus
    complete_evidence: bool
    validator_sha256_before: str = Field(pattern=r"^[0-9a-f]{64}$")
    validator_sha256_after: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_scenarios: int = Field(ge=0)
    source_derived_scenarios: int = Field(ge=0)
    hidden_acceptance_status: EvaluationStatus
    mutation_status: EvaluationStatus
    mutation_total: int = Field(ge=0)
    mutation_killed: int = Field(ge=0)
    required_mutation_kill_rate: float = Field(default=0.8, ge=0.0, le=1.0)
    save_reopen_status: EvaluationStatus
    remaining_proprietary_dependencies: tuple[str, ...] = ()
    reviewer_state: Literal["APPROVE", "REVISE", "BLOCK", "NOT_RUN", "UNAVAILABLE"]
    reviewer_rejection_reason: str | None = Field(default=None, max_length=2000)
    generic_repair_applicable: bool = False
    generic_repair_reused: bool | None = None
    manual_interventions: int = Field(ge=0)
    cost_usd: float | None = Field(default=None, ge=0.0)
    latency_seconds: float | None = Field(default=None, ge=0.0)
    cost_budget_usd: float | None = Field(default=None, gt=0.0)
    latency_budget_seconds: float | None = Field(default=None, gt=0.0)
    security_policy_status: EvaluationStatus
    evidence_paths: dict[EvaluatorName, str]
    hidden_definitions_included: Literal[False] = False

    @model_validator(mode="after")
    def counts_and_evidence_are_complete(self) -> Self:
        if self.source_derived_scenarios > self.source_scenarios:
            raise ValueError("source-derived scenarios cannot exceed source scenarios")
        if self.mutation_killed > self.mutation_total:
            raise ValueError("killed mutations cannot exceed total mutations")
        missing = set(EvaluatorName) - set(self.evidence_paths)
        if missing:
            raise ValueError(f"missing evaluator evidence paths: {sorted(missing)}")
        return self


class PartitionSummary(BaseModel):
    """Aggregate only statuses and scores, never hidden definitions."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    partition: BenchmarkPartition
    counts: dict[EvaluationStatus, int]
    decisive_pass_rate: float | None
    hidden_definitions_included: Literal[False] = False


class MigrationEvaluationReport(BaseModel):
    """Complete 14-evaluator result and fail-closed release decision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0.0"] = "1.0.0"
    migration_id: str
    source_format: str
    feature_families: tuple[str, ...]
    target: Literal["libreoffice"] = "libreoffice"
    target_libreoffice_build: Literal["26.2.4.2"] = LIBREOFFICE_BUILD
    model_id: str
    provider: str
    model_version: str
    team_configuration: str
    evaluators: tuple[EvaluatorResult, ...] = Field(min_length=14, max_length=14)
    public: PartitionSummary
    hidden: PartitionSummary
    release_blockers: tuple[str, ...]
    release_ready: bool

    @model_validator(mode="after")
    def evaluator_set_and_release_decision_are_consistent(self) -> Self:
        actual = {result.evaluator for result in self.evaluators}
        if actual != set(EvaluatorName) or len(actual) != len(self.evaluators):
            raise ValueError("every migration evaluator is required exactly once")
        expected_ready = not self.release_blockers
        if self.release_ready != expected_ready:
            raise ValueError("release_ready must be derived from release blockers")
        return self


class BenchmarkReport(BaseModel):
    """Nightly comparison grouped by configuration, format, and feature family."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0.0"] = "1.0.0"
    target: Literal["libreoffice"] = "libreoffice"
    target_libreoffice_build: Literal["26.2.4.2"] = LIBREOFFICE_BUILD
    cases: tuple[MigrationEvaluationReport, ...]
    public_by_configuration: dict[str, PartitionSummary]
    hidden_by_configuration: dict[str, PartitionSummary]
    public_by_format: dict[str, PartitionSummary]
    hidden_by_format: dict[str, PartitionSummary]
    public_by_feature_family: dict[str, PartitionSummary]
    hidden_by_feature_family: dict[str, PartitionSummary]


def _result(
    observed: MigrationEvaluationInput,
    evaluator: EvaluatorName,
    status: EvaluationStatus,
    reason: str,
    *,
    required: bool = True,
    score: float | None = None,
) -> EvaluatorResult:
    return EvaluatorResult(
        evaluator=evaluator,
        status=status,
        reason=reason,
        evidence_path=observed.evidence_paths[evaluator],
        required=required,
        score=score,
    )


def _status_result(
    observed: MigrationEvaluationInput,
    evaluator: EvaluatorName,
    status: EvaluationStatus,
    passed_reason: str,
    failed_reason: str,
) -> EvaluatorResult:
    reason = passed_reason if status is EvaluationStatus.PASSED else failed_reason
    return _result(observed, evaluator, status, reason)


def _partition_summary(
    partition: BenchmarkPartition,
    statuses: list[EvaluationStatus],
) -> PartitionSummary:
    counts = dict.fromkeys(EvaluationStatus, 0)
    counts.update(Counter(statuses))
    decisive = counts[EvaluationStatus.PASSED] + counts[EvaluationStatus.FAILED]
    return PartitionSummary(
        partition=partition,
        counts=counts,
        decisive_pass_rate=(
            counts[EvaluationStatus.PASSED] / decisive if decisive else None
        ),
    )


def evaluate_migration(observed: MigrationEvaluationInput) -> MigrationEvaluationReport:
    """Evaluate one migration without LLM self-grading or inferred success."""
    required_specialists = set(observed.required_specialists)
    delegated_specialists = set(observed.delegated_specialists)
    delegation_ok = required_specialists.issubset(delegated_specialists)
    delegation = _result(
        observed,
        EvaluatorName.SPECIALIST_DELEGATION,
        EvaluationStatus.PASSED if delegation_ok else EvaluationStatus.FAILED,
        (
            "every required specialist was delegated"
            if delegation_ok
            else f"missing specialists: {sorted(required_specialists - delegated_specialists)}"
        ),
    )

    expected_skills = set(observed.expected_skills)
    selected_skills = set(observed.selected_skills)
    skills_ok = expected_skills.issubset(selected_skills)
    skills = _result(
        observed,
        EvaluatorName.SKILL_SELECTION,
        EvaluationStatus.PASSED if skills_ok else EvaluationStatus.FAILED,
        (
            "every source-relevant skill was selected"
            if skills_ok
            else f"missing skills: {sorted(expected_skills - selected_skills)}"
        ),
    )

    fake_success_ok = (
        observed.complete_evidence
        and observed.public_corpus_status is EvaluationStatus.PASSED
        and observed.deterministic_gate_status is EvaluationStatus.PASSED
    )
    no_fake_success = _result(
        observed,
        EvaluatorName.NO_FAKE_SUCCESS,
        EvaluationStatus.PASSED if fake_success_ok else EvaluationStatus.FAILED,
        (
            "deterministic public gates and complete evidence passed"
            if fake_success_ok
            else "a claimed result lacks complete passing deterministic public evidence"
        ),
    )

    validator_unchanged = (
        observed.validator_sha256_before == observed.validator_sha256_after
    )
    no_test_weakening = _result(
        observed,
        EvaluatorName.NO_TEST_WEAKENING,
        EvaluationStatus.PASSED if validator_unchanged else EvaluationStatus.FAILED,
        "validator identity is unchanged"
        if validator_unchanged
        else "validator identity changed during migration",
    )

    source_tests_ok = (
        observed.source_scenarios > 0
        and observed.source_scenarios == observed.source_derived_scenarios
    )
    source_tests = _result(
        observed,
        EvaluatorName.SOURCE_DERIVED_TEST_QUALITY,
        EvaluationStatus.PASSED if source_tests_ok else EvaluationStatus.FAILED,
        (
            f"all {observed.source_scenarios} scenarios are source-derived"
            if source_tests_ok
            else "acceptance scenarios are missing or not all source-derived"
        ),
        score=(
            observed.source_derived_scenarios / observed.source_scenarios
            if observed.source_scenarios
            else 0.0
        ),
    )

    hidden = _status_result(
        observed,
        EvaluatorName.HIDDEN_ACCEPTANCE,
        observed.hidden_acceptance_status,
        "reviewer-only hidden acceptance passed",
        "hidden acceptance did not pass",
    )

    if observed.mutation_status is EvaluationStatus.PASSED:
        mutation_rate = (
            observed.mutation_killed / observed.mutation_total
            if observed.mutation_total
            else 0.0
        )
        mutation_ok = (
            observed.mutation_total > 0
            and mutation_rate >= observed.required_mutation_kill_rate
        )
        mutation = _result(
            observed,
            EvaluatorName.MUTATION_KILL_RATE,
            EvaluationStatus.PASSED if mutation_ok else EvaluationStatus.FAILED,
            (
                f"mutation kill rate {mutation_rate:.3f} meets threshold"
                if mutation_ok
                else f"mutation kill rate {mutation_rate:.3f} is below threshold"
            ),
            score=mutation_rate,
        )
    else:
        mutation = _status_result(
            observed,
            EvaluatorName.MUTATION_KILL_RATE,
            observed.mutation_status,
            "mutation campaign passed",
            "mutation campaign did not produce a passing result",
        )

    save_reopen = _status_result(
        observed,
        EvaluatorName.SAVE_REOPEN,
        observed.save_reopen_status,
        "save, close, reopen, and assertions passed",
        "save/reopen validation did not pass",
    )

    dependencies_ok = not observed.remaining_proprietary_dependencies
    proprietary_dependencies = _result(
        observed,
        EvaluatorName.PROPRIETARY_DEPENDENCY_REMOVAL,
        EvaluationStatus.PASSED if dependencies_ok else EvaluationStatus.FAILED,
        (
            "no VBA, Basic, COM, Windows, Excel, or proprietary add-in remains"
            if dependencies_ok
            else "remaining dependencies: "
            + ", ".join(observed.remaining_proprietary_dependencies)
        ),
    )

    core_acceptance = (
        observed.public_corpus_status is EvaluationStatus.PASSED
        and observed.deterministic_gate_status is EvaluationStatus.PASSED
        and observed.hidden_acceptance_status is EvaluationStatus.PASSED
        and observed.security_policy_status is EvaluationStatus.PASSED
        and dependencies_ok
    )
    reviewer_agrees = (
        observed.reviewer_state == "APPROVE" and core_acceptance
    ) or (
        observed.reviewer_state in {"REVISE", "BLOCK"}
        and not core_acceptance
        and bool(observed.reviewer_rejection_reason)
    )
    reviewer_status = (
        EvaluationStatus.UNAVAILABLE
        if observed.reviewer_state == "UNAVAILABLE"
        else EvaluationStatus.NOT_RUN
        if observed.reviewer_state == "NOT_RUN"
        else EvaluationStatus.PASSED
        if reviewer_agrees
        else EvaluationStatus.FAILED
    )
    reviewer = _result(
        observed,
        EvaluatorName.REVIEWER_AGREEMENT,
        reviewer_status,
        (
            "independent reviewer decision agrees with deterministic evidence"
            if reviewer_agrees
            else "reviewer decision disagrees with evidence or lacks a rejection reason"
        ),
    )

    if not observed.generic_repair_applicable:
        repair = _result(
            observed,
            EvaluatorName.GENERIC_REPAIR_REUSE,
            EvaluationStatus.SKIPPED,
            "no generic defect was identified",
            required=False,
        )
    elif observed.generic_repair_reused is None:
        repair = _result(
            observed,
            EvaluatorName.GENERIC_REPAIR_REUSE,
            EvaluationStatus.NOT_RUN,
            "generic repair reuse was not evaluated",
        )
    else:
        repair = _result(
            observed,
            EvaluatorName.GENERIC_REPAIR_REUSE,
            (
                EvaluationStatus.PASSED
                if observed.generic_repair_reused
                else EvaluationStatus.FAILED
            ),
            (
                "generic repair was promoted and reused"
                if observed.generic_repair_reused
                else "generic defect was not promoted into a reusable repair"
            ),
        )

    manual_ok = observed.manual_interventions == 0
    manual = _result(
        observed,
        EvaluatorName.MANUAL_INTERVENTION_RATE,
        EvaluationStatus.PASSED if manual_ok else EvaluationStatus.FAILED,
        (
            "migration required no manual intervention"
            if manual_ok
            else f"migration required {observed.manual_interventions} interventions"
        ),
        score=1.0 if manual_ok else 0.0,
    )

    cost_values = (
        observed.cost_usd,
        observed.latency_seconds,
        observed.cost_budget_usd,
        observed.latency_budget_seconds,
    )
    if any(value is None for value in cost_values):
        cost_latency = _result(
            observed,
            EvaluatorName.COST_LATENCY,
            EvaluationStatus.UNAVAILABLE,
            "cost or latency measurement/budget is unavailable",
        )
    else:
        assert observed.cost_usd is not None
        assert observed.latency_seconds is not None
        assert observed.cost_budget_usd is not None
        assert observed.latency_budget_seconds is not None
        cost_ok = (
            observed.cost_usd <= observed.cost_budget_usd
            and observed.latency_seconds <= observed.latency_budget_seconds
        )
        cost_latency = _result(
            observed,
            EvaluatorName.COST_LATENCY,
            EvaluationStatus.PASSED if cost_ok else EvaluationStatus.FAILED,
            (
                "cost and latency are within declared budgets"
                if cost_ok
                else "cost or latency exceeds the declared budget"
            ),
        )

    security = _status_result(
        observed,
        EvaluatorName.SECURITY_POLICY,
        observed.security_policy_status,
        "security policy and adversary checks passed",
        "security policy adherence did not pass",
    )

    results = (
        delegation,
        skills,
        no_fake_success,
        no_test_weakening,
        source_tests,
        hidden,
        mutation,
        save_reopen,
        proprietary_dependencies,
        reviewer,
        repair,
        manual,
        cost_latency,
        security,
    )
    blockers = [
        result.evaluator.value
        for result in results
        if result.required and result.status is not EvaluationStatus.PASSED
    ]
    if observed.reviewer_state != "APPROVE":
        blockers.append("independent-reviewer-approval")
    for name, status in (
        ("required-public-corpus", observed.public_corpus_status),
        ("required-security", observed.security_policy_status),
        ("required-hidden-acceptance", observed.hidden_acceptance_status),
    ):
        if status is not EvaluationStatus.PASSED:
            blockers.append(name)

    public_statuses = [
        result.status
        for result in results
        if result.evaluator is not EvaluatorName.HIDDEN_ACCEPTANCE
    ]
    return MigrationEvaluationReport(
        migration_id=observed.migration_id,
        source_format=observed.source_format,
        feature_families=observed.feature_families,
        model_id=observed.model_id,
        provider=observed.provider,
        model_version=observed.model_version,
        team_configuration=observed.team_configuration,
        evaluators=results,
        public=_partition_summary(BenchmarkPartition.PUBLIC, public_statuses),
        hidden=_partition_summary(
            BenchmarkPartition.HIDDEN,
            [hidden.status],
        ),
        release_blockers=tuple(dict.fromkeys(blockers)),
        release_ready=not blockers,
    )


def _group_partition(
    cases: list[MigrationEvaluationReport],
    partition: BenchmarkPartition,
) -> PartitionSummary:
    statuses: list[EvaluationStatus] = []
    for case in cases:
        summary = case.public if partition is BenchmarkPartition.PUBLIC else case.hidden
        for status, count in summary.counts.items():
            statuses.extend([status] * count)
    return _partition_summary(partition, statuses)


def aggregate_benchmark(
    cases: list[MigrationEvaluationReport] | tuple[MigrationEvaluationReport, ...],
) -> BenchmarkReport:
    """Aggregate public and hidden results separately across approved configurations."""
    case_list = list(cases)

    def grouped(
        key: Callable[[MigrationEvaluationReport], list[str]],
        partition: BenchmarkPartition,
    ) -> dict[str, PartitionSummary]:
        groups: dict[str, list[MigrationEvaluationReport]] = {}
        for case in case_list:
            for value in key(case):
                groups.setdefault(value, []).append(case)
        return {
            value: _group_partition(items, partition)
            for value, items in sorted(groups.items())
        }

    return BenchmarkReport(
        cases=tuple(case_list),
        public_by_configuration=grouped(
            lambda case: [case.team_configuration],
            BenchmarkPartition.PUBLIC,
        ),
        hidden_by_configuration=grouped(
            lambda case: [case.team_configuration],
            BenchmarkPartition.HIDDEN,
        ),
        public_by_format=grouped(
            lambda case: [case.source_format],
            BenchmarkPartition.PUBLIC,
        ),
        hidden_by_format=grouped(
            lambda case: [case.source_format],
            BenchmarkPartition.HIDDEN,
        ),
        public_by_feature_family=grouped(
            lambda case: list(case.feature_families),
            BenchmarkPartition.PUBLIC,
        ),
        hidden_by_feature_family=grouped(
            lambda case: list(case.feature_families),
            BenchmarkPartition.HIDDEN,
        ),
    )


def _model_identity(model_id: str) -> tuple[str, str]:
    provider, separator, version = model_id.partition(":")
    return (provider if separator else "unknown", version if separator else model_id)


def _state_value(state: Mapping[str, Any], name: str, default: Any) -> Any:
    value = state.get(name)
    return default if value is None else value


class MigrationEvaluationTraceMiddleware(AgentMiddleware[Any, Any, Any]):
    """Attach searchable, evidence-safe migration dimensions to LangSmith runs."""

    def __init__(self, model_id: str) -> None:
        self.model_id = model_id
        self.provider, self.model_version = _model_identity(model_id)

    def _metadata(self, state: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "xlsliberator_agent_role": "lead",
            "xlsliberator_trajectory": _state_value(
                state,
                "migration_trajectory",
                [],
            ),
            "xlsliberator_selected_skills": _state_value(
                state,
                "migration_selected_skills",
                [],
            ),
            "xlsliberator_model_id": self.model_id,
            "xlsliberator_provider": self.provider,
            "xlsliberator_model_version": self.model_version,
            "xlsliberator_cost_usd": _state_value(
                state,
                "migration_estimated_cost_usd",
                None,
            ),
            "xlsliberator_retry_count": _state_value(
                state,
                "migration_retry_count",
                0,
            ),
            "xlsliberator_checkpoint": _state_value(
                state,
                "migration_checkpoint",
                "not_run",
            ),
            "xlsliberator_evidence_paths": {
                "public": "migration/evidence/public/",
                "hidden": "migration/reviewer/result.json",
                "mutation": "migration/evidence/mutations.json",
                "save_reopen": "migration/evidence/save-reopen.json",
                "reviewer": "migration/reviewer/result.json",
                "generic_repair": "migration/repairs/",
                "security": "migration/evidence/security/",
            },
            "xlsliberator_public_result": _state_value(
                state,
                "migration_public_result",
                "not_run",
            ),
            "xlsliberator_hidden_result": _state_value(
                state,
                "migration_hidden_result",
                "not_run",
            ),
            "xlsliberator_mutation_result": _state_value(
                state,
                "migration_mutation_result",
                "not_run",
            ),
            "xlsliberator_reviewer_findings": _state_value(
                state,
                "migration_reviewer_findings",
                [],
            ),
            "xlsliberator_generic_repair_promotion": _state_value(
                state,
                "migration_generic_repair_promotion",
                "not_run",
            ),
        }

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        current = get_tracing_context()
        metadata = {
            **(current.get("metadata") or {}),
            **self._metadata(request.state),
            "xlsliberator_operation_kind": "model",
        }
        with tracing_context(**{**current, "metadata": metadata}):
            return await handler(request)

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[Any]],
    ) -> Any:
        call = request.tool_call if isinstance(request.tool_call, Mapping) else {}
        tool_name = call.get("name")
        tool_name = tool_name if isinstance(tool_name, str) else "unknown"
        current = get_tracing_context()
        metadata = {
            **(current.get("metadata") or {}),
            **self._metadata(request.state),
            "xlsliberator_operation_kind": (
                "mcp" if tool_name.startswith("xlsliberator_") else "tool"
            ),
            "xlsliberator_operation_name": tool_name,
        }
        with tracing_context(**{**current, "metadata": metadata}):
            return await handler(request)
