"""Server-owned capability and sandbox evidence for hostile workbook migrations."""

from __future__ import annotations

import json
import os
from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

CAPABILITY_GRANTS_ENV = "XLSLIBERATOR_CAPABILITY_GRANTS_JSON"
SECURITY_EVIDENCE_PATH = "thread-metadata/xlsliberator_security"


class CapabilityName(StrEnum):
    MAIL = "mail"
    DATABASE = "database"
    HTTP = "http"
    FILESYSTEM_EXPORT = "filesystem-export"
    BUILD_FARM = "build-farm"


class SecurityThreat(StrEnum):
    HOST_FILE_ACCESS = "host-file-access"
    PATH_OR_SYMLINK_ESCAPE = "path-or-symlink-escape"
    NETWORK_OR_CREDENTIAL_EXFILTRATION = "network-or-credential-exfiltration"
    PROCESS_PERSISTENCE = "process-persistence"
    RESOURCE_EXHAUSTION = "resource-exhaustion"
    ARCHIVE_BOMB = "archive-bomb"
    MALFORMED_XML_OR_OLE = "malformed-xml-or-ole"
    MACRO_INFINITE_LOOP = "macro-infinite-loop"
    PROMPT_INJECTION = "prompt-injection"
    UNAUTHORIZED_MCP = "unauthorized-mcp"
    HIDDEN_TEST_LEAKAGE = "hidden-test-leakage"
    CROSS_JOB_ACCESS = "cross-job-access"


SecurityRole = Literal[
    "lead",
    "dependency-liberation-engineer",
    "libreoffice-engineer",
    "security-adversary",
]

_ALLOWED_ROLES: dict[CapabilityName, frozenset[SecurityRole]] = {
    CapabilityName.MAIL: frozenset({"lead", "dependency-liberation-engineer"}),
    CapabilityName.DATABASE: frozenset({"lead", "dependency-liberation-engineer"}),
    CapabilityName.HTTP: frozenset({"lead", "dependency-liberation-engineer"}),
    CapabilityName.FILESYSTEM_EXPORT: frozenset({"lead", "dependency-liberation-engineer"}),
    CapabilityName.BUILD_FARM: frozenset({"libreoffice-engineer"}),
}


class CapabilityConfigurationError(ValueError):
    """Deployment capability policy is malformed and therefore unusable."""


class SecureCapabilityGrant(BaseModel):
    """Credential-free reference to authority issued by trusted server policy."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0.0"] = "1.0.0"
    grant_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{0,127}$")
    capability: CapabilityName
    resource_ref: str = Field(pattern=r"^[a-z0-9][a-z0-9._/-]{0,255}$")
    roles: tuple[SecurityRole, ...] = Field(min_length=1)
    issued_by: Literal["server-policy"] = "server-policy"

    @model_validator(mode="after")
    def grant_is_opaque_and_role_bounded(self) -> Self:
        if ".." in self.resource_ref.split("/"):
            raise ValueError("capability resource reference cannot traverse")
        if "://" in self.resource_ref or "@" in self.resource_ref:
            raise ValueError("capability grants must not contain endpoints or credentials")
        allowed = _ALLOWED_ROLES[self.capability]
        if not set(self.roles).issubset(allowed):
            raise ValueError(f"{self.capability.value} grant contains an unauthorized role")
        return self


class CapabilityDecision(BaseModel):
    """Evidence-safe authorization result for one task and role."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0.0"] = "1.0.0"
    status: Literal["AVAILABLE", "UNAVAILABLE"]
    role: SecurityRole
    required: tuple[CapabilityName, ...]
    grants: tuple[SecureCapabilityGrant, ...]
    missing: tuple[CapabilityName, ...]
    evidence_path: Literal["thread-metadata/xlsliberator_security"] = SECURITY_EVIDENCE_PATH
    credentials_included: Literal[False] = False

    @model_validator(mode="after")
    def status_matches_missing_capabilities(self) -> Self:
        expected = "UNAVAILABLE" if self.missing else "AVAILABLE"
        if self.status != expected:
            raise ValueError(f"capability decision status must be {expected}")
        return self


