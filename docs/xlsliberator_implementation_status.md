# XLSLiberator Open SWE implementation status

This ledger tracks the thin `johannhartmann/xlsliberator-swe` customization.
The deterministic workbook tooling remains in the separate
`johannhartmann/xlsliberator` repository.

## Upstream and repository boundary

- Initial Open SWE upstream:
  `f0897479c38f2506f03b4de38081d4770928f09d`.
- `origin`: `johannhartmann/xlsliberator-swe`.
- `upstream`: `langchain-ai/open-swe`.
- Domain code: `agent/xlsliberator/`.
- Default work repository: `johannhartmann/xlsliberator`.
- Upstream synchronization:
  [UPSTREAM_SYNC.md](../UPSTREAM_SYNC.md) and
  `scripts/check_upstream_drift.sh`.

The fork preserves the existing Slack, Linear, GitHub, dashboard, sandbox,
reviewer, analyzer, CI auto-fix, and upstream application structure. Prompt 07
does not replace or special-case ordinary Open SWE coding tasks.

## Prompt 07 baseline evidence

The application code at baseline was byte-for-byte Open SWE commit
`f0897479c38f2506f03b4de38081d4770928f09d`; the only fork commit in
[Agent CI run 29649629212](https://github.com/johannhartmann/xlsliberator-swe/actions/runs/29649629212)
added the missing CI typecheck job.

| Exact command | Exit | Outcome |
|---|---:|---|
| `make lint` | 0 | Upstream Ruff lint and format diff check passed. |
| `make format-check` | 0 | Upstream format check passed. |
| `make typecheck` | 0 | BasedPyright passed for `agent` and `tests`. |
| `make test` | 0 | The complete upstream unit test suite passed. |
| `cd tests/e2e && npx playwright test` | 0 | The uncustomized LangGraph/FastAPI/dashboard stack booted and the normal Open SWE coding workflow passed. |

The local Docker baseline build was attempted first and failed before executing
project code because Docker Desktop could not write its containerd metadata
database (`input/output error`). No host Python, `uv`, UNO, LibreOffice, or
`soffice` fallback was used.

## Prompt 07 customized evidence

The customized foundation at commit `27d2aa19` passed the complete preserved
Open SWE workflow in
[Agent CI run 29649931382](https://github.com/johannhartmann/xlsliberator-swe/actions/runs/29649931382):
Ruff lint, format checking, BasedPyright, the complete unit suite, and the
Playwright coding-workflow E2E test all passed. The separate
[upstream-drift run 29649931415](https://github.com/johannhartmann/xlsliberator-swe/actions/runs/29649931415)
also passed.

## Prompt checklist

| Prompt | Status | Acceptance evidence |
|---:|---|---|
| 07 — thin Open-SWE fork | COMPLETE; REMOTE CI GREEN AT `27d2aa19` | retained history, typed settings, namespace, full preserved CI, upstream drift and sync procedure |
| 08 — sandbox snapshot | PENDING | image identity, SBOM, tool versions, sandbox smoke |
| 09 — triggers and hydration | PENDING | deterministic threads, attachment safety, durable artifact evidence |
| 10 — Deep Agents skills | PENDING | progressive disclosure, precedence, skill lint |
| 11 — core migration skills | PENDING IN `xlsliberator` | forensics, planning, testing, and package skill evidence |
| 12 — specialist skills | PENDING IN `xlsliberator` | formula, VBA, UI, dependency, and LibreOffice skill evidence |
| 13 — specialist routing | PENDING | isolated specialist scopes and model routing |
| 14 — curated MCP tools | PENDING | allowlists, typed unavailable states, integration traces |
| 15 — deterministic middleware | PENDING | checkpoints and anti-fake-success gates |
| 16 — migration lead | PENDING | workflow and end-to-end trajectory |
| 17 — independent reviewer | PENDING | independent identity and hidden-test gate |
| 18 — web threads | PENDING | job/thread mapping, resume, artifact delivery |
| 19 — demos and corpus | PENDING | representative public episodes |
| 20 — repair promotion | PENDING | repair PR flow and build-farm boundary |
| 21 — execution hardening | PENDING | sandbox, network, secret, and retention controls |
| 22 — LangSmith evaluations | PENDING | datasets, evaluators, thresholds, release gate |
| 23 — autonomous showcase | PENDING | reproducible migration and independent verdict |

## Next action

Complete Prompt 08 by building and smoke-testing the versioned Docker-only
workbook migration sandbox.
