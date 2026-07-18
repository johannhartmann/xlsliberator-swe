"""Fail-closed evidence contract for the first autonomous migration showcase."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import stat
from datetime import datetime
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from typing import Literal, Self
from zipfile import BadZipFile, ZipFile

from pydantic import BaseModel, ConfigDict, Field, model_validator

INTERACTIVE_GAME_SOURCE_SHA256 = "da1bddc2c20ed8f5557b547e04a84cb1b476eca010e30a6be549be650894e4d1"
LIBREOFFICE_BUILD = "26.2.4.2"
MAX_ARCHIVE_FILES = 500
MAX_ARCHIVE_FILE_BYTES = 256 * 1024 * 1024
MAX_ARCHIVE_TOTAL_BYTES = 512 * 1024 * 1024
PUBLIC_SCENARIOS = frozenset(
    {
        "keyboard-control",
        "timer-tick",
        "native-controls",
        "document-events",
        "line-collapse",
    }
)
BASE_SPECIALIST_ROLES = frozenset(
    {
        "workbook-forensics",
        "vba-liberation-engineer",
        "test-adversary",
    }
)
UI_DEPENDENCY_ROLES = frozenset(
    {
        "ui-migration-engineer",
        "dependency-liberation-engineer",
    }
)
LIFECYCLE = (
    "open",
    "recalculate",
    "interaction",
    "event",
    "save",
    "close",
    "reopen",
    "assertions",
)


class StrictModel(BaseModel):
    """Immutable public boundary model with no tolerated extension fields."""

    model_config = ConfigDict(extra="forbid", frozen=True)


def _safe_artifact_path(value: str) -> str:
    path = PurePosixPath(value)
    if (
        not value
        or value == "manifest.json"
        or path.is_absolute()
        or ".." in path.parts
        or "." in path.parts
        or "\\" in value
        or value != path.as_posix()
    ):
        raise ValueError(f"showcase artifact path is unsafe: {value}")
    return value


class ArtifactRef(StrictModel):
    """Content-bound reference to one file inside the public bundle."""

    path: str = Field(min_length=1, max_length=500)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def path_stays_in_bundle(self) -> Self:
        _safe_artifact_path(self.path)
        return self


class IndexedArtifact(ArtifactRef):
    """Artifact index entry used for completeness and byte-level verification."""

    bytes: int = Field(gt=0)
    media_type: str = Field(min_length=1, max_length=200)
    privacy: Literal["public-sanitized"] = "public-sanitized"


class SourceIdentity(StrictModel):
    """Immutable identity of the real upstream interactive workbook."""

    original_filename: Literal["TetrisGameDemo.xlsb"] = "TetrisGameDemo.xlsb"
    source_format: Literal["xlsb"] = "xlsb"
    sha256: Literal["da1bddc2c20ed8f5557b547e04a84cb1b476eca010e30a6be549be650894e4d1"] = (
        INTERACTIVE_GAME_SOURCE_SHA256
    )
    immutable: Literal[True] = True
    dossier: ArtifactRef


class TargetIdentity(StrictModel):
    """Human-usable target bound to the sole supported office runtime."""

    target: Literal["libreoffice"] = "libreoffice"
    full_build: Literal["26.2.4.2"] = LIBREOFFICE_BUILD
    artifact: ArtifactRef
    runtime_image_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    playable: Literal[True] = True

    @model_validator(mode="after")
    def target_is_an_ods_application(self) -> Self:
        if not self.artifact.path.endswith(".ods"):
            raise ValueError("showcase target must be an ODS application")
        return self


class InvocationEvidence(StrictModel):
    """Proof that the episode entered through a public product surface."""

    surface: Literal["public_api", "web_ui"]
    method: Literal["POST"] = "POST"
    route: Literal["/api/xlsliberator/migrations", "/api/jobs"]
    thread_id: str = Field(min_length=1, max_length=200)
    run_id: str = Field(min_length=1, max_length=200)
    terminal_status: Literal["DELIVERABLE"] = "DELIVERABLE"
    source_sha256: Literal["da1bddc2c20ed8f5557b547e04a84cb1b476eca010e30a6be549be650894e4d1"] = (
        INTERACTIVE_GAME_SOURCE_SHA256
    )
    target_libreoffice_build: Literal["26.2.4.2"] = LIBREOFFICE_BUILD
    credential_material_included: Literal[False] = False
    evidence: ArtifactRef


SpecialistRole = Literal[
    "workbook-forensics",
    "vba-liberation-engineer",
    "ui-migration-engineer",
    "dependency-liberation-engineer",
    "test-adversary",
]


class SpecialistTrajectory(StrictModel):
    """Bounded specialist result; specialists can never certify the showcase."""

    role: SpecialistRole
    thread_id: str = Field(min_length=1, max_length=200)
    model_id: str = Field(min_length=1, max_length=200)
    skills: tuple[str, ...] = Field(min_length=1)
    status: Literal["COMPLETED"] = "COMPLETED"
    self_certified: Literal[False] = False
    evidence: ArtifactRef


class ScenarioEvidence(StrictModel):
    """One canonical public source-derived scenario and its passing result."""

    scenario_id: Literal[
        "keyboard-control",
        "timer-tick",
        "native-controls",
        "document-events",
        "line-collapse",
    ]
    source_refs: tuple[str, ...] = Field(min_length=1)
    oracle_policy: Literal["authored_acceptance_requirements"] = "authored_acceptance_requirements"
    status: Literal["PASSED"] = "PASSED"
    evidence: ArtifactRef


class LifecycleOperation(StrictModel):
    """One real target operation in the ordered LibreOffice lifecycle."""

    sequence: int = Field(ge=1)
    kind: Literal[
        "open",
        "recalculate",
        "interaction",
        "event",
        "save",
        "close",
        "reopen",
        "assertions",
    ]
    status: Literal["PASSED"] = "PASSED"
    evidence: ArtifactRef


class MutationCase(StrictModel):
    """One required source-derived mutant detected by behavioral evidence."""

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,99}$")
    category: Literal[
        "keyboard",
        "boundary",
        "rotation",
        "timer",
        "control-event",
        "persistence",
        "line-collapse",
        "scoring",
        "liberation",
    ]
    source_ref: str = Field(min_length=1, max_length=500)
    baseline_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    mutant_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    outcome: Literal["killed"] = "killed"
    trace: ArtifactRef
    evaluation: ArtifactRef

    @model_validator(mode="after")
    def mutation_changes_the_candidate(self) -> Self:
        if self.baseline_sha256 == self.mutant_sha256:
            raise ValueError("mutation must change the candidate identity")
        return self


class MutationEvidence(StrictModel):
    """A decisive campaign: every required mutant is killed."""

    status: Literal["PASSED"] = "PASSED"
    required_kill_rate: float = Field(default=1.0, ge=1.0, le=1.0)
    validator_sha256_before: str = Field(pattern=r"^[0-9a-f]{64}$")
    validator_sha256_after: str = Field(pattern=r"^[0-9a-f]{64}$")
    total: int = Field(ge=1)
    killed: int = Field(ge=1)
    survived: Literal[0] = 0
    inconclusive: Literal[0] = 0
    cases: tuple[MutationCase, ...] = Field(min_length=1)
    evidence: ArtifactRef

    @model_validator(mode="after")
    def campaign_is_complete_and_unchanged(self) -> Self:
        if self.validator_sha256_before != self.validator_sha256_after:
            raise ValueError("showcase validator changed during the migration")
        if self.total != len(self.cases) or self.killed != self.total:
            raise ValueError("every declared showcase mutation must be killed")
        if len({case.id for case in self.cases}) != len(self.cases):
            raise ValueError("mutation case IDs must be unique")
        traces = {case.trace.path for case in self.cases}
        if len(traces) != len(self.cases):
            raise ValueError("each mutation requires its own runtime trace")
        return self


class LiberationEvidence(StrictModel):
    """Direct proof that no proprietary execution architecture remains."""

    status: Literal["PASSED"] = "PASSED"
    no_vba_project: Literal["PASS"] = "PASS"
    no_basic_event_bindings: Literal["PASS"] = "PASS"
    no_com_office_automation: Literal["PASS"] = "PASS"
    no_windows_dll_dependency: Literal["PASS"] = "PASS"
    no_excel_runtime: Literal["PASS"] = "PASS"
    no_unresolved_proprietary_addin: Literal["PASS"] = "PASS"
    scanned_target_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence: ArtifactRef


class HiddenReviewSummary(StrictModel):
    """Privacy-safe hidden result; definitions can never enter the bundle."""

    status: Literal["PASSED"] = "PASSED"
    executed: int = Field(ge=1)
    passed: int = Field(ge=1)
    failed: Literal[0] = 0
    hidden_definitions_included: Literal[False] = False
    evidence: ArtifactRef

    @model_validator(mode="after")
    def counts_are_consistent(self) -> Self:
        if self.passed != self.executed:
            raise ValueError("all executed hidden reviewer tests must pass")
        return self


class ReviewerEvidence(StrictModel):
    """Fresh-context approval bound to the complete reviewed input set."""

    state: Literal["APPROVE"] = "APPROVE"
    reviewer_thread_id: str = Field(min_length=1, max_length=200)
    lead_thread_id: str = Field(min_length=1, max_length=200)
    reviewer_model_id: str = Field(min_length=1, max_length=200)
    independent_context: Literal[True] = True
    reviewed_target_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    reviewed_inputs_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    mandatory_checks: Literal["PASS"] = "PASS"
    blocking_findings: Literal[0] = 0
    hidden: HiddenReviewSummary
    evidence: ArtifactRef

    @model_validator(mode="after")
    def reviewer_has_a_fresh_thread(self) -> Self:
        if self.reviewer_thread_id == self.lead_thread_id:
            raise ValueError("independent reviewer must use a fresh thread")
        return self


class ReplayEvidence(StrictModel):
    """Recorded, replayable, privacy-safe evidence for every public scenario."""

    privacy: Literal["public-sanitized"] = "public-sanitized"
    replayable: Literal[True] = True
    covered_scenarios: tuple[str, ...] = Field(min_length=5, max_length=5)
    target_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    recording: ArtifactRef
    entrypoint: ArtifactRef
    event_log: ArtifactRef
    verification_status: Literal["PASSED"] = "PASSED"
    source_included: Literal[False] = False
    hidden_data_included: Literal[False] = False
    credentials_included: Literal[False] = False
    internal_paths_included: Literal[False] = False

    @model_validator(mode="after")
    def every_public_scenario_is_replayable(self) -> Self:
        if set(self.covered_scenarios) != PUBLIC_SCENARIOS:
            raise ValueError("replay must cover every canonical public scenario exactly once")
        if len(set(self.covered_scenarios)) != len(self.covered_scenarios):
            raise ValueError("replay scenario IDs must be unique")
        if not self.recording.path.endswith((".webm", ".mp4")):
            raise ValueError("showcase recording must be WebM or MP4")
        if not self.entrypoint.path.endswith(".html"):
            raise ValueError("showcase replay entrypoint must be HTML")
        return self


class ModelUsage(StrictModel):
    """Versioned model use and attributable cost for one episode role."""

    role: str = Field(min_length=1, max_length=100)
    provider: str = Field(min_length=1, max_length=100)
    model_id: str = Field(min_length=1, max_length=200)
    model_version: str = Field(min_length=1, max_length=200)
    calls: int = Field(ge=1)
    cost_usd: float = Field(ge=0.0)


class Limitation(StrictModel):
    """Remaining limitation disclosed without permitting a blocking result."""

    summary: str = Field(min_length=1, max_length=1000)
    blocking: Literal[False] = False


class OperationsEvidence(StrictModel):
    """Commands, service versions, model use, cost, and wall runtime."""

    commands_documented: Literal[True] = True
    service_versions_documented: Literal[True] = True
    started_at: datetime
    ended_at: datetime
    runtime_seconds: float = Field(gt=0.0)
    manual_interventions: Literal[0] = 0
    models: tuple[ModelUsage, ...] = Field(min_length=1)
    aggregate_cost_usd: float = Field(ge=0.0)
    limitations_documented: Literal[True] = True
    limitations: tuple[Limitation, ...] = ()
    evidence: ArtifactRef

    @model_validator(mode="after")
    def totals_and_runtime_are_consistent(self) -> Self:
        if self.started_at.tzinfo is None or self.ended_at.tzinfo is None:
            raise ValueError("showcase runtime timestamps must include a timezone")
        elapsed = (self.ended_at - self.started_at).total_seconds()
        if elapsed <= 0 or not math.isclose(elapsed, self.runtime_seconds, abs_tol=0.001):
            raise ValueError("showcase runtime does not match its timestamps")
        cost = sum(model.cost_usd for model in self.models)
        if not math.isclose(cost, self.aggregate_cost_usd, abs_tol=1e-9):
            raise ValueError("aggregate showcase cost does not match model costs")
        if len({model.role for model in self.models}) != len(self.models):
            raise ValueError("showcase model roles must be unique")
        return self


class ShowcaseBundleManifest(StrictModel):
    """Complete first-showcase release contract; partial evidence cannot validate."""

    schema_version: Literal["1.0.0"] = "1.0.0"
    showcase_id: Literal["interactive-game"] = "interactive-game"
    migration_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{1,127}$")
    status: Literal["PASSED"] = "PASSED"
    release_ready: Literal[True] = True
    privacy: Literal["public-sanitized"] = "public-sanitized"
    lead_thread_id: str = Field(min_length=1, max_length=200)
    source: SourceIdentity
    target: TargetIdentity
    invocation: InvocationEvidence
    specialists: tuple[SpecialistTrajectory, ...]
    scenarios: tuple[ScenarioEvidence, ...] = Field(min_length=5, max_length=5)
    lifecycle: tuple[LifecycleOperation, ...] = Field(min_length=8)
    mutation: MutationEvidence
    liberation: LiberationEvidence
    review_inputs: ArtifactRef
    reviewer: ReviewerEvidence
    replay: ReplayEvidence
    operations: OperationsEvidence
    artifact_index: tuple[IndexedArtifact, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def all_showcase_gates_are_bound(self) -> Self:
        self._validate_specialists()
        self._validate_scenarios_and_lifecycle()
        self._validate_cross_references()
        self._validate_models()
        self._validate_artifact_index()
        return self

    def _validate_specialists(self) -> None:
        roles = {specialist.role for specialist in self.specialists}
        if len(roles) != len(self.specialists):
            raise ValueError("showcase specialist roles must be unique")
        if not BASE_SPECIALIST_ROLES.issubset(roles):
            raise ValueError("showcase is missing a required specialist role")
        if not roles.intersection(UI_DEPENDENCY_ROLES):
            raise ValueError("showcase requires a UI or dependency specialist")
        threads = {specialist.thread_id for specialist in self.specialists}
        if len(threads) != len(self.specialists) or self.lead_thread_id in threads:
            raise ValueError("specialists require unique threads separate from the lead")
        if self.reviewer.reviewer_thread_id in threads:
            raise ValueError("reviewer thread must be separate from every specialist")

    def _validate_scenarios_and_lifecycle(self) -> None:
        scenario_ids = [scenario.scenario_id for scenario in self.scenarios]
        if set(scenario_ids) != PUBLIC_SCENARIOS or len(set(scenario_ids)) != len(scenario_ids):
            raise ValueError("showcase requires each canonical public scenario exactly once")
        sequences = [operation.sequence for operation in self.lifecycle]
        if sequences != list(range(1, len(self.lifecycle) + 1)):
            raise ValueError("showcase lifecycle operations must be consecutively ordered")
        cursor = 0
        for operation in self.lifecycle:
            if operation.kind == LIFECYCLE[cursor]:
                cursor += 1
                if cursor == len(LIFECYCLE):
                    break
        if cursor != len(LIFECYCLE):
            raise ValueError("showcase lifecycle is incomplete or out of order")

    def _validate_cross_references(self) -> None:
        target_sha256 = self.target.artifact.sha256
        if self.invocation.thread_id != self.lead_thread_id:
            raise ValueError("public invocation must identify the lead thread")
        if self.reviewer.lead_thread_id != self.lead_thread_id:
            raise ValueError("reviewer result is bound to a different lead thread")
        if self.reviewer.reviewed_target_sha256 != target_sha256:
            raise ValueError("reviewer result is stale for the target")
        if self.reviewer.reviewed_inputs_sha256 != self.review_inputs.sha256:
            raise ValueError("reviewer result is stale for the complete review inputs")
        if self.liberation.scanned_target_sha256 != target_sha256:
            raise ValueError("liberation evidence is stale for the target")
        if self.replay.target_sha256 != target_sha256:
            raise ValueError("replay evidence is stale for the target")

    def _validate_models(self) -> None:
        expected = {
            "lead",
            "independent-reviewer",
            *(specialist.role for specialist in self.specialists),
        }
        actual = {model.role for model in self.operations.models}
        if not expected.issubset(actual):
            raise ValueError(f"missing model/cost records for roles: {sorted(expected - actual)}")
        reviewer_usage = next(
            model for model in self.operations.models if model.role == "independent-reviewer"
        )
        if reviewer_usage.model_id != self.reviewer.reviewer_model_id:
            raise ValueError("reviewer model record does not match reviewer evidence")
        specialist_models = {
            specialist.role: specialist.model_id for specialist in self.specialists
        }
        for usage in self.operations.models:
            expected_model = specialist_models.get(usage.role)
            if expected_model is not None and usage.model_id != expected_model:
                raise ValueError(f"model record does not match {usage.role} trajectory")

    def _validate_artifact_index(self) -> None:
        indexed = {artifact.path: artifact for artifact in self.artifact_index}
        if len(indexed) != len(self.artifact_index):
            raise ValueError("artifact index paths must be unique")
        referenced = {reference.path: reference for reference in self.artifact_references()}
        if set(indexed) != set(referenced):
            raise ValueError("artifact index must exactly cover every referenced bundle file")
        for path, reference in referenced.items():
            if indexed[path].sha256 != reference.sha256:
                raise ValueError(f"artifact index hash disagrees with reference: {path}")

    def artifact_references(self) -> tuple[ArtifactRef, ...]:
        """Return every content-bound file referenced by the manifest."""
        references: list[ArtifactRef] = [
            self.source.dossier,
            self.target.artifact,
            self.invocation.evidence,
            *(specialist.evidence for specialist in self.specialists),
            *(scenario.evidence for scenario in self.scenarios),
            *(operation.evidence for operation in self.lifecycle),
            self.mutation.evidence,
            *(
                reference
                for case in self.mutation.cases
                for reference in (case.trace, case.evaluation)
            ),
            self.liberation.evidence,
            self.review_inputs,
            self.reviewer.hidden.evidence,
            self.reviewer.evidence,
            self.replay.recording,
            self.replay.entrypoint,
            self.replay.event_log,
            self.operations.evidence,
        ]
        by_path: dict[str, ArtifactRef] = {}
        for reference in references:
            existing = by_path.get(reference.path)
            if existing is not None and existing.sha256 != reference.sha256:
                raise ValueError(f"conflicting hashes for referenced artifact: {reference.path}")
            by_path[reference.path] = reference
        return tuple(by_path.values())


def inspect_showcase_bundle(directory: Path) -> ShowcaseBundleManifest:
    """Validate a complete public showcase bundle without executing any runtime."""
    root = directory.resolve()
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise ValueError("showcase manifest is absent or unsafe")
    manifest = ShowcaseBundleManifest.model_validate(
        json.loads(manifest_path.read_text(encoding="utf-8"))
    )
    indexed_paths = {artifact.path for artifact in manifest.artifact_index}
    actual_paths: set[str] = set()
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"showcase bundle contains a symlink: {path.relative_to(root)}")
        if path.is_file() and path != manifest_path:
            actual_paths.add(path.relative_to(root).as_posix())
    if actual_paths != indexed_paths:
        raise ValueError("showcase artifact index does not match the bundle contents")
    for artifact in manifest.artifact_index:
        path = _confined_file(root, artifact.path)
        payload = path.read_bytes()
        if len(payload) != artifact.bytes:
            raise ValueError(f"showcase artifact byte count mismatch: {artifact.path}")
        if hashlib.sha256(payload).hexdigest() != artifact.sha256:
            raise ValueError(f"showcase artifact hash mismatch: {artifact.path}")
    return manifest


def inspect_showcase_archive(archive_path: Path) -> ShowcaseBundleManifest:
    """Safely extract and validate a public showcase archive."""
    if archive_path.is_symlink():
        raise ValueError("showcase archive is absent or unsafe")
    archive = archive_path.resolve()
    if not archive.is_file():
        raise ValueError("showcase archive is absent or unsafe")
    try:
        with ZipFile(archive) as bundle:
            members = bundle.infolist()
            file_members = [member for member in members if not member.is_dir()]
            if not file_members or len(members) > MAX_ARCHIVE_FILES:
                raise ValueError("showcase archive file count is invalid")
            names: set[str] = set()
            total_bytes = 0
            for member in members:
                name = member.filename
                path = PurePosixPath(name)
                normalized = path.as_posix().rstrip("/")
                if (
                    not normalized
                    or path.is_absolute()
                    or ".." in path.parts
                    or "." in path.parts
                    or "\\" in name
                    or normalized != name.rstrip("/")
                    or len(normalized) > 500
                    or len(path.parts) > 20
                ):
                    raise ValueError(f"showcase archive path is unsafe: {name}")
                if normalized in names:
                    raise ValueError(f"showcase archive path is duplicated: {normalized}")
                names.add(normalized)
                mode = member.external_attr >> 16
                if stat.S_ISLNK(mode):
                    raise ValueError(f"showcase archive contains a symlink: {name}")
                if member.flag_bits & 0x1:
                    raise ValueError(f"showcase archive member is encrypted: {name}")
                if member.file_size > MAX_ARCHIVE_FILE_BYTES:
                    raise ValueError(f"showcase archive member is oversized: {name}")
                if not member.is_dir():
                    total_bytes += member.file_size
            if total_bytes > MAX_ARCHIVE_TOTAL_BYTES:
                raise ValueError("showcase archive expands beyond its size limit")

            with TemporaryDirectory(prefix="xlsliberator-showcase-") as temp:
                root = Path(temp)
                for member in file_members:
                    destination = root.joinpath(*PurePosixPath(member.filename).parts)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with bundle.open(member) as source, destination.open("wb") as output:
                        while chunk := source.read(1024 * 1024):
                            output.write(chunk)
                return inspect_showcase_bundle(root)
    except BadZipFile as exc:
        raise ValueError("showcase archive is not a valid ZIP file") from exc


def _confined_file(root: Path, reference: str) -> Path:
    _safe_artifact_path(reference)
    path = root.joinpath(*PurePosixPath(reference).parts)
    cursor = root
    for part in PurePosixPath(reference).parts:
        cursor /= part
        if cursor.is_symlink():
            raise ValueError(f"showcase artifact uses a symlink: {reference}")
    resolved = path.resolve()
    if not resolved.is_relative_to(root) or not path.is_file():
        raise ValueError(f"showcase artifact is missing or escapes the bundle: {reference}")
    return resolved


def main(argv: list[str] | None = None) -> int:
    """Validate a showcase directory or archive from a Docker-contained CLI."""
    parser = argparse.ArgumentParser(description="Validate an XLSLiberator showcase bundle")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--directory", type=Path)
    source.add_argument("--archive", type=Path)
    arguments = parser.parse_args(argv)
    manifest = (
        inspect_showcase_archive(arguments.archive)
        if arguments.archive is not None
        else inspect_showcase_bundle(arguments.directory)
    )
    print(
        json.dumps(
            {
                "showcase_id": manifest.showcase_id,
                "migration_id": manifest.migration_id,
                "status": manifest.status,
                "release_ready": manifest.release_ready,
                "target_build": manifest.target.full_build,
                "reviewer_state": manifest.reviewer.state,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
