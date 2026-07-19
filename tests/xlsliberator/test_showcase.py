"""Fail-closed evidence-contract tests for the autonomous showcase."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from io import BytesIO
from pathlib import Path
from typing import Any
from zipfile import ZipFile

import pytest
from pydantic import ValidationError

from agent.xlsliberator.showcase import (
    INTERACTIVE_GAME_SOURCE_SHA256,
    ShowcaseBundleManifest,
    inspect_showcase_archive,
    inspect_showcase_bundle,
    main,
)

SCENARIOS = [
    "keyboard-control",
    "timer-tick",
    "native-controls",
    "document-events",
    "line-collapse",
]
SPECIALISTS = [
    "workbook-forensics",
    "vba-liberation-engineer",
    "ui-migration-engineer",
    "test-adversary",
]
LIFECYCLE = [
    "open",
    "recalculate",
    "interaction",
    "event",
    "save",
    "close",
    "reopen",
    "assertions",
]


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _build_bundle(root: Path) -> dict[str, Any]:
    files: dict[str, bytes] = {}

    def reference(path: str, payload: bytes | None = None) -> dict[str, str]:
        content = payload if payload is not None else f"evidence:{path}\n".encode()
        files[path] = content
        return {"path": path, "sha256": _sha256(content)}

    dossier = reference("private-safe/dossier.md")
    candidate_files = {
        "candidate_generated/__init__.py": b'"""Generated candidate."""\n',
        "candidate_generated/adapter.py": (
            b"def build_target(request):\n    return request\n\n"
            b"def create_controller(session, document, config):\n"
            b"    return (session, document, config)\n"
        ),
    }
    candidate_manifest = {
        "schema_version": "1.0.0",
        "candidate_id": "source-derived-candidate",
        "source_sha256": INTERACTIVE_GAME_SOURCE_SHA256,
        "target_build": "26.2.4.2",
        "entrypoints": {
            "build": "candidate_generated.adapter:build_target",
            "controller": "candidate_generated.adapter:create_controller",
        },
        "files": {
            path: _sha256(content) for path, content in sorted(candidate_files.items())
        },
        "capabilities": ["native-controls", "keyboard-events"],
    }
    candidate_manifest_bytes = (
        json.dumps(candidate_manifest, indent=2, sort_keys=True) + "\n"
    ).encode()
    candidate_output = BytesIO()
    with ZipFile(candidate_output, "w") as archive:
        archive.writestr("manifest.json", candidate_manifest_bytes)
        for path, content in candidate_files.items():
            archive.writestr(path, content)
    candidate = reference("generated/candidate.zip", candidate_output.getvalue())
    target = reference("public/target.ods", b"deterministic-test-ods")
    invocation = reference("evidence/invocation.json")
    specialist_evidence = {
        role: reference(f"evidence/trajectories/{role}.json") for role in SPECIALISTS
    }
    scenario_evidence = {
        scenario: reference(f"evidence/scenarios/{scenario}.json") for scenario in SCENARIOS
    }
    lifecycle_evidence = [
        reference(f"evidence/runtime/{index:02d}-{kind}.json")
        for index, kind in enumerate(LIFECYCLE, start=1)
    ]
    mutation_trace = reference("evidence/mutations/keyboard-direction-trace.json")
    mutation_evaluation = reference("evidence/mutations/keyboard-direction-evaluation.json")
    mutation_report = reference("evidence/mutations/report.json")
    liberation = reference("evidence/liberation.json")
    review_inputs = reference("evidence/review-inputs.json")
    hidden = reference("evidence/reviewer/hidden-aggregate.json")
    reviewer = reference("evidence/reviewer/result.json")
    recording = reference("public/replay/showcase.webm", b"deterministic-test-recording")
    entrypoint = reference("public/replay/index.html", b"<!doctype html><title>Replay</title>")
    event_log = reference("public/replay/events.json")
    operations = reference("evidence/operations.json")

    target_sha256 = target["sha256"]
    models = [
        {
            "role": role,
            "provider": "test-provider",
            "model_id": f"test-provider:{role}",
            "model_version": "fixed-test-version",
            "calls": 1,
            "cost_usd": 0.1,
        }
        for role in ["lead", *SPECIALISTS]
    ]
    models.append(
        {
            "role": "independent-reviewer",
            "provider": "review-provider",
            "model_id": "review-provider:reviewer",
            "model_version": "fixed-review-version",
            "calls": 1,
            "cost_usd": 0.1,
        }
    )

    manifest: dict[str, Any] = {
        "schema_version": "1.0.0",
        "showcase_id": "interactive-game",
        "migration_id": "interactive-game-001",
        "status": "PASSED",
        "release_ready": True,
        "privacy": "public-sanitized",
        "lead_thread_id": "lead-thread",
        "source": {
            "original_filename": "TetrisGameDemo.xlsb",
            "source_format": "xlsb",
            "sha256": INTERACTIVE_GAME_SOURCE_SHA256,
            "immutable": True,
            "dossier": dossier,
        },
        "candidate": {
            "schema_version": "1.0.0",
            "candidate_id": "source-derived-candidate",
            "source_sha256": INTERACTIVE_GAME_SOURCE_SHA256,
            "target_build": "26.2.4.2",
            "build_entrypoint": "candidate_generated.adapter:build_target",
            "controller_entrypoint": "candidate_generated.adapter:create_controller",
            "file_count": len(candidate_files),
            "capabilities": ["native-controls", "keyboard-events"],
            "manifest_sha256": _sha256(candidate_manifest_bytes),
            "artifact": candidate,
        },
        "target": {
            "target": "libreoffice",
            "full_build": "26.2.4.2",
            "artifact": target,
            "built_from_candidate_sha256": candidate["sha256"],
            "runtime_image_digest": f"sha256:{'a' * 64}",
            "playable": True,
        },
        "invocation": {
            "surface": "public_api",
            "method": "POST",
            "route": "/api/xlsliberator/migrations",
            "thread_id": "lead-thread",
            "run_id": "public-run",
            "terminal_status": "DELIVERABLE",
            "source_sha256": INTERACTIVE_GAME_SOURCE_SHA256,
            "target_libreoffice_build": "26.2.4.2",
            "credential_material_included": False,
            "evidence": invocation,
        },
        "specialists": [
            {
                "role": role,
                "thread_id": f"{role}-thread",
                "model_id": f"test-provider:{role}",
                "skills": [f"{role}-skill"],
                "status": "COMPLETED",
                "self_certified": False,
                "evidence": specialist_evidence[role],
            }
            for role in SPECIALISTS
        ],
        "scenarios": [
            {
                "scenario_id": scenario,
                "source_refs": ["dependencies/ModGame.bas"],
                "oracle_policy": "authored_acceptance_requirements",
                "status": "PASSED",
                "candidate_sha256": candidate["sha256"],
                "evidence": scenario_evidence[scenario],
            }
            for scenario in SCENARIOS
        ],
        "lifecycle": [
            {
                "sequence": index,
                "kind": kind,
                "status": "PASSED",
                "evidence": lifecycle_evidence[index - 1],
            }
            for index, kind in enumerate(LIFECYCLE, start=1)
        ],
        "mutation": {
            "status": "PASSED",
            "required_kill_rate": 1.0,
            "validator_sha256_before": "b" * 64,
            "validator_sha256_after": "b" * 64,
            "total": 1,
            "killed": 1,
            "survived": 0,
            "inconclusive": 0,
            "cases": [
                {
                    "id": "keyboard-direction",
                    "category": "keyboard",
                    "source_ref": "ModGame.bas: keyboard direction",
                    "baseline_sha256": target_sha256,
                    "mutant_sha256": "c" * 64,
                    "outcome": "killed",
                    "trace": mutation_trace,
                    "evaluation": mutation_evaluation,
                }
            ],
            "evidence": mutation_report,
        },
        "liberation": {
            "status": "PASSED",
            "no_vba_project": "PASS",
            "no_basic_event_bindings": "PASS",
            "no_com_office_automation": "PASS",
            "no_windows_dll_dependency": "PASS",
            "no_excel_runtime": "PASS",
            "no_unresolved_proprietary_addin": "PASS",
            "scanned_target_sha256": target_sha256,
            "evidence": liberation,
        },
        "review_inputs": review_inputs,
        "reviewer": {
            "state": "APPROVE",
            "reviewer_thread_id": "reviewer-thread",
            "lead_thread_id": "lead-thread",
            "reviewer_model_id": "review-provider:reviewer",
            "independent_context": True,
            "reviewed_candidate_sha256": candidate["sha256"],
            "reviewed_target_sha256": target_sha256,
            "reviewed_inputs_sha256": review_inputs["sha256"],
            "mandatory_checks": "PASS",
            "blocking_findings": 0,
            "hidden": {
                "status": "PASSED",
                "executed": 3,
                "passed": 3,
                "failed": 0,
                "hidden_definitions_included": False,
                "evidence": hidden,
            },
            "evidence": reviewer,
        },
        "replay": {
            "privacy": "public-sanitized",
            "replayable": True,
            "covered_scenarios": SCENARIOS,
            "candidate_sha256": candidate["sha256"],
            "target_sha256": target_sha256,
            "recording": recording,
            "entrypoint": entrypoint,
            "event_log": event_log,
            "verification_status": "PASSED",
            "source_included": False,
            "hidden_data_included": False,
            "credentials_included": False,
            "internal_paths_included": False,
        },
        "operations": {
            "commands_documented": True,
            "service_versions_documented": True,
            "started_at": "2026-07-18T10:00:00Z",
            "ended_at": "2026-07-18T10:02:00Z",
            "runtime_seconds": 120.0,
            "manual_interventions": 0,
            "models": models,
            "aggregate_cost_usd": len(models) * 0.1,
            "limitations_documented": True,
            "limitations": [
                {
                    "summary": "Sound remains disabled without a portable capability grant.",
                    "blocking": False,
                }
            ],
            "evidence": operations,
        },
    }
    manifest["artifact_index"] = [
        {
            "path": path,
            "sha256": _sha256(content),
            "bytes": len(content),
            "media_type": (
                "application/vnd.oasis.opendocument.spreadsheet"
                if path.endswith(".ods")
                else "video/webm"
                if path.endswith(".webm")
                else "text/html"
                if path.endswith(".html")
                else "application/json"
            ),
            "privacy": "public-sanitized",
        }
        for path, content in sorted(files.items())
    ]
    for relative, content in files.items():
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
    _write_manifest(root, manifest)
    return manifest


def _write_manifest(root: Path, payload: dict[str, Any]) -> None:
    (root / "manifest.json").write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )


def test_complete_content_bound_showcase_bundle_passes(tmp_path: Path) -> None:
    _build_bundle(tmp_path)
    inspected = inspect_showcase_bundle(tmp_path)

    assert inspected.release_ready is True
    assert inspected.target.full_build == "26.2.4.2"
    assert {scenario.scenario_id for scenario in inspected.scenarios} == set(SCENARIOS)
    assert inspected.reviewer.state == "APPROVE"


def test_complete_showcase_archive_passes_safe_extraction(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "bundle"
    _build_bundle(root)
    archive = tmp_path / "public-showcase.zip"
    with ZipFile(archive, "w") as output:
        for path in sorted(root.rglob("*")):
            if path.is_file():
                output.write(path, path.relative_to(root).as_posix())

    inspected = inspect_showcase_archive(archive)

    assert inspected.release_ready is True
    assert main(["--archive", str(archive)]) == 0
    output = capsys.readouterr().out
    assert '"candidate_id": "source-derived-candidate"' in output
    assert '"reviewer_state": "APPROVE"' in output


def test_showcase_archive_rejects_path_traversal(tmp_path: Path) -> None:
    archive = tmp_path / "unsafe.zip"
    with ZipFile(archive, "w") as output:
        output.writestr("../escape.txt", "blocked")

    with pytest.raises(ValueError, match="path is unsafe"):
        inspect_showcase_archive(archive)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("source", "sha256"), "d" * 64),
        (("target", "full_build"), "26.2"),
        (("invocation", "route"), "/internal/run"),
    ],
)
def test_exact_source_target_and_public_invocation_are_required(
    tmp_path: Path,
    path: tuple[str, str],
    value: str,
) -> None:
    payload = _build_bundle(tmp_path)
    payload[path[0]][path[1]] = value

    with pytest.raises(ValidationError):
        ShowcaseBundleManifest.model_validate(payload)


def test_required_roles_scenarios_and_ordered_lifecycle_fail_closed(tmp_path: Path) -> None:
    payload = _build_bundle(tmp_path)

    no_adversary = deepcopy(payload)
    no_adversary["specialists"] = [
        item for item in no_adversary["specialists"] if item["role"] != "test-adversary"
    ]
    with pytest.raises(ValidationError, match="required specialist"):
        ShowcaseBundleManifest.model_validate(no_adversary)

    missing_scenario = deepcopy(payload)
    missing_scenario["scenarios"].pop()
    with pytest.raises(ValidationError):
        ShowcaseBundleManifest.model_validate(missing_scenario)

    reordered = deepcopy(payload)
    reordered["lifecycle"][5]["kind"] = "reopen"
    reordered["lifecycle"][6]["kind"] = "close"
    with pytest.raises(ValidationError, match="incomplete or out of order"):
        ShowcaseBundleManifest.model_validate(reordered)


def test_mutation_and_liberation_cannot_claim_partial_success(tmp_path: Path) -> None:
    payload = _build_bundle(tmp_path)

    survivor = deepcopy(payload)
    survivor["mutation"]["survived"] = 1
    survivor["mutation"]["killed"] = 0
    survivor["mutation"]["cases"][0]["outcome"] = "survived"
    with pytest.raises(ValidationError):
        ShowcaseBundleManifest.model_validate(survivor)

    contaminated = deepcopy(payload)
    contaminated["liberation"]["no_vba_project"] = "FAIL"
    with pytest.raises(ValidationError):
        ShowcaseBundleManifest.model_validate(contaminated)


def test_reviewer_must_be_independent_current_and_hidden_safe(tmp_path: Path) -> None:
    payload = _build_bundle(tmp_path)

    same_thread = deepcopy(payload)
    same_thread["reviewer"]["reviewer_thread_id"] = "lead-thread"
    with pytest.raises(ValidationError, match="fresh thread"):
        ShowcaseBundleManifest.model_validate(same_thread)

    stale = deepcopy(payload)
    stale["reviewer"]["reviewed_inputs_sha256"] = "e" * 64
    with pytest.raises(ValidationError, match="review inputs"):
        ShowcaseBundleManifest.model_validate(stale)

    stale_candidate = deepcopy(payload)
    stale_candidate["reviewer"]["reviewed_candidate_sha256"] = "f" * 64
    with pytest.raises(ValidationError, match="generated candidate"):
        ShowcaseBundleManifest.model_validate(stale_candidate)

    leaked = deepcopy(payload)
    leaked["reviewer"]["hidden"]["hidden_definitions_included"] = True
    with pytest.raises(ValidationError):
        ShowcaseBundleManifest.model_validate(leaked)


def test_replay_models_cost_and_runtime_are_complete(tmp_path: Path) -> None:
    payload = _build_bundle(tmp_path)

    incomplete_replay = deepcopy(payload)
    incomplete_replay["replay"]["covered_scenarios"] = SCENARIOS[:-1]
    with pytest.raises(ValidationError):
        ShowcaseBundleManifest.model_validate(incomplete_replay)

    missing_model = deepcopy(payload)
    missing_model["operations"]["models"] = [
        model
        for model in missing_model["operations"]["models"]
        if model["role"] != "test-adversary"
    ]
    missing_model["operations"]["aggregate_cost_usd"] -= 0.1
    with pytest.raises(ValidationError, match="model/cost records"):
        ShowcaseBundleManifest.model_validate(missing_model)

    wrong_runtime = deepcopy(payload)
    wrong_runtime["operations"]["runtime_seconds"] = 119.0
    with pytest.raises(ValidationError, match="runtime"):
        ShowcaseBundleManifest.model_validate(wrong_runtime)


def test_paths_hashes_and_artifact_completeness_are_verified(tmp_path: Path) -> None:
    payload = _build_bundle(tmp_path)

    unsafe = deepcopy(payload)
    unsafe["source"]["dossier"]["path"] = "../dossier.md"
    with pytest.raises(ValidationError, match="unsafe"):
        ShowcaseBundleManifest.model_validate(unsafe)

    target = tmp_path / "public/target.ods"
    target.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="byte count mismatch|hash mismatch"):
        inspect_showcase_bundle(tmp_path)

    target.write_bytes(b"deterministic-test-ods")
    extra = tmp_path / "public/unindexed.txt"
    extra.write_text("not indexed\n", encoding="utf-8")
    with pytest.raises(ValueError, match="does not match"):
        inspect_showcase_bundle(tmp_path)


def test_candidate_archive_is_content_bound_and_fail_closed(tmp_path: Path) -> None:
    payload = _build_bundle(tmp_path)

    wrong_target_binding = deepcopy(payload)
    wrong_target_binding["target"]["built_from_candidate_sha256"] = "e" * 64
    with pytest.raises(ValidationError, match="not built from"):
        ShowcaseBundleManifest.model_validate(wrong_target_binding)

    candidate_path = tmp_path / "generated/candidate.zip"
    with ZipFile(candidate_path, "a") as archive:
        archive.writestr("candidate_generated/special_case.py", b"fixture_specific = True\n")
    tampered = candidate_path.read_bytes()
    tampered_sha256 = _sha256(tampered)
    payload["candidate"]["artifact"]["sha256"] = tampered_sha256
    payload["target"]["built_from_candidate_sha256"] = tampered_sha256
    payload["reviewer"]["reviewed_candidate_sha256"] = tampered_sha256
    payload["replay"]["candidate_sha256"] = tampered_sha256
    for scenario in payload["scenarios"]:
        scenario["candidate_sha256"] = tampered_sha256
    indexed_candidate = next(
        artifact
        for artifact in payload["artifact_index"]
        if artifact["path"] == "generated/candidate.zip"
    )
    indexed_candidate["sha256"] = tampered_sha256
    indexed_candidate["bytes"] = len(tampered)
    _write_manifest(tmp_path, payload)

    with pytest.raises(ValueError, match="inventory does not match"):
        inspect_showcase_bundle(tmp_path)
