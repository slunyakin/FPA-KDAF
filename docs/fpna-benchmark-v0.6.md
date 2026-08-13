# KDAF FP&A Public Benchmark v1

The v0.6 benchmark is a deterministic, inspectable baseline for KDAF's finance-specific retrieval
and grounded-answer workflow. Its canonical fixture is packaged at
`src/kdaf/resources/benchmarks/fpna_v1.json`.

## Coverage

| Case | Behavior evaluated |
| --- | --- |
| `fpna:variance` | Largest actual-to-budget variance evidence |
| `fpna:budget_vs_actuals` | Monthly revenue budget comparison |
| `fpna:forecast` | Revenue forecast movement |
| `fpna:department_spend` | Department operating-expense analysis |
| `fpna:revenue_driver` | Revenue driver context |
| `fpna:provenance_heavy` | DWH query IDs, question linkage, graph context, and validation state |
| `fpna:unsupported_claim_refusal` | Refusal when the evidence does not support a cash-balance claim |

## Expected evidence and grading rubric

Every case declares required graph concept IDs and whether it requires financial facts, provenance,
and validation state. A grounded-answer case must return valid evidence citations. The refusal case
must return `insufficiently_supported` with no citations. A case passes only when every declared
criterion passes; the suite passes only when every selected case passes.

Execution errors do not abort the suite. They are persisted in the metadata database with
`status: "error"` and `error: {"code": "...", "message": "..."}`. Result metadata contains IDs and
grades, not DWH financial values.

## Run the baseline

Create a project and load the starter kit first, then run:

```bash
kdaf --metadata-store .kdaf/v06-metadata.sqlite3 \
  --dwh-store .kdaf/v06-financial-dwh.sqlite3 \
  eval benchmark <project-id> --offline-graph
```

Print the fixture with `kdaf eval catalog`. Select individual cases by repeating
`--case-id <benchmark-case-id>`. The tool-server equivalents are `eval.catalog` and
`eval.benchmark`.

The packaged offline graph makes the baseline network-free. Omit `--offline-graph` to exercise
live Neo4j. Financial numbers remain in the separate DWH in both modes.
