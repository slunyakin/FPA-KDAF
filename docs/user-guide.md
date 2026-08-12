# KDAF User Guide

This guide covers the current FP&A starter-kit capabilities. KDAF is still early, but it already
lets you run a local finance analytics foundation, load starter warehouse data, load a semantic graph,
and use business questions to define a minimum viable graph (MVG).

## What KDAF Lets You Do Today

KDAF helps you move from finance business questions to a small, inspectable analytics model:

1. Start local services for Neo4j and Postgres.
2. Create a project workspace.
3. Load starter FP&A warehouse data.
4. Run starter financial sample queries.
5. Load starter FP&A semantic concepts into Neo4j.
6. Inspect how graph concepts map to warehouse dimensions.
7. Capture competency questions as project metadata.
8. Create MVG artifacts from those questions.
9. Load a canonical starter question catalog.
10. Use the same capabilities through the CLI or the agent tool server.

The useful shape is:

```text
business question -> competency question -> MVG -> graph concepts -> DWH dependencies
```

Competency questions are design inputs. They are not stored as Neo4j nodes, and KDAF does not create
question-to-concept graph relationships. The graph stays focused on durable finance concepts.

## Install and Check the Project

Create a Python environment and install KDAF:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
```

Check that the local package works:

```bash
kdaf --metadata-store .kdaf/demo.sqlite3 health
```

Expected result: a JSON response with `status` set to `ok`.

## Start Local Services

Start the local service stack:

```bash
docker compose up -d --wait
```

Neo4j Browser should be available at:

```text
http://localhost:7474
```

Default local services:

| Service | Purpose | Default |
| --- | --- | --- |
| Neo4j | Semantic graph | `bolt://localhost:7687` |
| Postgres metadata DB | Future framework metadata service | `localhost:5432/kdaf_metadata` |
| Postgres financial DWH | Financial facts and measures | `localhost:5433/kdaf_financial_dwh` |
| SQLite metadata store | Current local project/MVG metadata | `.kdaf/demo.sqlite3` |

## Create a Project

Create a workspace for your FP&A demo or modeling effort:

```bash
kdaf --metadata-store .kdaf/demo.sqlite3 project create "FP&A Starter Demo"
```

Save the returned `id` as your project ID. You will use it when loading starter questions and MVGs.

List projects:

```bash
kdaf --metadata-store .kdaf/demo.sqlite3 project list
```

## Load the Starter Kit

The fastest path is to load the full starter kit into your project:

```bash
kdaf --metadata-store .kdaf/demo.sqlite3 starter-kit load <project-id>
```

This command loads:

- starter DWH dimensions and facts
- starter Neo4j graph concepts
- starter competency questions
- starter MVG artifacts

Expected result: a single JSON summary with `dwh`, `graph`, and `questions` sections.

If you are working without Neo4j, skip the graph layer explicitly:

```bash
kdaf --metadata-store .kdaf/demo.sqlite3 starter-kit load <project-id> --skip-graph
```

Repeated loads are idempotent. If the starter questions and MVGs already exist for the project,
KDAF returns `status: "already_loaded"` and tells you to clean the local stores before rebuilding
from scratch.

## Run the Demo Script

Use the demo script when you want one command that proves the starter vertical slice works:

```bash
python scripts/run_starter_kit_demo.py \
  --metadata-store .kdaf/demo.sqlite3 \
  --dwh-store .kdaf/starter_dwh.sqlite3
```

The demo script:

- creates a project
- loads the starter kit
- runs DWH sample facts
- lists starter competency questions
- lists MVG artifacts
- inspects graph context

Expected result: `{"ok": true, "result": ...}` with project, starter-kit, DWH, question, MVG, and
graph sections.

If Neo4j is not running, use:

```bash
python scripts/run_starter_kit_demo.py \
  --metadata-store .kdaf/demo.sqlite3 \
  --dwh-store .kdaf/starter_dwh.sqlite3 \
  --skip-graph
```

## Load Starter DWH Data

The full starter-kit command already loads this layer. Use these commands when you want to work with
the DWH layer directly.

Load the starter FP&A data warehouse seed:

```bash
kdaf --metadata-store .kdaf/demo.sqlite3 starter-dwh load
```

Expected result: row counts for starter entities, departments, accounts, periods, scenarios, and
facts.

Run the starter fact queries:

```bash
kdaf --metadata-store .kdaf/demo.sqlite3 starter-dwh facts
```

You should see JSON outputs for:

- budget vs actual revenue by month
- department spend for the sample period

This is intentionally warehouse data. KDAF does not put financial facts or time series values into
Neo4j.

## Load Starter Graph Concepts

The full starter-kit command already loads this layer unless you pass `--skip-graph`. Use these
commands when you want to work with the graph layer directly.

Load the FP&A starter graph into Neo4j:

```bash
kdaf --metadata-store .kdaf/demo.sqlite3 starter-graph load
```

Inspect the starter graph summary:

```bash
kdaf --metadata-store .kdaf/demo.sqlite3 starter-graph inspect
```

