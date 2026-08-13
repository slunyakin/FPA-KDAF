# KDAF

KDAF is a Knowledge-Driven Analytics Framework for finance-focused analytical systems. It is a neutral, reusable foundation for combining semantic financial context with governed numerical analytics.

## Purpose

KDAF separates meaning from measures:

- Neo4j stores semantic graph context such as entities, relationships, taxonomy, lineage, definitions, and analytical concepts.
- A Postgres metadata database stores framework metadata such as jobs, datasets, ingestion state, and operational records.
- A separate Postgres data warehouse stores financial numbers, facts, measures, and tabular analytical outputs.

Financial numbers must not be stored in the graph. The graph explains what financial data means and how concepts relate; the DWH stores the numeric values used for analysis.

## Architecture

The local runtime contains three backing services plus dependency-free local adapters used by the
CLI and MCP-style tool server:

| Service | Purpose | Default local connection |
| --- | --- | --- |
| Neo4j | Semantic graph | `bolt://localhost:7687`, browser `http://localhost:7474` |
| Postgres metadata DB | Framework metadata | `localhost:5432/kdaf_metadata` |
| Postgres financial DWH | Financial numbers and facts | `localhost:5433/kdaf_financial_dwh` |
| SQLite metadata store | v0.2 project/run metadata | `.kdaf/metadata.sqlite3` |
| SQLite extraction DWH adapter | v0.4 extracted financial rows | `.kdaf/extraction_dwh.sqlite3` |
| SQLite graph adapter | v0.4 semantic provenance references only | `.kdaf/graph_context.sqlite3` |

The v0.4 SQLite files preserve the same physical boundaries as production Postgres and Neo4j. They
are a local execution harness, not a change to storage ownership: CSV values go only to the DWH
adapter, while graph provenance contains identifiers and relationships only.

Configuration loads from built-in defaults, optionally from `config/kdaf.example.toml`, and then from `KDAF_*` environment variables.

## Local-First Posture

KDAF starts as a local-first framework. The default Docker Compose stack is suitable for development and smoke testing without depending on managed cloud services. Secrets in `.env.example` are development placeholders only.

## Non-Goals

- KDAF v0.2 is not a production deployment template.
- KDAF does not prescribe a single finance domain model.
- KDAF does not store financial facts, measures, or time series values in Neo4j.
- KDAF does not require Docker for static tests or package development.

## Quick Start

For a guided consumer walkthrough, see [docs/user-guide.md](docs/user-guide.md). For an explanation
of the value and workflow for analysts, finance leaders, engineers, developers, auditors, and
operators, see [the role-based consumer guide](docs/role-based-consumer-guide.md).

Create and activate a virtual environment, then install developer dependencies:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
```

Run the static foundation tests:

```bash
pytest -m "not integration"
```

Run all tests:

```bash
pytest
```

Run the optional live Docker smoke test:

```bash
pytest -m integration
```

The integration smoke test skips cleanly when Docker is unavailable.

## CLI and Tool Server

KDAF v0.2 adds a human CLI and an MCP-style JSON-line tool server. Both surfaces use the same
`KdafCore` APIs and the same metadata store.

Run a health check:

```bash
kdaf --metadata-store .kdaf/v02-demo.sqlite3 health
```

Show the non-secret config summary:

```bash
kdaf --metadata-store .kdaf/v02-demo.sqlite3 config
```

Create, list, and read projects:

```bash
kdaf --metadata-store .kdaf/v02-demo.sqlite3 project create "Demo Project"
kdaf --metadata-store .kdaf/v02-demo.sqlite3 project list
kdaf --metadata-store .kdaf/v02-demo.sqlite3 project get <project-id>
```

Create and read runs:

```bash
kdaf --metadata-store .kdaf/v02-demo.sqlite3 run create <project-id>
kdaf --metadata-store .kdaf/v02-demo.sqlite3 run get <run-id>
```

Load the full v0.3 FP&A starter kit for a project:

```bash
docker compose up -d --wait neo4j
kdaf --metadata-store .kdaf/v02-demo.sqlite3 starter-kit load <project-id>
```

This single command loads the starter DWH seed, starter Neo4j graph concepts, starter competency
questions, and MVG artifacts. Repeated loads return `status: "already_loaded"` for the project and
refresh the idempotent starter stores. Use `--skip-graph` when running offline without Neo4j.

Run the complete starter-kit demo sequence:

```bash
python scripts/run_starter_kit_demo.py \
  --metadata-store .kdaf/demo.sqlite3 \
  --dwh-store .kdaf/starter_dwh.sqlite3
