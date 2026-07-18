# Workbook migration triggers

Workbook migrations are first-class, resumable Open-SWE threads. The trigger
API hydrates the source into the thread's persistent Docker sandbox, runs the
deterministic `xlsprobe dossier` command, and dispatches the normal agent graph
with bounded dossier metadata. It never places workbook bytes, extracted cell
text, formulas, or VBA source in the system prompt.

## API

All routes require `Authorization: Bearer <XLSLIBERATOR_TRIGGER_TOKEN>` and an
`X-XLSLiberator-Owner` header. The owner must equal the request owner on create
and the persisted thread owner thereafter. Cross-owner lookups return 404 so
thread existence is not disclosed. The deployment must leave the routes
unavailable when the token is not configured.

- `POST /api/xlsliberator/migrations` creates or idempotently returns a
  migration. It accepts exactly one base64 upload or public artifact URL.
- `POST /api/xlsliberator/migrations/{thread_id}/follow-ups` interrupts and
  resumes the same durable thread with requirements and/or a dependency.
- `POST /api/xlsliberator/migrations/{thread_id}/cancel` cancels pending and
  running executions without silently deleting evidence.
- `GET /api/xlsliberator/migrations/{thread_id}` returns safe operation status
  and the fixed public artifact manifest.
- `GET /api/xlsliberator/migrations/{thread_id}/events?since=N` streams stable
  lead, plan, specialist, LibreOffice, reviewer, and final stages.
- `GET /api/xlsliberator/migrations/{thread_id}/artifacts` lists opaque artifact
  IDs; `.../artifacts/{artifact_id}` downloads one owner-checked artifact.
- `GET /api/xlsliberator/migrations/{thread_id}/final` returns only after a
  terminal state.
- `DELETE /api/xlsliberator/migrations/{thread_id}` explicitly removes the
  source and dossier from the persistent sandbox.

The trigger contract includes `task_kind=workbook_migration`, the original
filename, caller-supplied SHA-256, user requirements, dependency metadata,
output restrictions, LibreOffice profile and exact build `26.2.4.2`, and a
privacy/retention policy. A tenant-scoped UUIDv5 of the source SHA-256 produces
the stable thread ID. A separate delivery digest makes retries idempotent.
API responses never expose the sandbox-relative paths retained in private
thread metadata.

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

Completion requires the dossier, plan, ODS, public acceptance scenarios,
LibreOffice execution evidence, save/reopen evidence, unresolved inventory,
and independent reviewer result. When the policy requests source deletion,
`/workspace/source` and `/workspace/dependencies` are removed before the API
reports `complete`. The API persists an absolute expiry from `retain_days`;
expired workspaces are deleted and return 410.

Only an explicit publication allowlist can be downloaded: the ODS, generated
Python/UNO or service/extension artifacts, reports, public tests and
trajectories, LibreOffice/reviewer evidence, visual evidence, and logs. Unsafe
names, internal/hidden paths, oversized files, credentials, hidden-case
material, system prompts, and private reasoning fail closed. Internal paths in
otherwise safe text artifacts are redacted.

Workbook content, VBA comments, formulas, extracted text, attachment names and
dependency content are always untrusted data. The model sees only a bounded
summary containing counts, coverage status, user requirements, restrictions
and artifact-relative paths. Ordinary Open-SWE tasks do not set
`task_kind=workbook_migration`; the workbook middleware is therefore a no-op
for the original coding workflow.

GitHub issue/PR attachments and optional Slack/Linear attachments use this same
trigger contract after their existing webhook layer has safely retrieved the
attachment. They must not bypass hash, media, archive or authorization checks.

## Progressive-disclosure skills

Only the main agent for `task_kind=workbook_migration` receives migration
skills. Deep Agents exposes names, descriptions, compatibility and declared
tools first; the agent reads a full `SKILL.md` or its resources only when the
task makes that skill relevant. Ordinary coding tasks and general-purpose or
browser subagents do not inherit these sources.

Sources are loaded with deterministic last-wins precedence: bundled Open-SWE
orchestration guidance, the approved XLSLiberator repository's `skills/`
directory, optional team sources, then optional user sources. The project
source is exported from the deployment-approved repository and ref into a
separate sandbox path. A task branch, pull-request head, workbook, or user
message cannot select the source ref or inject a skill. Optional sources must be
pre-materialized by trusted deployment code below
`/workspace/.xlsliberator-skills/`.

Every skill must use a matching lowercase-hyphen directory and `name`, explain
what it does and when to use it, declare compatibility and allowed or
recommended tools, remain below the size limit, and pass `make skill-lint`.
When a generic migration fix becomes reusable, update the relevant project
skill, validate it, and submit the change through the normal review flow.
Customer workbook content must never be copied into skill instructions.

## Docker-only operation

The API service, migration sandbox, `xlsprobe`, Python, LibreOffice, UNO and
PyUNO run only in Docker. The host may invoke Docker and perform Git/file
operations, but it must never run local Python, `uv`, LibreOffice, UNO or
PyUNO.
