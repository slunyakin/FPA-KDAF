# KDAF v0.6 Release Readiness Report

Evidence date: 2026-08-12

## Readiness decision

KDAF v0.6 is ready for public local evaluation and early-adopter inspection. The offline public
demo, evaluation harness, and seven-case FP&A benchmark are repeatable without Docker or an external
model provider. This decision does not classify KDAF as production-ready: production persistence,
identity, access control, retention, monitoring, and provider operations remain adopter
responsibilities or future work.

The final package-version update, release notes, and consolidated adoption navigation belong to the
dependent adoption-package issue, KDAF-033.

## Readiness checklist

| Gate | Status | Evidence |
| --- | --- | --- |
| Static foundation smoke | Pass | `pytest -m smoke`: 5 passed |
| Full automated suite | Pass | `pytest`: 154 passed, 3 clean Docker skips |
| Lint | Pass | `ruff check .`: passed |
| FP&A benchmark baseline | Pass | 7 selected cases, 7 passed, 0 failed |
| Offline public demo | Pass | Documented script creates a cited answer and passing evaluation result |
| Stable public errors | Pass | CLI/tool/script tests cover malformed, missing, invalid, and not-found inputs |
| Bad-request server survival | Pass | JSON-line server processes a valid request after malformed input |
| Secret/config leakage checks | Pass | Provider/config failures return bounded errors without credentials or traces |
| Optional live Docker smoke | Not run | 3 tests skipped cleanly: Docker daemon unavailable |
| Final v0.6 packaging | Pending KDAF-033 | Version, release notes, and adoption index are intentionally downstream |

Commands executed for this report:

```bash
pytest -m smoke
pytest -m integration
pytest -q \
  tests/test_v06_fpna_benchmark.py::test_eval_harness_runs_public_benchmark_and_persists_baseline \
  tests/test_v06_public_demo.py::test_documented_public_demo_script_runs_offline
pytest
ruff check .
```

The full suite and lint are rerun on every issue branch before commit. Docker tests are designed to
skip rather than fail when Docker is unavailable.

## Benchmark baseline

| Case | Baseline | Evidence behavior |
| --- | --- | --- |
| Variance | Pass | Financial facts, required semantic concepts, provenance, validation, citations |
| Budget vs actuals | Pass | Monthly revenue comparison with cited DWH evidence |
| Forecast | Pass | Forecast movement evidence and semantic context |
| Department spend | Pass | Department operating-expense facts and concepts |
| Revenue driver | Pass | Revenue/headcount driver context and cited facts |
| Provenance-heavy | Pass | DWH query IDs plus graph-to-question lineage and validation state |
| Unsupported claim | Pass | Cash-balance request returns `insufficiently_supported` with no citations |

The canonical cases and rubric are in
[`src/kdaf/resources/benchmarks/fpna_v1.json`](../src/kdaf/resources/benchmarks/fpna_v1.json), with
usage documented in [the benchmark guide](fpna-benchmark-v0.6.md). Per-case results are stored in
the metadata database; financial values are not copied into result metadata or Neo4j.

## Architecture coverage

| Architecture boundary | Covered behavior | Evidence | Current boundary |
| --- | --- | --- | --- |
| Neo4j semantic graph | Concepts, relationships, relevance, provenance links, validation state | CARP tests, live graph integration test, offline graph benchmark | Live test not executed for this report because Docker is unavailable |
| Postgres metadata DB role | Projects, runs, workflow audit, validation, evaluation results | Metadata repository, evaluation, benchmark, and demo tests | Dependency-free local workflows currently use the separate SQLite metadata adapter |
| Separate Postgres DWH role | Controlled read-only financial queries and facts | DWH adapter tests, evidence packets, benchmark | Local demo uses a separate SQLite DWH adapter; Postgres query adapter is unit-tested |
| No financial facts in Neo4j | Graph output and graph adapter contain no DWH amounts/fact tables | Explicit architecture-boundary tests | Required invariant; no exception |
| Shared core services | CLI, tool server, and scripts call `KdafCore` workflows | Public-entrypoint tests | No separate business logic per interface |
| Stable error envelope | Machine-readable code/message; server continues | Negative-path and server-survival tests | Authentication/authorization is outside current scope |

## Supported workflows

- create and inspect projects, runs, competency questions, and MVG metadata
- load the FP&A starter DWH, semantic graph, question catalog, and starter kit
- register/extract CSV sources with cross-store provenance and expert validation state
- execute controlled read-only DWH queries
- retrieve CARP semantic context from Neo4j or the explicit offline seed
- build evidence packets and generate citation-checked grounded answers
- refuse unsupported claims and sanitize provider failures
- run repeatable starter evaluations and the seven-case public FP&A benchmark
- run the project-to-evaluation public demo through core, CLI, tool server, or script

## Unsupported areas and known limitations

- formats other than CSV are not extracted
- project-to-source, MVG-to-source, and MVG-to-extraction associations are not automatic
- local extraction and starter-DWH workflows do not yet persist through production Postgres adapters
- the starter catalog and allow-listed queries cover a small FP&A domain, not all finance workflows
- live Neo4j and full Docker-stack health were not verified in this report environment
- identity, authorization, multi-tenancy, retention, monitoring, backups, and deployment hardening are
  not supplied
- provider-specific streaming, retry, rate-limit, and production observability are not supplied
- citations prove linkage to supplied evidence, not source accuracy or analytical correctness

## Next-release roadmap

No v0.7 milestone or committed scope exists in the repository as of the evidence date. The next
release should be planned from these evidence-backed gaps rather than treated as an implied promise:

1. define a milestone and acceptance criteria for production Postgres metadata/DWH persistence;
2. decide and test automatic relevance links among projects, MVGs, sources, and extractions;
3. expand the public benchmark with adopter datasets and additional finance workflows;
4. specify provider retry, streaming, rate-limit, and observability contracts;
5. publish an application-security and operations profile covering identity, authorization,
   retention, monitoring, backup, and recovery; and
6. run and publish live Docker/Neo4j/Postgres evidence in a Docker-capable release environment.

These are roadmap candidates until maintainers create and prioritize corresponding issues.