```

The demo creates a project, loads the starter kit, runs starter DWH queries, lists starter questions
and MVGs, and inspects graph context. Add `--skip-graph` when Neo4j is not running.

Capture competency questions and use them to define a minimum viable graph (MVG) artifact:

```bash
kdaf --metadata-store .kdaf/v02-demo.sqlite3 competency-question create \
  <project-id> "Where is actual spend over budget this quarter?" \
  --business-context "Monthly business review"

kdaf --metadata-store .kdaf/v02-demo.sqlite3 mvg create \
  <project-id> "Budget variance MVG" \
  --description "Initial graph scope for variance analysis" \
  --question-id <question-id> \
  --concept-id metric:budget_variance \
  --concept-id department:sales

kdaf --metadata-store .kdaf/v02-demo.sqlite3 mvg get <mvg-id>
```

Competency questions are metadata inputs for designing the starter MVG. They solve the blank-canvas
problem in the same spirit that business questions guide DWH model design. KDAF does not store
competency questions as Neo4j nodes and does not create direct question-to-concept graph edges. The
MVG artifact records source question IDs and starter concept IDs so extraction workflows can grow the
knowledge graph from documents and domain material.

Inspect and load the canonical starter question catalog:

```bash
kdaf --metadata-store .kdaf/v02-demo.sqlite3 starter-questions catalog
kdaf --metadata-store .kdaf/v02-demo.sqlite3 starter-questions load <project-id>
```

The starter catalog includes canonical budget-vs-actuals, forecast movement, department spend,
revenue driver, and variance questions. Each catalog entry includes the expected DWH dependencies
and expected graph concept IDs. Loading the catalog creates project competency-question metadata and
MVG artifacts, and it is repeatable: existing starter questions and MVGs are reused instead of
duplicated.

Load the v0.3 FP&A starter DWH seed into a local DWH store:

```bash
kdaf --metadata-store .kdaf/v02-demo.sqlite3 starter-dwh load
kdaf --metadata-store .kdaf/v02-demo.sqlite3 starter-dwh facts
```

The starter DWH includes Postgres SQL artifacts for the canonical schema, seed data, and sample
queries. The CLI uses a dedicated local DWH store by default at `.kdaf/starter_dwh.sqlite3` so
starter financial facts remain outside the metadata repository.

Load the v0.3 FP&A starter graph into Neo4j:

```bash
docker compose up -d --wait neo4j
kdaf --metadata-store .kdaf/v02-demo.sqlite3 starter-graph load
kdaf --metadata-store .kdaf/v02-demo.sqlite3 starter-graph inspect
```

Open Neo4j Browser at `http://localhost:7474` and inspect the seeded semantic context:

```cypher
MATCH path = (:FinanceDomain {id: 'domain:fpna_starter'})-[:HAS_CONCEPT]->(:SemanticConcept)
RETURN path
LIMIT 50;
```

The graph seed uses stable concept IDs such as `account:revenue`, `department:sales`, and
`scenario:actual`. Concept nodes link to DWH dimensions through `REFERENCES_DWH_DIMENSION`; they do
not duplicate financial fact rows in Neo4j.

Call the tool server with JSON-line requests:

```bash
printf '{"tool":"health","arguments":{}}\n' \
  | kdaf-tool-server --metadata-store .kdaf/v02-demo.sqlite3

printf '{"tool":"project.create","arguments":{"name":"Agent Project"}}\n' \
  | kdaf-tool-server --metadata-store .kdaf/v02-demo.sqlite3

printf '{"tool":"competency_question.create","arguments":{"project_id":"<project-id>","question_text":"Where is actual spend over budget this quarter?"}}\n' \
  | kdaf-tool-server --metadata-store .kdaf/v02-demo.sqlite3

printf '{"tool":"mvg.create","arguments":{"project_id":"<project-id>","name":"Budget variance MVG","question_ids":["<question-id>"],"concept_ids":["metric:budget_variance","department:sales"]}}\n' \
  | kdaf-tool-server --metadata-store .kdaf/v02-demo.sqlite3

printf '{"tool":"starter_questions.catalog","arguments":{}}\n' \
  | kdaf-tool-server --metadata-store .kdaf/v02-demo.sqlite3

printf '{"tool":"starter_questions.load","arguments":{"project_id":"<project-id>"}}\n' \
  | kdaf-tool-server --metadata-store .kdaf/v02-demo.sqlite3

printf '{"tool":"starter_kit.load","arguments":{"project_id":"<project-id>"}}\n' \
  | kdaf-tool-server --metadata-store .kdaf/v02-demo.sqlite3

printf '{"tool":"starter_dwh.load","arguments":{}}\n' \
  | kdaf-tool-server --metadata-store .kdaf/v02-demo.sqlite3

printf '{"tool":"starter_graph.load","arguments":{}}\n' \
  | kdaf-tool-server --metadata-store .kdaf/v02-demo.sqlite3
```

