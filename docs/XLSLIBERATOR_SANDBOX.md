# XLSLiberator workbook-migration sandbox

The workbook-migration sandbox is a versioned derivative of XLSLiberator's
exact `xlsliberator-libreoffice:26.2.4.2` image. LibreOffice, its bundled Python,
PyUNO, and the Python script provider therefore remain inside Docker. Open SWE
must never discover or execute host Python, `uv`, UNO, LibreOffice, or
`soffice`.

## Pinned identity

`docker/xlsliberator-sandbox/versions.env` is the source of truth for:

- sandbox version and target image tag;
- the exact XLSLiberator source commit installed editable in the image;
- the exact LibreOffice full build;
- the exact office base-image tag.

The Dockerfile also pins the Open SWE toolchain's major release line and
download checksums. `/etc/xlsliberator-sandbox/versions.txt` records resolved
tool and Python-package versions. `/etc/xlsliberator-sandbox/identity.json`
records the two source commits and LibreOffice build. The entrypoint copies a
runtime-enriched identity to
`/workspace/.xlsliberator/sandbox-identity.json`; Open SWE persists the same
payload in thread metadata.

The image contains no provider, GitHub, LangSmith, or service credentials.
Workbook jobs do not inherit them. Trusted server-side services retain their
own credentials and expose only role-authorized, task-scoped MCP operations.

## Build

BuildKit and Docker are required. The default build context fetches the exact
public XLSLiberator commit, so a different or dirty adjacent checkout cannot
silently change the image:

```bash
scripts/build_xlsliberator_sandbox.sh
```

For a clean adjacent checkout at the pinned commit:

```bash
XLSLIBERATOR_BUILD_CONTEXT=../xlsliberator \
  scripts/build_xlsliberator_sandbox.sh
```

The build installs:

- Open SWE's locked requirements in `/opt/open-swe-venv`;
- uv-managed Python 3.11 and 3.12;
- XLSLiberator and its locked dev dependencies in
  `/opt/xlsliberator-venv`;
- LibreOffice 26.2.4.2, bundled Python 3.12, PyUNO, and the Python script
  provider from the office base;
- Xvfb, Chromium, ImageMagick, Java 17, Docker CLI, Git, GitHub CLI,
  ripgrep, jq, zip/unzip, Go, and Rust;
- openpyxl, oletools, pyxlsb, msoffcrypto-tool, pytest, Ruff, and mypy;
- `xlsliberator-build-farm-client`, a credential-free health client for an
  external build farm.

## Smoke test

Start the trusted XLSLiberator MCP orchestrator from the pinned XLSLiberator
checkout, then run the explicit CI health smoke on the host network:

```bash
docker compose -f ../xlsliberator/docker-compose.yml up -d --build xlsliberator-mcp
docker run --rm --network host \
  -e XLSLIBERATOR_LIBREOFFICE_MCP_ENDPOINT=http://127.0.0.1:8000/mcp \
  ghcr.io/johannhartmann/xlsliberator-swe-sandbox:2026.07.0 \
  xlsliberator-sandbox-smoke
```

This host-network command is an operator-authorized service health check, not a
workbook-task default. It passes only the credential-free MCP endpoint. The
smoke fails unless shell tools, both Python lines, LibreOffice, bundled
PyUNO, the script provider, workbook CLIs, Xvfb screenshots, image identity,
and a real FastMCP `list_tools` handshake all pass. A missing MCP endpoint is
`UNAVAILABLE`, never success.

## Resource and filesystem defaults

| Resource | Default | Enforcement |
|---|---:|---|
| CPU | 2 vCPU | LangSmith create request and Docker Compose |
| memory | 7,936 MiB | LangSmith create request and Docker Compose |
| root filesystem | 32 GiB | LangSmith snapshot/create request; Docker storage quota where supported |
| processes | 1,024 | Docker Compose; provider runtime policy otherwise |
| command timeout | 1,800 seconds | migration command policy |
| idle stop | 7,200 seconds | LangSmith create request |
| delete after stop | 86,400 seconds | LangSmith create request |

