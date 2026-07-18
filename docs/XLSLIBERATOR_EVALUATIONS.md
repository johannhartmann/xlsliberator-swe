# XLSLiberator evaluations and release gates

XLSLiberator migration claims come from typed evidence. Model prose, progress
messages, and public-suite success cannot certify a migration.

## Trace contract

`MigrationEvaluationTraceMiddleware` adds searchable LangSmith metadata only
for workbook migrations. Lead and specialist calls record:

- agent role and trajectory;
- selected skills;
- tool or XLSLiberator MCP operation;
- exact provider, model identifier, and model version;
- observed cost and retry count;
- current checkpoint and canonical evidence paths;
- public, hidden-aggregate, mutation, reviewer, and repair-promotion outcomes.

Specialist middleware adds the specialist role, declared skills, effort, and
writable artifact paths. Hidden test definitions, inputs, expected values,
prompts, and reviewer reasoning never enter lead/specialist traces.

## Deterministic evaluators

`agent/xlsliberator/evaluation.py` evaluates exactly these dimensions:

1. correct specialist delegation;
2. relevant skill selection;
3. no fake success;
4. no test weakening;
5. source-derived test quality;
6. hidden acceptance pass;
7. mutation kill rate;
8. save/reopen pass;
9. proprietary dependency removal;
10. reviewer agreement and evidence-backed rejection;
11. generic repair reuse;
12. manual intervention rate;
13. cost and latency per successful migration;
14. security-policy adherence.

Every result is one of `passed`, `failed`, `skipped`, `unavailable`, or
`not_run`. A decisive result has a confined evidence path. Mutation acceptance
requires a declared threshold (default `0.8`). Cost and latency require measured
values and declared budgets; missing values are `unavailable`, not zero.

The release decision is derived. Required evaluators must pass, the required
public corpus, security suite, and hidden acceptance must pass, and the
independent reviewer must return `APPROVE`. A correct `REVISE` or `BLOCK`
decision can pass the reviewer-agreement evaluator while still blocking the
release.

## Capability reporting

Nightly output identifies LibreOffice full build `26.2.4.2` and groups results
by approved team configuration, source format, and feature family. Public and
hidden summaries are separate. Rates use only decisive passed/failed results;
the underlying five-state counts remain visible. No manually maintained
percentage is a release claim.

## Nightly benchmark

`.github/workflows/xlsliberator_eval.yml` builds the pinned office and agent
images, then asks a trusted benchmark service to run the public workbook dataset
through the public migration API for every configuration in
`evals/xlsliberator/approved-configurations.json`. The service executes hidden
tests only inside the independent reviewer boundary and returns typed aggregate
observations.

The benchmark harness rejects:

- hidden definitions in the response;
- unapproved configurations;
- omitted approved configurations;
- a target other than LibreOffice `26.2.4.2`;
- any required migration release gate that is not passed.

The bridge-networked harness is a trusted CI coordinator. It does not execute
untrusted workbooks and does not forward its benchmark token into migration
jobs. Each hostile-workbook job retains the networkless, read-only,
capability-dropped sandbox policy.

Required repository secrets are `XLSLIBERATOR_BENCHMARK_ENDPOINT` and
`XLSLIBERATOR_BENCHMARK_TOKEN`. They authorize benchmark orchestration, not
workbook behavior. The uploaded report is privacy-safe and contains hidden
aggregate outcomes only.
