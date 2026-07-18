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
| 08 — sandbox snapshot | COMPLETE; REMOTE CI GREEN AT `84d22454` | Docker-only image build, immutable dependency locks, exact LibreOffice `26.2.4.2`, PyUNO/runtime tool smoke, MCP connectivity, identity, secret scan and SPDX SBOM in [run 29651333157](https://github.com/johannhartmann/xlsliberator-swe/actions/runs/29651333157) |
| 09 — triggers and hydration | COMPLETE; REMOTE CI GREEN AT `f513e485` | deterministic threads, fail-closed attachment safety, durable sandbox hydration, bounded dossier context, resume/cancel/cleanup, full Agent CI in [run 29651655678](https://github.com/johannhartmann/xlsliberator-swe/actions/runs/29651655678) and Docker-only sandbox evidence in [run 29651655701](https://github.com/johannhartmann/xlsliberator-swe/actions/runs/29651655701) |
| 10 — Deep Agents skills | COMPLETE; REMOTE SANDBOX CI GREEN AT `9228c3aa` | progressive disclosure, precedence, skill lint and migration-only wiring |
| 11 — core migration skills | COMPLETE IN `xlsliberator` | production forensics, planning, testing, package and security skills; full CI in [run 29652794341](https://github.com/johannhartmann/xlsliberator/actions/runs/29652794341) |
| 12 — specialist skills | COMPLETE IN `xlsliberator` | formula, VBA, UI, dependency, adapter, debugging and core-patching skills; full CI in [run 29652794341](https://github.com/johannhartmann/xlsliberator/actions/runs/29652794341) |
| 13 — specialist routing | COMPLETE AT `886a23dc` | isolated specialist scopes, artifacts, budgets and model routing |
| 14 — curated MCP tools | COMPLETE; REMOTE CI GREEN AT `37c52efa` | allowlists, typed unavailable states, integration traces; Agent and sandbox runs `29653378974` and `29653378972` |
| 15 — deterministic middleware | COMPLETE AT `49164719` | ordered checkpoints, resume, mutation and anti-fake-success gates |
| 16 — migration lead | COMPLETE AT `18e0d770` | deterministic lead trajectory, feature routing and terminal evidence contract |
| 17 — independent reviewer | COMPLETE; REMOTE CI GREEN AT `7c7ee4c8` | independent identity, read-only review, hidden-test and artifact-digest approval gate; Agent and sandbox runs `29654989184` and `29654989178` |
| 18 — web threads | COMPLETE; REMOTE CI GREEN AT `6a7f22bc` | authenticated owner-scoped status/events/messages/artifacts/final API, deterministic thread mapping, retention, safe publication and fake-service integration |
| 19 — demos and corpus | COMPLETE IN `xlsliberator`; REMOTE CI GREEN AT `28a80f5` | eight licensed serious episodes, behavioral scenarios, searchable public subsets, evidence-derived reporting |
| 20 — repair promotion | COMPLETE; REMOTE MAIN CI GREEN AT `28a80f5`; OPEN-SWE FORMAT REPAIR INCLUDED IN `e2430a23` | exact eight-stage state machine, immutable layer classification, pinned LO identities, corpus/build-farm boundaries, validator and independent-review gates |
| 21 — execution hardening | IMPLEMENTED AT `d0481087`; CI REPAIR PUSHED AS `e2430a23` | networkless read-only sandbox, server-owned typed grants, role-authorized MCP, twelve-probe security adversary, escape smoke, Docker Bandit and dependency audit; main repository fully green in run `29658220586` |
| 22 — LangSmith evaluations | IMPLEMENTED; CI EVIDENCE PENDING | migration-only trace metadata, exactly fourteen deterministic evaluators, five-state public/hidden reports, format/feature/configuration grouping, fail-closed release decision, nightly approved-configuration benchmark |
| 23 — autonomous showcase | PENDING | reproducible migration and independent verdict |

## Next action

Obtain blocking CI evidence for Prompts 21 and 22, then execute the first full
autonomous migration showcase in Prompt 23.
