"""Evidence-derived workbook migration evaluation tests."""

from __future__ import annotations

from agent.xlsliberator.evaluation import (
    BenchmarkPartition,
    EvaluationStatus,
    EvaluatorName,
    MigrationEvaluationInput,
    MigrationEvaluationReport,
    MigrationEvaluationTraceMiddleware,
    aggregate_benchmark,
    evaluate_migration,
)


def _observed(**updates: object) -> MigrationEvaluationInput:
    payload: dict[str, object] = {
        "migration_id": "invoice-001",
        "source_format": "xlsm",
        "feature_families": ["vba", "userforms", "formulas"],
        "model_id": "openai:gpt-5.6",
        "provider": "openai",
        "model_version": "gpt-5.6",
        "team_configuration": "lead-specialists-v1",
        "required_specialists": [
            "workbook-forensics",
            "vba-liberation-engineer",
            "ui-migration-engineer",
            "test-adversary",
        ],
        "delegated_specialists": [
            "workbook-forensics",
            "vba-liberation-engineer",
            "ui-migration-engineer",
            "test-adversary",
        ],
        "expected_skills": [
            "workbook-forensics",
            "vba-to-python-uno",
            "userform-to-uno",
            "migration-test-design",
        ],
        "selected_skills": [
            "workbook-forensics",
            "vba-to-python-uno",
            "userform-to-uno",
            "migration-test-design",
        ],
        "public_corpus_status": "passed",
        "deterministic_gate_status": "passed",
        "complete_evidence": True,
        "validator_sha256_before": "a" * 64,
        "validator_sha256_after": "a" * 64,
        "source_scenarios": 10,
        "source_derived_scenarios": 10,
        "hidden_acceptance_status": "passed",
        "mutation_status": "passed",
        "mutation_total": 10,
        "mutation_killed": 9,
        "save_reopen_status": "passed",
        "remaining_proprietary_dependencies": [],
        "reviewer_state": "APPROVE",
        "generic_repair_applicable": False,
        "manual_interventions": 0,
        "cost_usd": 1.5,
        "latency_seconds": 90,
        "cost_budget_usd": 5,
        "latency_budget_seconds": 600,
        "security_policy_status": "passed",
        "evidence_paths": {
            evaluator.value: f"migration/evidence/evaluations/{evaluator.value}.json"
            for evaluator in EvaluatorName
        },
    }
    payload.update(updates)
    return MigrationEvaluationInput.model_validate(payload)


def _status(
    report: MigrationEvaluationReport,
    evaluator: EvaluatorName,
) -> EvaluationStatus:
    return next(result.status for result in report.evaluators if result.evaluator is evaluator)


def test_all_fourteen_evaluators_pass_or_truthfully_skip() -> None:
    report = evaluate_migration(_observed())

    assert {result.evaluator for result in report.evaluators} == set(EvaluatorName)
    assert len(report.evaluators) == 14
    assert report.release_ready is True
    assert report.release_blockers == ()
    assert _status(report, EvaluatorName.GENERIC_REPAIR_REUSE) is EvaluationStatus.SKIPPED
    assert all(
        result.status is EvaluationStatus.PASSED or not result.required
        for result in report.evaluators
    )


def test_required_corpus_security_hidden_and_reviewer_gates_block_release() -> None:
    report = evaluate_migration(
        _observed(
            public_corpus_status="failed",
            hidden_acceptance_status="unavailable",
            security_policy_status="failed",
            reviewer_state="BLOCK",
            reviewer_rejection_reason="security and hidden acceptance are not green",
        )
    )

    assert report.release_ready is False
    assert "required-public-corpus" in report.release_blockers
    assert "required-security" in report.release_blockers
    assert "required-hidden-acceptance" in report.release_blockers
    assert "independent-reviewer-approval" in report.release_blockers
    assert _status(report, EvaluatorName.REVIEWER_AGREEMENT) is EvaluationStatus.PASSED


def test_fake_success_test_weakening_and_weak_source_tests_are_detected() -> None:
    report = evaluate_migration(
        _observed(
            complete_evidence=False,
            validator_sha256_after="b" * 64,
            source_derived_scenarios=4,
            reviewer_state="REVISE",
            reviewer_rejection_reason="deterministic evidence is incomplete",
        )
    )

    assert _status(report, EvaluatorName.NO_FAKE_SUCCESS) is EvaluationStatus.FAILED
    assert _status(report, EvaluatorName.NO_TEST_WEAKENING) is EvaluationStatus.FAILED
    assert _status(report, EvaluatorName.SOURCE_DERIVED_TEST_QUALITY) is EvaluationStatus.FAILED


