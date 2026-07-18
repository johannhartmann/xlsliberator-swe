"""Truthful sandbox-image identity capture for migration threads."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

from deepagents.backends.protocol import SandboxBackendProtocol

logger = logging.getLogger(__name__)

IDENTITY_COMMAND = "xlsliberator-sandbox-identity"


def parse_identity_output(output: object) -> dict[str, Any] | None:
    """Parse the bounded identity object emitted by the sandbox image."""

    if not isinstance(output, str):
        return None
    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    image = payload.get("image")
    if payload.get("status") != "PASSED" or not isinstance(image, dict):
        return None
    required = {
        "name",
        "version",
        "open_swe_commit",
        "xlsliberator_commit",
        "libreoffice_build",
    }
    if not required.issubset(image) or not all(
        isinstance(image[key], str) for key in required
    ):
        return None
    return payload


def local_unavailable_identity(sandbox_id: str) -> dict[str, Any]:
    """Return an explicit non-success identity for the unisolated local provider."""

    return {
        "status": "UNAVAILABLE",
        "reason": "SANDBOX_TYPE=local is not isolated and is forbidden for workbook migration",
        "sandbox_id": sandbox_id,
        "snapshot_id": None,
    }


async def capture_sandbox_identity(
    sandbox_backend: SandboxBackendProtocol,
) -> dict[str, Any] | None:
    """Read image identity without invoking Python, UNO, or LibreOffice."""

    response = await asyncio.to_thread(sandbox_backend.execute, IDENTITY_COMMAND)
    return parse_identity_output(getattr(response, "output", None))


async def record_sandbox_identity(
    thread_id: str,
    sandbox_backend: SandboxBackendProtocol,
    *,
    thread_client: Any,
) -> None:
    """Persist an image/snapshot tuple in thread metadata on every agent run."""

    if os.getenv("SANDBOX_TYPE", "langsmith") == "local":
        logger.warning("Skipping image identity for unisolated local sandbox %s", sandbox_backend.id)
        return
    try:
        payload = await capture_sandbox_identity(sandbox_backend)
    except Exception:
        logger.exception("Failed to capture sandbox image identity for thread %s", thread_id)
        return
    if payload is None:
        logger.warning("Sandbox %s did not provide a valid image identity", sandbox_backend.id)
        return

    payload["sandbox_id"] = sandbox_backend.id
    payload["snapshot_id"] = os.getenv("DEFAULT_SANDBOX_SNAPSHOT_ID") or None
    try:
        await thread_client.threads.update(
            thread_id=thread_id,
            metadata={"xlsliberator_sandbox_identity": payload},
        )
    except Exception:
        logger.exception("Failed to persist sandbox image identity for thread %s", thread_id)