class SecurityProbe(BaseModel):
    """One safe hostile-workbook probe with durable evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    threat: SecurityThreat
    status: Literal["BLOCKED", "ESCAPED", "UNAVAILABLE"]
    evidence_path: str = Field(pattern=r"^migration/evidence/security/[a-z0-9][a-z0-9._/-]{0,255}$")
    detail: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def evidence_cannot_escape_security_root(self) -> Self:
        if ".." in self.evidence_path.split("/"):
            raise ValueError("security evidence path cannot traverse")
        return self


class SecurityAdversaryEvaluation(BaseModel):
    """Fail-closed aggregate covering the complete hostile-workbook threat set."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0.0"] = "1.0.0"
    evaluator: Literal["security-adversary"] = "security-adversary"
    target_libreoffice_build: Literal["26.2.4.2"] = "26.2.4.2"
    probes: tuple[SecurityProbe, ...] = Field(min_length=12, max_length=12)
    verdict: Literal["PASS", "FAIL", "UNAVAILABLE"]
    workbook_data_delimited: Literal[True] = True
    hidden_definitions_included: Literal[False] = False

    @model_validator(mode="after")
    def verdict_matches_complete_probe_set(self) -> Self:
        expected = set(SecurityThreat)
        actual = {probe.threat for probe in self.probes}
        if actual != expected or len(actual) != len(self.probes):
            raise ValueError("security evaluation requires every threat exactly once")
        statuses = {probe.status for probe in self.probes}
        required = (
            "FAIL"
            if "ESCAPED" in statuses
            else "UNAVAILABLE"
            if "UNAVAILABLE" in statuses
            else "PASS"
        )
        if self.verdict != required:
            raise ValueError(f"security verdict must be {required}")
        return self


def evaluate_security_probes(
    probes: list[SecurityProbe] | tuple[SecurityProbe, ...],
) -> SecurityAdversaryEvaluation:
    """Derive a truthful result; missing or unavailable probes cannot pass."""
    statuses = {probe.status for probe in probes}
    verdict: Literal["PASS", "FAIL", "UNAVAILABLE"]
    if "ESCAPED" in statuses:
        verdict = "FAIL"
    elif "UNAVAILABLE" in statuses:
        verdict = "UNAVAILABLE"
    else:
        verdict = "PASS"
    return SecurityAdversaryEvaluation(probes=tuple(probes), verdict=verdict)


def load_server_capability_grants(raw: str | None = None) -> tuple[SecureCapabilityGrant, ...]:
    """Load credential-free grants from deployment policy, never workbook content."""
    encoded = os.environ.get(CAPABILITY_GRANTS_ENV, "[]") if raw is None else raw
    try:
        payload = json.loads(encoded)
    except json.JSONDecodeError as exc:
        raise CapabilityConfigurationError("capability grant policy is invalid JSON") from exc
    if not isinstance(payload, list):
        raise CapabilityConfigurationError("capability grant policy must be a list")
    try:
        grants = tuple(SecureCapabilityGrant.model_validate(item) for item in payload)
    except (TypeError, ValueError) as exc:
        raise CapabilityConfigurationError("capability grant policy is malformed") from exc
    if len({grant.grant_id for grant in grants}) != len(grants):
        raise CapabilityConfigurationError("capability grant identifiers must be unique")
    return grants


def authorize_capabilities(
    required: list[CapabilityName] | tuple[CapabilityName, ...],
    *,
    role: SecurityRole,
    grants: tuple[SecureCapabilityGrant, ...] | None = None,
) -> CapabilityDecision:
    """Resolve requested capabilities through trusted grants and role policy."""
    required_ordered = tuple(dict.fromkeys(required))
    configured = load_server_capability_grants() if grants is None else grants
    matched = tuple(
        grant
        for grant in configured
        if grant.capability in required_ordered and role in grant.roles
    )
    granted_names = {grant.capability for grant in matched}
    missing = tuple(
        capability for capability in required_ordered if capability not in granted_names
    )
    return CapabilityDecision(
        status="UNAVAILABLE" if missing else "AVAILABLE",
        role=role,
        required=required_ordered,
        grants=matched,
        missing=missing,
    )


def safe_sandbox_environment(source: dict[str, str]) -> dict[str, str]:
    """Remove provider, GitHub, service, and user credentials from job environments."""
    allowed = {"LANG", "LC_ALL", "TZ"}
    clean = {name: value for name, value in source.items() if name in allowed}
    clean.update(
        {
            "HOME": "/home/sandbox",
            "TMPDIR": "/tmp",  # nosec B108 - isolated container tmpfs, not a host temp path
            "XLSLIBERATOR_UNTRUSTED_WORKBOOK": "1",
        }
    )
    return clean
