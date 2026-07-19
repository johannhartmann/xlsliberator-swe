# Autonomous migration showcase

The manually dispatched `XLSLiberator autonomous showcase` workflow is the
reproducible public entrypoint for the first complete workbook-migration
episode. It accepts the immutable public `TetrisGameDemo.xlsb` through
`POST /api/xlsliberator/migrations`, runs Open SWE with the selected provider's
declared role models, and targets only LibreOffice full build `26.2.4.2`.

The workflow supports direct OpenAI, Anthropic, Google Gemini, and Fireworks
credentials. GitHub Models is deliberately unavailable to the workflow. A
manual dispatch must explicitly authorize paid model usage before the job can
start. The trusted server container receives only the selected provider
credential and the Docker socket for sandbox orchestration. Per-thread workbook
sandboxes are separately created with no network, no credentials, no Docker
socket, a read-only root filesystem, dropped capabilities, bounded resources,
and writable private tmpfs mounts. LibreOffice and PyUNO are invoked only
through the trusted runtime MCP, whose office jobs are disposable Docker
containers.

The workflow fails unless the public API reaches `complete` and exposes the
canonical dossier, plan, ODS target, source-derived scenarios, LibreOffice and
save/reopen evidence, mutation result, unresolved report, independent
`APPROVE`, and the WebM/HTML/JSON replay. A read-only validator safely extracts
`public-showcase.zip`, rejects unsafe or unindexed archive entries, verifies
every byte against the strict manifest, and checks the source, runtime,
specialist, scenario, lifecycle, mutation, liberation, reviewer, replay, and
operations cross-references. The uploaded workflow artifact also contains
content hashes, service logs, image identity, invocation metadata, terminal
status, and the validator result.

Direct providers require the matching repository secret: `OPENAI_API_KEY`,
`ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, or `FIREWORKS_API_KEY`. The workflow
does not request the `models: read` permission and never uses the workflow token
for model inference.

This manually dispatched showcase is diagnostic evidence, not a required CI
status check. Direct-provider runs remain strict and fail unless all evidence
gates pass.