Tool-server success responses use `{"ok": true, "result": ...}`. Errors use
`{"ok": false, "error": {"code": "...", "message": "..."}}`, including malformed JSON lines and
invalid tool requests.

## v0.6 Evaluation Harness

After creating a project and loading the starter kit, run all starter-question evaluations with the
same local metadata and financial DWH stores:

```bash
kdaf \
  --metadata-store .kdaf/v06-metadata.sqlite3 \
  --dwh-store .kdaf/v06-financial-dwh.sqlite3 \
  eval run <project-id> --offline-graph
```

The runner evaluates retrieval context, grounded financial evidence, provenance completeness,
answer citations, unsupported-claim refusal, and graph validation state. Every case is stored in the
metadata database. A failed case has `status: "error"` and a stable `error` object; it does not stop
the remaining cases.

Inspect stored results:

```bash
kdaf --metadata-store .kdaf/v06-metadata.sqlite3 eval list --run-id <run-id>
kdaf --metadata-store .kdaf/v06-metadata.sqlite3 eval get <evaluation-result-id>
```

Agents use the same core service through `eval.run`, `eval.list`, and `eval.get`:

```bash
printf '%s\n' \
  '{"tool":"eval.run","arguments":{"project_id":"<project-id>","dwh_store_path":".kdaf/v06-financial-dwh.sqlite3","offline_graph":true}}' \
  | kdaf-tool-server --metadata-store .kdaf/v06-metadata.sqlite3
```

`--offline-graph` uses the packaged semantic seed for repeatable local evaluation. Omit it to query
Neo4j. Financial facts are always read from the separate DWH and are never persisted in Neo4j or in
evaluation metadata.

Run the public FP&A benchmark baseline:

```bash
kdaf --metadata-store .kdaf/v06-metadata.sqlite3 \
  --dwh-store .kdaf/v06-financial-dwh.sqlite3 \
  eval benchmark <project-id> --offline-graph
```

Use `kdaf eval catalog` to inspect its seven versioned cases and rubric. See the
[FP&A benchmark guide](docs/fpna-benchmark-v0.6.md) for coverage, expected evidence, grading, and
case selection. The matching agent tools are `eval.catalog` and `eval.benchmark`.

Run the complete v0.6 public demo without Docker or an external model:

```bash
python scripts/run_public_demo.py \
  --metadata-store .kdaf/public-demo-metadata.sqlite3 \
  --dwh-store .kdaf/public-demo-financial-dwh.sqlite3 \
  --graph-store .kdaf/public-demo-graph.sqlite3 \
  --project-name "KDAF v0.6 Public Demo" \
  --offline-graph
```

The demo creates a project, loads the starter kit, retrieves CARP context, builds an evidence
packet, generates a cited answer, verifies refusal, and records evaluation-ready metadata. See the
[public demo tutorial](docs/public-demo-v0.6.md) for expected output and troubleshooting. The same
shared workflow is exposed as `kdaf public-demo` and `public_demo.run`.

## v0.4 Extraction and Validation Demo

The source-to-review vertical slice uses the sample file at `examples/v04_actuals.csv`. Choose
separate local files for metadata, extracted financial rows, and graph context:

```bash
kdaf \
  --metadata-store .kdaf/v04-metadata.sqlite3 \
  --dwh-store .kdaf/v04-financial-dwh.sqlite3 \
  --graph-store .kdaf/v04-graph.sqlite3 \
  source register "January actuals" examples/v04_actuals.csv
```

Copy the returned source `id`, then extract and inspect its provenance:

```bash
kdaf --metadata-store .kdaf/v04-metadata.sqlite3 \
  --dwh-store .kdaf/v04-financial-dwh.sqlite3 \
  --graph-store .kdaf/v04-graph.sqlite3 source extract <source-id>

kdaf --metadata-store .kdaf/v04-metadata.sqlite3 \
  --dwh-store .kdaf/v04-financial-dwh.sqlite3 \
  --graph-store .kdaf/v04-graph.sqlite3 provenance get <extraction-id>
```

Queue the extraction for expert review. A comment moves it to `needs_changes`; it may then be
approved or rejected. Every action is timestamped in the returned `decisions` history.

