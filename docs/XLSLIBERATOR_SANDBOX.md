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
Runtime services inject short-lived credentials or proxy access outside the
image.

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
checkout, then run the sandbox smoke on the host network:

```bash
docker compose -f ../xlsliberator/docker-compose.yml up -d --build xlsliberator-mcp
docker run --rm --network host \
  -e XLSLIBERATOR_LIBREOFFICE_MCP_ENDPOINT=http://127.0.0.1:8000/mcp \
  ghcr.io/johannhartmann/xlsliberator-swe-sandbox:2026.07.0 \
  xlsliberator-sandbox-smoke
```

The smoke fails unless shell tools, both Python lines, LibreOffice, bundled
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
bounded tmpfs mounts. Repository source mounts are read-only. Production
providers must enforce equivalent controls; inability to enforce a required
limit is `UNAVAILABLE`.

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
