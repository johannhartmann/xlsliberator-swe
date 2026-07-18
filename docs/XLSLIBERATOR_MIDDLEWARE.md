# XLSLiberator migration middleware

The deterministic middleware stack is installed only when
`task_kind=workbook_migration`. Ordinary Open SWE coding runs keep the upstream
middleware path.

The fixed order is:

1. `PromptInjectionBoundaryMiddleware`
2. `LiberationPolicyMiddleware`
3. `NoTestWeakeningMiddleware`
4. `MigrationBudgetMiddleware`
5. `MigrationCheckpointMiddleware`
6. `RegressionPromotionMiddleware`
7. `NoFakeSuccessMiddleware`
8. `EvidenceRequiredMiddleware`

Workbook-derived text is always untrusted data. It cannot change service
authorization, tool policy, credentials, approvals, or evidence gates. The
liberation and test guards return actionable error tool messages before a
forbidden change executes.

Meaningful successful operations snapshot `migration/dossier.md`,
`migration/plan.md`, current output, generated code, tests, logs, and evidence
under `migration/checkpoints/`. A resumed run validates the latest checkpoint
name and manifest and restores only missing artifacts from it. Symbolic-link or
malformed checkpoint state fails closed.

A migration must end with exactly one explicit marker:

- `XLSLIBERATOR_STATUS: DELIVERABLE` requires the dossier, plan, target ODS,
  acceptance scenarios, LibreOffice execution trace, save/reopen result,
  unresolved list, and independent reviewer result. The runtime service must
  report `AVAILABLE`, and evidence cannot describe required operations as
  skipped, unavailable, unimplemented, timed out, transport-only, or missing.
- `XLSLIBERATOR_STATUS: UNRESOLVED` requires a non-empty
  `migration/unresolved.md`. Budget exhaustion writes this result instead of
  manufacturing success.

If a migration changes generic XLSLiberator or LibreOffice implementation code,
delivery additionally requires a minimized fixture, fail-before/pass-after
test, affected corpus run, and skill or capability update under
`migration/regression/`.

The following server-side limits are optional and must be positive:

- `XLSLIBERATOR_BUDGET_MODEL_CALLS`
- `XLSLIBERATOR_BUDGET_SPECIALIST_RUNS`
- `XLSLIBERATOR_BUDGET_RUNTIME_SESSIONS`
- `XLSLIBERATOR_BUDGET_BUILD_FARM_CALLS`
- `XLSLIBERATOR_BUDGET_COST_USD`
- `XLSLIBERATOR_BUDGET_WALL_SECONDS`