`/workspace` is the only durable writable job workspace. The image root is
read-only in the development Compose profile; `/tmp` and `/home/sandbox` are
bounded tmpfs mounts. Repository source mounts are read-only. The default
Compose network is `none`, the Docker socket is absent, all Linux capabilities
are dropped, privilege escalation is disabled, and PID 1 is an init process
that reaps descendants. Each thread gets a disposable home and an isolated
workspace; cleanup removes the job rather than reusing it across tenants.
Production providers must enforce equivalent controls; inability to enforce a
required limit is `UNAVAILABLE`.

## Capability and adversary boundary

Mail, database, HTTP, filesystem export, and build-farm access require explicit
credential-free grants in `XLSLIBERATOR_CAPABILITY_GRANTS_JSON`. Grants are
created by deployment policy, bound to an agent role and opaque adapter
resource, and copied into `thread-metadata/xlsliberator_security`. Workbook or
API content may declare a need but cannot grant itself authority. A missing
grant returns `UNAVAILABLE` before workbook hydration.

Network remains disabled inside the workbook container. Granted operations are
performed by authenticated server-side adapters with curated MCP paths and
role-specific tool allowlists. Only the LibreOffice engineer can receive
build-farm mutation authority, and that still requires the separate repair-flow
authorization. Implementation agents never receive reviewer hidden-test tools.

Workbook cells, formulas, VBA, names, comments, external data, and tool output
are delimited as untrusted data. They cannot select executables, mounts,
endpoints, roles, tools, grants, or evidence verdicts. The
`security-adversary` specialist is read-only except for
`migration/evidence/security/**` and must report exactly twelve threat probes;
an escape is `FAIL` and an unexercised required probe is `UNAVAILABLE`.

CI runs an ordinary `xlsprobe` command under the networkless boundary, tests
read-only root and credential absence, stops a container with a live child
process to verify process-tree cleanup, and runs Bandit plus `pip-audit` from
inside Docker. The audit's outbound advisory lookup is an explicit CI-only HTTP
capability and is not available to workbook execution.

## LangSmith snapshot

Push the multi-architecture image by immutable tag or digest, then create the
snapshot through LangSmith's UI or the existing helper:

```bash
docker run --rm \
  -e LANGSMITH_API_KEY \
  ghcr.io/johannhartmann/xlsliberator-swe-sandbox:2026.07.0 \
  open-swe-python /opt/open-swe/scripts/create_sandbox_snapshot.py \
    --name xlsliberator-open-swe-2026-07-0 \
    --image ghcr.io/johannhartmann/xlsliberator-swe-sandbox:2026.07.0 \
    --fs-capacity 34359738368
```

The helper therefore runs inside the versioned image, not through host Python.
Set the returned UUID as
`DEFAULT_SANDBOX_SNAPSHOT_ID`, set `REPO_SNAPSHOT_BASE_IMAGE` to the immutable
image reference, and set `XLSLIBERATOR_SANDBOX_IMAGE_DIGEST` to the published
digest. Every migration thread then records the image tuple, digest when
available, snapshot ID, and sandbox ID.

Daytona, Runloop, E2B, and Modal remain supported through Open SWE's existing
provider adapters. Their template/snapshot must be built from this Dockerfile
and must pass the same smoke command. If a provider cannot preserve the pinned
LibreOffice/PyUNO image or resource limits, workbook migration is unavailable
on that provider.

`SANDBOX_TYPE=local` is not an isolated sandbox: it runs commands directly in
the server's environment. It is unsuitable for workbook migration and never
authorizes local Python, UNO, PyUNO, LibreOffice, or `soffice`. The
`docker-compose.sandbox.yml` image is the Docker-only local-development
surface.

## Residual risk and production requirements

Containers share the host kernel, so kernel or Docker-engine compromise,
trusted orchestrator compromise, and previously unknown LibreOffice/parser
vulnerabilities remain residual risks. Higher-assurance deployments should use
an ephemeral VM or microVM boundary while preserving the same immutable image,
resource limits, no-network default, per-job storage, and evidence contract.

Production must authenticate the public migration API and every MCP service,
authorize every tool by task and role, isolate tenant storage and encryption
keys, enforce outbound allowlists at the adapter layer, use short-lived service
credentials, verify immutable image digests, collect audit logs without
workbook secrets, and delete expired workspaces. An isolated LibreOffice user
profile alone is never considered a security sandbox.
