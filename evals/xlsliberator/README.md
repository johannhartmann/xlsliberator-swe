# XLSLiberator migration benchmark

This harness compares the server-approved lead/specialist/reviewer
configurations in `approved-configurations.json`. The trusted benchmark service
runs the public workbook corpus through the public migration API and executes
hidden acceptance only in the independent reviewer boundary.

The runner sends configuration identities and public dataset identity. It
explicitly requests aggregate hidden outcomes only. The response is rejected if
it contains hidden definitions, omits an approved configuration, or introduces
an unapproved configuration. The resulting report keeps public and hidden
status summaries separate and groups them by configuration, source format, and
feature family.

For an offline replay, provide a versioned observation envelope:

```text
open-swe-python -m evals.xlsliberator.run_benchmark \
  --observations /workspace/observations.json \
  --output /workspace/benchmark-report.json \
  --check-release
```

This command is run only inside the pinned Docker sandbox. Observation records
contain evidence paths and aggregate results, never hidden cases, inputs,
expected values, prompts, or reviewer reasoning.
