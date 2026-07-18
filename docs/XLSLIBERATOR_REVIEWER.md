# XLSLiberator independent migration reviewer

The `migration_reviewer` LangGraph assistant reviews workbook behavior in a
fresh model context after the migration lead has produced a candidate. It
shares the persistent migration sandbox for reads, but it cannot edit source,
candidate, plan, tests, evidence, or reviewer files. A schema-validating
server-side tool is the only writer for
`migration/reviewer/result.json`.

The lead starts review with `request_independent_migration_review`. The tool
uses a new review thread, the configured reviewer model, the current target ODS
SHA-256, and a reviewer-only MCP registry. The implementation registry never
contains `xlsliberator_corpus_run_hidden_acceptance`; hidden definitions and raw
cases therefore never enter the lead context. The reviewer result exposes only
aggregate hidden-suite counts, a safe summary, structured findings, and
filesystem evidence paths.

The reviewer reads the original dossier and source, requirements, plan,
generated ODS and modules, public and mutation results, LibreOffice logs and
screenshots, save/reopen evidence, implementation trajectories, and unresolved
findings. It checks source-derived behavior coverage, adds adversarial
scenarios on disposable runtime sessions when needed, and verifies:

- no VBA project;
- no Basic event binding;
- no COM or Office automation;
- no Windows DLL dependency;
- no Excel runtime;
- no unresolved proprietary add-in.

The result state is one of:

- `APPROVE`: hidden acceptance executed and passed, every mandatory check
  passed, visual review passed or was not required, and no blocking finding
  remains.
- `REVISE`: the private candidate can be repaired from safe behavioral
  findings.
- `BLOCK`: required authority, source evidence, safe execution, or an open
  service is unavailable.

`IndependentReviewMiddleware` prevents the lead from forging reviewer output.
A deliverable terminal state requires `APPROVE`, and the reviewed artifact
digest must still equal the current `migration/output/target.ods`. Public test
success, stale approval, skipped hidden tests, or a plausible narrative cannot
pass this gate.
