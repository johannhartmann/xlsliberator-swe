# Autonomous migration showcase

The manually dispatched `XLSLiberator autonomous showcase` workflow is the
reproducible public entrypoint for the first complete workbook-migration
episode. It accepts the immutable public `TetrisGameDemo.xlsb` through
`POST /api/xlsliberator/migrations`, runs Open SWE with the declared GitHub
Models role models, and targets only LibreOffice full build `26.2.4.2`.

The trusted server container receives the workflow-scoped GitHub token for
model inference and the Docker socket for sandbox orchestration. Per-thread
workbook sandboxes are separately created with no network, no credentials, no
Docker socket, a read-only root filesystem, dropped capabilities, bounded
resources, and writable private tmpfs mounts. LibreOffice and PyUNO are invoked
only through the trusted runtime MCP, whose office jobs are disposable Docker
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

GitHub Models access is granted only through the workflow's `models: read`
permission. No long-lived provider key is required, and the workflow records
the billed model cost as zero while disclosing that GitHub may apply account
rate limits. Manual dispatch prevents ordinary pull-request updates from
consuming the public model quota.