You should see semantic concepts such as:

- `account:revenue`
- `department:sales`
- `scenario:actual`
- `scenario:budget`
- `metric:budget_vs_actuals`
- `metric:department_spend`

In Neo4j Browser, inspect the graph:

```cypher
MATCH path = (:FinanceDomain {id: 'domain:fpna_starter'})-[:HAS_CONCEPT]->(:SemanticConcept)
RETURN path
LIMIT 50;
```

Inspect warehouse dimension mappings:

```cypher
MATCH (concept:SemanticConcept)-[:REFERENCES_DWH_DIMENSION]->(dimension:DwhDimension)
RETURN concept.id, concept.name, dimension.table, dimension.key, dimension.value
ORDER BY concept.id;
```

## Capture a Competency Question

Create a finance question as project metadata:

```bash
kdaf --metadata-store .kdaf/demo.sqlite3 competency-question create \
  <project-id> "Where is actual revenue above or below budget by month?" \
  --business-context "Monthly budget-to-actual review"
```

Expected result: a competency question record with an `id`, `project_id`, `question_text`, and
`business_context`.

This question is not inserted into Neo4j. It is a modeling input.

## Create an MVG

Create a minimum viable graph artifact from a competency question:

```bash
kdaf --metadata-store .kdaf/demo.sqlite3 mvg create \
  <project-id> "Budget vs Actuals MVG" \
  --description "Starter graph scope for budget-to-actual review" \
  --question-id <question-id> \
  --concept-id metric:budget_vs_actuals \
  --concept-id metric:variance \
  --concept-id account:revenue \
  --concept-id scenario:actual \
  --concept-id scenario:budget
```

Expected result: an MVG artifact with source `question_ids` and starter `concept_ids`.

The MVG gives extraction and modeling workflows a starting scope. It answers: “which concepts should
we care about first?” It does not claim the graph is complete.

## Use the Starter Question Catalog

The full starter-kit command already loads this catalog into project metadata. Use these commands
when you want to inspect or load the question layer directly.

Inspect the packaged starter catalog:

```bash
kdaf --metadata-store .kdaf/demo.sqlite3 starter-questions catalog
```

The catalog currently includes questions for:

- budget vs actuals
- forecast movement
- department spend
- revenue drivers
- variance analysis

Each catalog entry includes expected DWH dependencies and expected graph concept IDs.

Load the catalog into your project:

```bash
kdaf --metadata-store .kdaf/demo.sqlite3 starter-questions load <project-id>
```

Expected result: KDAF creates competency-question metadata and MVG artifacts for the project.
The loader is idempotent: running it again reuses existing starter questions and MVGs instead of
creating duplicates.

## Use the Tool Server

Agents can use the same capabilities through JSON-line requests:

```bash
printf '{"tool":"starter_questions.catalog","arguments":{}}\n' \
  | kdaf-tool-server --metadata-store .kdaf/demo.sqlite3
```

Load starter questions:

```bash
printf '{"tool":"starter_questions.load","arguments":{"project_id":"<project-id>"}}\n' \
  | kdaf-tool-server --metadata-store .kdaf/demo.sqlite3
```

Load the full starter kit:

```bash
printf '{"tool":"starter_kit.load","arguments":{"project_id":"<project-id>"}}\n' \
  | kdaf-tool-server --metadata-store .kdaf/demo.sqlite3
```

Skip graph loading through the tool server:

```bash
printf '{"tool":"starter_kit.load","arguments":{"project_id":"<project-id>","include_graph":false}}\n' \
  | kdaf-tool-server --metadata-store .kdaf/demo.sqlite3
```

Create an MVG:

```bash
printf '{"tool":"mvg.create","arguments":{"project_id":"<project-id>","name":"Budget vs Actuals MVG","question_ids":["<question-id>"],"concept_ids":["metric:budget_vs_actuals","scenario:actual","scenario:budget"]}}\n' \
  | kdaf-tool-server --metadata-store .kdaf/demo.sqlite3
```

Tool-server success responses use:

```json
{"ok": true, "result": {}}
```

Errors use:

```json
{"ok": false, "error": {"code": "...", "message": "..."}}
```

## Troubleshooting

If Docker is not running, live Neo4j and Docker smoke tests will skip or fail. Start Docker Desktop
or your Docker daemon, then rerun the command.

If Neo4j load fails, check that the `neo4j` service is healthy:

```bash
docker compose ps neo4j
```

If a command returns `not_found`, confirm that you are passing the correct project, question, or MVG
ID from the same metadata store file.

If expected metadata disappears between runs, check the `--metadata-store` path. Different store
paths are separate local workspaces.

## Current Limits

KDAF does not yet provide:

- document ingestion or extraction from real FP&A files
- provenance links across metadata, DWH, and graph
- human validation queues
- retrieval over graph context and DWH facts
- grounded natural-language answer generation
- evaluation benchmarks

Those are planned follow-on slices. The current value is the reusable starter foundation: local
services, starter financial data, starter semantic graph, starter questions, and MVG scoping.