```bash
kdaf --metadata-store .kdaf/v04-metadata.sqlite3 \
  validation enqueue extraction <extraction-id>
kdaf --metadata-store .kdaf/v04-metadata.sqlite3 \
  validation comment <validation-id> --reviewer controller --comment "Recheck totals"
kdaf --metadata-store .kdaf/v04-metadata.sqlite3 \
  validation approve <validation-id> --reviewer controller --comment "Totals reconcile"
kdaf --metadata-store .kdaf/v04-metadata.sqlite3 validation list --status approved
```

The same workflow is available to agents through `source.register`, `source.extract`,
`source.extractions`, `provenance.get`, `validation.enqueue`, `validation.list`, `validation.get`,
`validation.comment`, `validation.approve`, and `validation.reject` tools. For example:

```bash
printf '%s\n' \
  '{"tool":"validation.approve","arguments":{"id":"<validation-id>","reviewer":"controller"}}' \
  | kdaf-tool-server --metadata-store .kdaf/v04-metadata.sqlite3
```

See [the v0.4 lifecycle contract](docs/provenance-validation-contract-v0.4.md) for fields, state
transitions, audit expectations, and storage-boundary details.

## v0.5 DWH-Aware CARP and Grounded Answers

v0.5 joins the starter competency questions to semantic context and warehouse facts without
blurring storage ownership. Load a project, its starter questions, and its separate DWH, then create
a run. Use the returned budget-vs-actual competency-question ID and run ID below:

```bash
kdaf --metadata-store .kdaf/v05-metadata.sqlite3 \
  --dwh-store .kdaf/v05-financial-dwh.sqlite3 dwh query budget_vs_actuals

kdaf --metadata-store .kdaf/v05-metadata.sqlite3 \
  carp retrieve <question-id>

kdaf --metadata-store .kdaf/v05-metadata.sqlite3 \
  --dwh-store .kdaf/v05-financial-dwh.sqlite3 \
  evidence build <question-id> <run-id>
```

`carp retrieve` uses Neo4j by default. Pass `--offline-graph` only for the bundled local demo; it
reads the same semantic seed model used to populate Neo4j. Evidence packets include addressable DWH
rows, graph nodes and relationships, provenance links, validation decisions, question/project/run
IDs, and build metadata.

Generate an answer from a saved evidence packet:

```bash
kdaf --metadata-store .kdaf/v05-metadata.sqlite3 \
  answer generate evidence.json
```

The default deterministic provider makes the demo repeatable without network access. Use
`--provider ollama --model <model>` for local Ollama, or `--provider openai-compatible --base-url
<url> --model <model>` for a compatible endpoint. KDAF accepts an answer as grounded only when all
citations resolve to entries in the supplied packet; otherwise it returns
`insufficiently_supported`.

Run the complete public vertical slice, including an explicit unsupported-claim refusal:

```bash
kdaf --metadata-store .kdaf/v05-metadata.sqlite3 \
  --dwh-store .kdaf/v05-financial-dwh.sqlite3 \
  grounded-demo <question-id> <run-id> --offline-graph
```

Agent equivalents are `dwh.query`, `carp.retrieve`, `evidence.build`, `answer.generate`, and
`grounded_answer.demo`. See [the v0.5 contract](docs/carp-retrieval-contract-v0.5.md) for schemas,
error behavior, audit fields, provider rules, and the DWH/graph boundary.

## Local Services

Copy `.env.example` if you want to customize ports or credentials:

```bash
cp .env.example .env
docker compose up -d --wait
```

Default settings:

- Neo4j: `KDAF_NEO4J_URI=bolt://localhost:7687`, `KDAF_NEO4J_USER=neo4j`
- Metadata DB: `KDAF_METADATA_DB_HOST=localhost`, `KDAF_METADATA_DB_PORT=5432`, `KDAF_METADATA_DB_NAME=kdaf_metadata`
- Financial DWH: `KDAF_DWH_DB_HOST=localhost`, `KDAF_DWH_DB_PORT=5433`, `KDAF_DWH_DB_NAME=kdaf_financial_dwh`

Stop the stack:

```bash
docker compose down
```

## Developer Workflow

Format and lint:

```bash
ruff format .
ruff check .
```

Test:

```bash
pytest
pytest -m "not integration"
pytest -m integration
```

## Project Status

KDAF v0.5 adds controlled read-only DWH queries, CARP semantic retrieval, evidence packets,
Ollama/OpenAI-compatible grounded answer generation, citation validation, prompt/output auditing,
and a runnable question-to-cited-answer slice. It retains the v0.3 starter kit and v0.4 CSV
extraction, provenance, and expert-validation workflows.
