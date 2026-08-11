# KDAF

KDAF is a Knowledge-Driven Analytics Framework for finance-focused analytical systems. It is a neutral, reusable foundation for combining semantic financial context with governed numerical analytics.

## Purpose

KDAF separates meaning from measures:

- Neo4j stores semantic graph context such as entities, relationships, taxonomy, lineage, definitions, and analytical concepts.
- A Postgres metadata database stores framework metadata such as jobs, datasets, ingestion state, and operational records.
- A separate Postgres data warehouse stores financial numbers, facts, measures, and tabular analytical outputs.

Financial numbers must not be stored in the graph. The graph explains what financial data means and how concepts relate; the DWH stores the numeric values used for analysis.

## Architecture

The v0.2 local runtime contains three backing services plus a local metadata store used by the CLI
and MCP-style tool server:

| Service | Purpose | Default local connection |
| --- | --- | --- |
| Neo4j | Semantic graph | `bolt://localhost:7687`, browser `http://localhost:7474` |
| Postgres metadata DB | Framework metadata | `localhost:5432/kdaf_metadata` |
| Postgres financial DWH | Financial numbers and facts | `localhost:5433/kdaf_financial_dwh` |
| SQLite metadata store | v0.2 project/run metadata | `.kdaf/metadata.sqlite3` |

Configuration loads from built-in defaults, optionally from `config/kdaf.example.toml`, and then from `KDAF_*` environment variables.

## Local-First Posture

KDAF starts as a local-first framework. The default Docker Compose stack is suitable for development and smoke testing without depending on managed cloud services. Secrets in `.env.example` are development placeholders only.

## Non-Goals

- KDAF v0.2 is not a production deployment template.
- KDAF does not prescribe a single finance domain model.
- KDAF does not store financial facts, measures, or time series values in Neo4j.
- KDAF does not require Docker for static tests or package development.

## Quick Start

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

printf '{"tool":"starter_dwh.load","arguments":{}}\n' \
  | kdaf-tool-server --metadata-store .kdaf/v02-demo.sqlite3

printf '{"tool":"starter_graph.load","arguments":{}}\n' \
  | kdaf-tool-server --metadata-store .kdaf/v02-demo.sqlite3
```

Tool-server success responses use `{"ok": true, "result": ...}`. Errors use
`{"ok": false, "error": {"code": "...", "message": "..."}}`, including malformed JSON lines and
invalid tool requests.

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

KDAF is moving through v0.3 FP&A starter-kit scope. The current public surface includes v0.1 local
infrastructure, typed configuration, shared core APIs, project/run metadata persistence, a CLI shell,
an MCP-style tool server, parity tests, a starter FP&A DWH schema with seed data and sample finance
queries, and a Neo4j-backed starter semantic graph for finance concepts.
