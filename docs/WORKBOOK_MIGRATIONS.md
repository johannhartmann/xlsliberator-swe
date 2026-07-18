# Workbook migration triggers

Workbook migrations are first-class, resumable Open-SWE threads. The trigger
API hydrates the source into the thread's persistent Docker sandbox, runs the
deterministic `xlsprobe dossier` command, and dispatches the normal agent graph
with bounded dossier metadata. It never places workbook bytes, extracted cell
text, formulas, or VBA source in the system prompt.

## API

All routes require `Authorization: Bearer <XLSLIBERATOR_TRIGGER_TOKEN>`. The
deployment must leave the routes unavailable when the token is not configured.

- `POST /api/xlsliberator/migrations` creates or idempotently returns a
  migration. It accepts exactly one base64 upload or public artifact URL.
- `POST /api/xlsliberator/migrations/{thread_id}/follow-ups` interrupts and
  resumes the same durable thread with requirements and/or a dependency.
- `POST /api/xlsliberator/migrations/{thread_id}/cancel` cancels pending and
  running executions without silently deleting evidence.
- `DELETE /api/xlsliberator/migrations/{thread_id}` explicitly removes the
  source and dossier from the persistent sandbox.

The trigger contract includes `task_kind=workbook_migration`, the original
filename, caller-supplied SHA-256, user requirements, dependency metadata,
output restrictions, LibreOffice profile and exact build `26.2.4.2`, and a
privacy/retention policy. A tenant-scoped UUIDv5 of the source SHA-256 produces
the stable thread ID. A separate delivery digest makes retries idempotent.

## Hydration and safety

The API validates the filename, extension, media type, file size, SHA-256 and
container signature before upload. ZIP packages are scanned without expanding
them and are rejected for unsafe paths, excessive entries, oversized members,
total expansion, or compression ratio. Public downloads use DNS pinning and
validate every redirect. Interrupted or incomplete hydration fails the trigger;
it never starts an agent run.

Validated files are uploaded under `/workspace/source/`. `xlsprobe dossier`
runs inside the versioned Docker sandbox and transactionally creates
`/workspace/migration/`. Thread metadata stores only sandbox-relative paths
such as `source/...` and `migration/`, never host paths or signed source URLs.
The same sandbox ID remains bound to the thread, so follow-ups resume with the
same dossier.

Workbook content, VBA comments, formulas, extracted text, attachment names and
dependency content are always untrusted data. The model sees only a bounded
summary containing counts, coverage status, user requirements, restrictions
and artifact-relative paths. Ordinary Open-SWE tasks do not set
`task_kind=workbook_migration`; the workbook middleware is therefore a no-op
for the original coding workflow.

GitHub issue/PR attachments and optional Slack/Linear attachments use this same
trigger contract after their existing webhook layer has safely retrieved the
attachment. They must not bypass hash, media, archive or authorization checks.

## Docker-only operation

The API service, migration sandbox, `xlsprobe`, Python, LibreOffice, UNO and
PyUNO run only in Docker. The host may invoke Docker and perform Git/file
operations, but it must never run local Python, `uv`, LibreOffice, UNO or
PyUNO.
