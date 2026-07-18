from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest

from agent.xlsliberator.sandbox_identity import (
    capture_sandbox_identity,
    local_unavailable_identity,
    parse_identity_output,
)


def _identity() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "PASSED",
        "image": {
            "name": "registry.example/sandbox:v1",
            "version": "v1",
            "open_swe_commit": "a" * 40,
            "xlsliberator_commit": "b" * 40,
            "libreoffice_build": "26.2.4.2",
        },
        "runtime": {"image_digest": "sha256:abc", "snapshot_id": "snapshot-1"},
    }


def test_parse_identity_accepts_complete_passed_payload() -> None:
    identity = _identity()

    assert parse_identity_output(json.dumps(identity)) == identity


@pytest.mark.parametrize(
    "output",
    [
        None,
        "",
        "not-json",
        "[]",
        '{"status":"FAILED","image":{}}',
        '{"status":"PASSED","image":{"name":"incomplete"}}',
    ],
)
def test_parse_identity_rejects_non_evidence(output: object) -> None:
    assert parse_identity_output(output) is None


async def test_capture_identity_uses_only_identity_command() -> None:
    identity = _identity()

    class Backend:
        id = "sandbox-1"

        def execute(self, command: str) -> SimpleNamespace:
            assert command == "xlsliberator-sandbox-identity"
            return SimpleNamespace(output=json.dumps(identity))

    assert await capture_sandbox_identity(Backend()) == identity  # type: ignore[arg-type]


def test_local_provider_is_explicitly_unavailable() -> None:
    payload = local_unavailable_identity("local")

    assert payload["status"] == "UNAVAILABLE"
    assert payload["sandbox_id"] == "local"
    assert payload["snapshot_id"] is None