def test_delegation_skills_mutations_dependency_and_repair_reuse_are_scored() -> None:
    report = evaluate_migration(
        _observed(
            delegated_specialists=["workbook-forensics"],
            selected_skills=["workbook-forensics"],
            mutation_total=10,
            mutation_killed=2,
            remaining_proprietary_dependencies=["VBA project", "Excel COM"],
            generic_repair_applicable=True,
            generic_repair_reused=False,
            reviewer_state="BLOCK",
            reviewer_rejection_reason="proprietary dependencies remain",
        )
    )

    assert _status(report, EvaluatorName.SPECIALIST_DELEGATION) is EvaluationStatus.FAILED
    assert _status(report, EvaluatorName.SKILL_SELECTION) is EvaluationStatus.FAILED
    assert _status(report, EvaluatorName.MUTATION_KILL_RATE) is EvaluationStatus.FAILED
    assert _status(report, EvaluatorName.PROPRIETARY_DEPENDENCY_REMOVAL) is EvaluationStatus.FAILED
    assert _status(report, EvaluatorName.GENERIC_REPAIR_REUSE) is EvaluationStatus.FAILED


def test_unavailable_not_run_skipped_and_failed_remain_distinct() -> None:
    report = evaluate_migration(
        _observed(
            hidden_acceptance_status="unavailable",
            mutation_status="not_run",
            save_reopen_status="failed",
            generic_repair_applicable=False,
            cost_usd=None,
            reviewer_state="BLOCK",
            reviewer_rejection_reason="required evidence is unavailable",
        )
    )

    assert _status(report, EvaluatorName.HIDDEN_ACCEPTANCE) is EvaluationStatus.UNAVAILABLE
    assert _status(report, EvaluatorName.MUTATION_KILL_RATE) is EvaluationStatus.NOT_RUN
    assert _status(report, EvaluatorName.SAVE_REOPEN) is EvaluationStatus.FAILED
    assert _status(report, EvaluatorName.GENERIC_REPAIR_REUSE) is EvaluationStatus.SKIPPED
    assert _status(report, EvaluatorName.COST_LATENCY) is EvaluationStatus.UNAVAILABLE


def test_manual_intervention_cost_and_latency_are_release_evidence() -> None:
    report = evaluate_migration(
        _observed(
            manual_interventions=1,
            cost_usd=7,
            latency_seconds=700,
            reviewer_state="REVISE",
            reviewer_rejection_reason="autonomy and budget gates failed",
        )
    )

    assert _status(report, EvaluatorName.MANUAL_INTERVENTION_RATE) is EvaluationStatus.FAILED
    assert _status(report, EvaluatorName.COST_LATENCY) is EvaluationStatus.FAILED
    assert report.release_ready is False


def test_public_and_hidden_reports_group_by_configuration_format_and_feature() -> None:
    first = evaluate_migration(_observed())
    second = evaluate_migration(
        _observed(
            migration_id="game-001",
            source_format="xls",
            feature_families=["vba", "controls"],
            team_configuration="lead-tournament-v1",
        )
    )

    benchmark = aggregate_benchmark([first, second])

    assert benchmark.target_libreoffice_build == "26.2.4.2"
    assert set(benchmark.public_by_configuration) == {
        "lead-specialists-v1",
        "lead-tournament-v1",
    }
    assert set(benchmark.hidden_by_format) == {"xls", "xlsm"}
    assert set(benchmark.public_by_feature_family) == {
        "controls",
        "formulas",
        "userforms",
        "vba",
    }
    assert all(
        summary.partition is BenchmarkPartition.HIDDEN
        for summary in benchmark.hidden_by_configuration.values()
    )
    assert all(
        summary.hidden_definitions_included is False
        for summary in benchmark.hidden_by_configuration.values()
    )


def test_langsmith_trace_metadata_records_required_dimensions_without_hidden_cases() -> None:
    middleware = MigrationEvaluationTraceMiddleware("anthropic:claude-opus-4-8")

    metadata = middleware._metadata(
        {
            "migration_trajectory": ["lead", "workbook-forensics"],
            "migration_selected_skills": ["workbook-forensics"],
            "migration_estimated_cost_usd": 2.25,
            "migration_retry_count": 1,
            "migration_checkpoint": "implementation",
            "migration_public_result": "passed",
            "migration_hidden_result": "passed",
            "migration_mutation_result": "passed",
            "migration_reviewer_findings": [],
            "migration_generic_repair_promotion": "skipped",
        }
    )

    assert metadata["xlsliberator_model_id"] == "anthropic:claude-opus-4-8"
    assert metadata["xlsliberator_provider"] == "anthropic"
    assert metadata["xlsliberator_model_version"] == "claude-opus-4-8"
    assert metadata["xlsliberator_retry_count"] == 1
    assert metadata["xlsliberator_evidence_paths"]["hidden"] == ("migration/reviewer/result.json")
    assert "definitions" not in metadata
