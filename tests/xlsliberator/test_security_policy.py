"""Fail-closed capability and hostile-workbook security policy tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from agent.xlsliberator.security import (
    CapabilityConfigurationError,
    CapabilityName,
    SecureCapabilityGrant,
    SecurityAdversaryEvaluation,
    SecurityProbe,
    SecurityThreat,
    authorize_capabilities,
    evaluate_security_probes,
    load_server_capability_grants,
    safe_sandbox_environment,
)


def _grant(
    capability: CapabilityName,
    *,
    role: str = "lead",
) -> SecureCapabilityGrant:
    return SecureCapabilityGrant.model_validate(
        {
            "grant_id": f"grant-{capability.value}",
            "capability": capability,
            "resource_ref": f"adapters/{capability.value}/tenant-1",
            "roles": [role],
        }
    )


def _probe(
    threat: SecurityThreat,
    status: str = "BLOCKED",
) -> SecurityProbe:
    return SecurityProbe.model_validate(
        {
            "threat": threat,
            "status": status,
            "evidence_path": f"migration/evidence/security/{threat.value}.json",
            "detail": "the disposable sandbox blocked the attack",
        }
    )


def test_no_required_capabilities_is_available_without_grants() -> None:
    decision = authorize_capabilities([], role="lead", grants=())

    assert decision.status == "AVAILABLE"
    assert decision.grants == ()
    assert decision.credentials_included is False


def test_missing_capability_is_unavailable_and_recorded() -> None:
    decision = authorize_capabilities(
        [CapabilityName.HTTP, CapabilityName.DATABASE],
        role="lead",
        grants=(_grant(CapabilityName.HTTP),),
    )

    assert decision.status == "UNAVAILABLE"
    assert decision.missing == (CapabilityName.DATABASE,)
    assert decision.evidence_path == "thread-metadata/xlsliberator_security"


@pytest.mark.parametrize(
    "capability",
    [
        CapabilityName.MAIL,
        CapabilityName.DATABASE,
        CapabilityName.HTTP,
        CapabilityName.FILESYSTEM_EXPORT,
    ],
)
def test_adapter_capabilities_are_explicit_opaque_server_grants(
    capability: CapabilityName,
) -> None:
    decision = authorize_capabilities(
        [capability],
        role="dependency-liberation-engineer",
        grants=(_grant(capability, role="dependency-liberation-engineer"),),
    )

    assert decision.status == "AVAILABLE"
    assert decision.grants[0].resource_ref.startswith("adapters/")
    assert "://" not in decision.grants[0].resource_ref


def test_build_farm_grant_is_restricted_to_libreoffice_engineer() -> None:
    with pytest.raises(ValidationError, match="unauthorized role"):
        _grant(CapabilityName.BUILD_FARM)

    grant = _grant(CapabilityName.BUILD_FARM, role="libreoffice-engineer")
    assert (
        authorize_capabilities(
            [CapabilityName.BUILD_FARM],
            role="libreoffice-engineer",
            grants=(grant,),
        ).status
        == "AVAILABLE"
    )


@pytest.mark.parametrize(
    "resource_ref",
    [
        "../secrets",
        "https://user:password@example.test",
        "user@example.test",
    ],
)
def test_grants_reject_traversal_endpoints_and_credentials(resource_ref: str) -> None:
    with pytest.raises(ValidationError):
        SecureCapabilityGrant(
            grant_id="bad",
            capability=CapabilityName.HTTP,
            resource_ref=resource_ref,
            roles=("lead",),
        )


def test_malformed_deployment_policy_fails_closed() -> None:
    with pytest.raises(CapabilityConfigurationError):
        load_server_capability_grants("{not-json")
    with pytest.raises(CapabilityConfigurationError):
        load_server_capability_grants("{}")
    with pytest.raises(CapabilityConfigurationError):
        load_server_capability_grants(
            json.dumps(
                [
                    {
                        "grant_id": "duplicate",
                        "capability": "http",
                        "resource_ref": "adapters/http/one",
                        "roles": ["lead"],
                    },
                    {
                        "grant_id": "duplicate",
                        "capability": "http",
                        "resource_ref": "adapters/http/two",
                        "roles": ["lead"],
                    },
                ]
            )
        )


def test_sandbox_environment_drops_provider_service_and_github_secrets() -> None:
    clean = safe_sandbox_environment(
        {
            "LANG": "C.UTF-8",
            "TZ": "UTC",
            "OPENAI_API_KEY": "provider-secret",
            "ANTHROPIC_API_KEY": "provider-secret",
            "GITHUB_TOKEN": "github-secret",
            "XLSLIBERATOR_LIBREOFFICE_MCP_TOKEN": "service-secret",
            "XLSLIBERATOR_CAPABILITY_GRANTS_JSON": "server-policy-secret",
        }
    )

    assert clean == {
        "LANG": "C.UTF-8",
        "TZ": "UTC",
        "HOME": "/home/sandbox",
        "TMPDIR": "/tmp",
        "XLSLIBERATOR_UNTRUSTED_WORKBOOK": "1",
    }


def test_sandbox_image_reuses_preexisting_numeric_uid_and_gid() -> None:
    dockerfile = (Path(__file__).parents[2] / "docker/xlsliberator-sandbox/Dockerfile").read_text(
        encoding="utf-8"
    )

    assert "if ! getent group 10001" in dockerfile
    assert "if ! getent passwd 10001" in dockerfile
    assert "getent group sandbox" not in dockerfile
    assert "getent passwd sandbox" not in dockerfile


def test_sandbox_image_pins_firewall_binary_without_runtime_bootstrap() -> None:
    dockerfile = (Path(__file__).parents[2] / "docker/xlsliberator-sandbox/Dockerfile").read_text(
        encoding="utf-8"
    )

    assert "ARG SFW_BINARY_VERSION=1.13.1" in dockerfile
    assert "sfw-free/releases/download/v${SFW_BINARY_VERSION}" in dockerfile
    assert "4dc46b626a7c5b81c0b54e1984ee53be5a628dbfb2f55ab14e9b04c8a134db6a" in dockerfile
    assert "f87bbbca2192fca9740f9bdb115e7cfaa22e957a8f5234d5f97fce1383aa1d66" in dockerfile
    assert "install -m 0755" in dockerfile
    assert "/usr/local/bin/sfw" in dockerfile
    assert 'npm install --global "sfw@' not in dockerfile
    assert ".sfw-cache/latest" not in dockerfile


def test_showcase_services_share_a_private_numeric_identity_and_fail_closed() -> None:
    root = Path(__file__).parents[2]
    workflow = (root / ".github/workflows/xlsliberator_showcase.yml").read_text(encoding="utf-8")
    server_image = (root / "docker/xlsliberator-server/Dockerfile").read_text(encoding="utf-8")

    assert "COPY --chown=10001:10001" in server_image
    assert "USER 10001:10001" in server_image
    assert "Preflight public workbook hydration in hostile sandbox" in workflow
    assert "--network none" in workflow
    assert "xlsprobe dossier /input/TetrisGameDemo.xlsb" in workflow
    assert 'http_status="$(' in workflow
    assert "hydration-diagnostic.json" in workflow
    assert "hydration-files.txt" in workflow
    assert 'sudo chown -R 10001:10001 "$bridge" "$runtime" "$hidden"' in workflow
    assert 'chmod 0700 "$bridge" "$runtime" "$hidden"' in workflow
    assert workflow.count("--env XLSLIBERATOR_MCP_TRUSTED_CONTAINER_PROXY=1") == 2
    assert workflow.count('--group-add "$(stat -c %g /var/run/docker.sock)"') == 2
    assert '("libreoffice-mcp", 8000), ("corpus-mcp", 8010)' in workflow
    assert "docker logs xlsliberator-showcase-runtime" in workflow
    assert "docker logs xlsliberator-showcase-corpus" in workflow


def test_security_adversary_requires_all_twelve_threats_and_derives_verdict() -> None:
    probes = [_probe(threat) for threat in SecurityThreat]

    passed = evaluate_security_probes(probes)

    assert passed.verdict == "PASS"
    assert len(passed.probes) == 12
    assert passed.hidden_definitions_included is False

    probes[0] = _probe(SecurityThreat.HOST_FILE_ACCESS, "UNAVAILABLE")
    assert evaluate_security_probes(probes).verdict == "UNAVAILABLE"
    probes[1] = _probe(SecurityThreat.PATH_OR_SYMLINK_ESCAPE, "ESCAPED")
    assert evaluate_security_probes(probes).verdict == "FAIL"

    with pytest.raises(ValidationError, match="at least 12"):
        SecurityAdversaryEvaluation(probes=tuple(probes[:-1]), verdict="PASS")


def test_duplicate_security_probe_cannot_satisfy_complete_evaluation() -> None:
    probes = [_probe(threat) for threat in SecurityThreat]
    probes[-1] = _probe(SecurityThreat.HOST_FILE_ACCESS)

    with pytest.raises(ValidationError, match="every threat exactly once"):
        evaluate_security_probes(probes)
