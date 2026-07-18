"""Run the trusted nightly workbook benchmark and validate aggregate observations."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import httpx

from agent.xlsliberator.evaluation import (
    BenchmarkReport,
    MigrationEvaluationInput,
    aggregate_benchmark,
    evaluate_migration,
)

DEFAULT_CONFIG_PATH = Path(__file__).with_name("approved-configurations.json")


def _load_approved(path: Path) -> list[dict[str, str]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "1.0.0":
        raise ValueError("unsupported approved-configuration schema")
    configurations = payload.get("configurations")
    if not isinstance(configurations, list) or not configurations:
        raise ValueError("at least one approved configuration is required")
    ids: set[str] = set()
    normalized: list[dict[str, str]] = []
    for raw in configurations:
        if not isinstance(raw, dict):
            raise ValueError("approved configurations must be objects")
        item = {str(key): str(value) for key, value in raw.items()}
        identifier = item.get("id", "")
        if not identifier or identifier in ids:
            raise ValueError("approved configuration ids must be non-empty and unique")
        ids.add(identifier)
        normalized.append(item)
    return normalized


def _load_observations(payload: object) -> list[MigrationEvaluationInput]:
    if not isinstance(payload, dict) or payload.get("schema_version") != "1.0.0":
        raise ValueError("unsupported benchmark observation schema")
    raw_observations = payload.get("observations")
    if not isinstance(raw_observations, list):
        raise ValueError("benchmark response must contain observations")
    return [
        MigrationEvaluationInput.model_validate(observation) for observation in raw_observations
    ]


def _request_observations(
    endpoint: str,
    token: str,
    configurations: list[dict[str, str]],
    *,
    timeout_seconds: float,
) -> list[MigrationEvaluationInput]:
    request = {
        "schema_version": "1.0.0",
        "dataset": "xlsliberator-public-nightly-v1",
        "target": "libreoffice",
        "target_libreoffice_build": "26.2.4.2",
        "approved_configurations": configurations,
        "return_hidden_definitions": False,
        "return_hidden_aggregate_only": True,
    }
    with httpx.Client(timeout=timeout_seconds) as client:
        response = client.post(
            endpoint,
            headers={"Authorization": f"Bearer {token}"},
            json=request,
        )
        response.raise_for_status()
        return _load_observations(response.json())


def run_benchmark(
    observations: list[MigrationEvaluationInput],
    approved: list[dict[str, str]],
) -> BenchmarkReport:
    """Evaluate only observations from the exact approved configuration set."""
    approved_ids = {configuration["id"] for configuration in approved}
    observed_ids = {observation.team_configuration for observation in observations}
    unapproved = observed_ids - approved_ids
    missing = approved_ids - observed_ids
    if unapproved:
        raise ValueError(f"benchmark returned unapproved configurations: {sorted(unapproved)}")
    if missing:
        raise ValueError(f"benchmark omitted approved configurations: {sorted(missing)}")
    if any(observation.hidden_definitions_included for observation in observations):
        raise ValueError("benchmark response exposed hidden definitions")
    return aggregate_benchmark([evaluate_migration(observation) for observation in observations])


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--approved", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--observations", type=Path)
    parser.add_argument("--endpoint", default=os.environ.get("XLSLIBERATOR_BENCHMARK_ENDPOINT"))
    parser.add_argument("--token", default=os.environ.get("XLSLIBERATOR_BENCHMARK_TOKEN"))
    parser.add_argument("--timeout-seconds", type=float, default=21_600)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check-release", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    approved = _load_approved(args.approved)
    if args.observations is not None:
        observations = _load_observations(json.loads(args.observations.read_text(encoding="utf-8")))
    else:
        if not args.endpoint or not args.token:
            raise SystemExit(
                "benchmark endpoint and token are required when --observations is absent"
            )
        observations = _request_observations(
            args.endpoint,
            args.token,
            approved,
            timeout_seconds=args.timeout_seconds,
        )
    report = run_benchmark(observations, approved)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        report.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    if args.check_release and any(not case.release_ready for case in report.cases):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
