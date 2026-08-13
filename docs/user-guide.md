# KDAF User Guide

This guide covers the v0.3 FP&A starter kit, v0.4 extraction and validation, v0.5 DWH-aware
retrieval and grounded answers, and the v0.6 evaluation harness. KDAF supports model design,
governed ingestion, auditable question-to-answer workflows, and repeatable quality measurement
while keeping semantic context separate from financial facts.

For a view organized around consumer responsibilities and outcomes, see
[How KDAF Helps Each Role](role-based-consumer-guide.md).

## v0.3 and v0.4 at a Glance

v0.4 builds on v0.3; it does not replace it.

| Version | Primary user goal | Main capabilities | Typical output |
| --- | --- | --- | --- |
| v0.3 | Learn, prototype, and scope an FP&A analytics model | Starter DWH, starter semantic graph, competency questions, question catalog, MVGs, starter-kit loader and demo | A project with sample finance facts, semantic concepts, business questions, and an MVG scope |
| v0.4 | Ingest and govern a structured finance source | CSV source registry, extraction batches, DWH row loading, cross-store provenance, validation queue, reviewer decisions and audit history | A traceable source-to-DWH extraction with an approved, rejected, or needs-changes review state |

The two workflows answer different questions:

- v0.3 asks: **What finance question are we solving, and what concepts and DWH dependencies are
  needed?**
- v0.4 asks: **Where did this imported data come from, what was extracted, and has an expert
  reviewed it?**

Use v0.3 by itself when you are evaluating KDAF, teaching the architecture, prototyping an FP&A use
case, or defining an MVG before real source data is ready.

Use v0.4 by itself when you already have a CSV and mainly need repeatable ingestion, source lineage,
failure tracking, and an auditable human decision.

Use them together when you want the complete current workflow: use v0.3 to define the business
question and semantic scope, then use v0.4 to ingest and review the source data that will support
that work. In v0.4, this is a coordinated user workflow rather than an automatic project-to-source or
MVG-to-extraction link; keep the returned IDs and review context together in your operating process.

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
10. Register a structured finance CSV as a governed source.
11. Extract its rows into a separate DWH store.
12. Trace the extraction back to its source across metadata, DWH, and graph context.
13. Queue a source or extraction for expert validation.
14. Request changes, approve, or reject while retaining a timestamped decision history.
15. Use the same capabilities through the CLI or the agent tool server.
16. Run repeatable evaluations and inspect durable per-case metrics.

## Evaluate the Grounded Workflow

Load the starter kit, then evaluate every starter competency question:

```bash
kdaf --metadata-store .kdaf/demo.sqlite3 \
  --dwh-store .kdaf/starter_dwh.sqlite3 \
  eval run <project-id> --offline-graph
```

The JSON summary reports total, passed, and failed cases. Each stored result checks retrieval,
grounding, provenance, citations, unsupported-claim refusal, and validation completeness. Use
`eval list --run-id <run-id>` or `eval get <evaluation-result-id>` to inspect the durable metadata.
Case errors use a stable `{"code": "...", "message": "..."}` shape and do not terminate the run.

The useful shape is:

```text
business question -> competency question -> MVG -> graph concepts -> DWH dependencies
```

The v0.4 governance path adds:

```text
CSV source -> extraction batch -> DWH rows -> provenance -> validation -> expert decision
```

Used together, these paths provide design intent on one side and governed source evidence on the
other. They are not yet joined automatically by a single project workflow.

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
| SQLite extraction DWH adapter | Current local v0.4 extracted CSV rows | `.kdaf/extraction_dwh.sqlite3` |
| SQLite graph provenance adapter | Current local v0.4 semantic provenance references | `.kdaf/graph_context.sqlite3` |

The v0.4 local adapters preserve KDAF's storage boundaries without requiring live database drivers.
Financial CSV values are stored only in the extraction DWH adapter. The graph provenance adapter
stores identifiers and relationships, never amounts or row payloads. The configured Postgres and
Neo4j services remain the production architecture boundaries.

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

## Register and Extract a CSV with v0.4

Use this workflow when you want to move from packaged starter data to a real structured source. The
repository includes `examples/v04_actuals.csv`, which you can use for a first run.

Choose three separate local stores. Reuse the same metadata store as your v0.3 project if you are
using both workflows together:

```bash
METADATA_STORE=.kdaf/demo.sqlite3
EXTRACTION_DWH=.kdaf/extraction_dwh.sqlite3
GRAPH_STORE=.kdaf/graph_context.sqlite3
```

Register the CSV:

```bash
kdaf \
  --metadata-store "$METADATA_STORE" \
  --dwh-store "$EXTRACTION_DWH" \
  --graph-store "$GRAPH_STORE" \
  source register "January actuals" examples/v04_actuals.csv
```

Expected result: a source record with an `id`, name, `source_type: "csv"`, locator, metadata, and
timestamps. Save the returned ID as `<source-id>`.

Registration records intent and source metadata. It does not read the file yet, so a planned or
temporarily unavailable source can still be registered.

Extract the registered source:

```bash
kdaf \
  --metadata-store "$METADATA_STORE" \
  --dwh-store "$EXTRACTION_DWH" \
  --graph-store "$GRAPH_STORE" \
  source extract <source-id>
```

Expected result: a completed extraction with an `id`, row count, content hash, timestamps, and
provenance-link count. Save the extraction ID as `<extraction-id>`.

During extraction, KDAF:

- validates the CSV header and row shape
- creates a durable extraction attempt
- writes the CSV row values to the separate extraction DWH
- records source and batch references for the DWH batch and rows
- creates semantic provenance context without copying financial values into the graph
- records a safe failure code and message if the file is missing or malformed

Inspect sources and extraction attempts:

```bash
kdaf --metadata-store "$METADATA_STORE" source list
kdaf --metadata-store "$METADATA_STORE" source get <source-id>
kdaf --metadata-store "$METADATA_STORE" source extractions --source-id <source-id>
```

## Trace Source Provenance

Trace a successful extraction across the three stores:

```bash
kdaf \
  --metadata-store "$METADATA_STORE" \
  --dwh-store "$EXTRACTION_DWH" \
  --graph-store "$GRAPH_STORE" \
  provenance get <extraction-id>
```

Expected result: a combined response containing:

- the registered source and extraction status from metadata
- metadata provenance links to the DWH batch, DWH row IDs, and semantic context
- DWH row references and the source content hash
- graph context identifiers and a `DERIVED_FROM` relationship

The provenance response identifies DWH rows but does not return their financial values from the
graph. This preserves the rule that financial numbers belong in the DWH, not Neo4j.

## Validate a Source or Extraction

Queue the completed extraction for expert review:

```bash
kdaf --metadata-store "$METADATA_STORE" \
  validation enqueue extraction <extraction-id>
```

You can instead review the source registration itself:

```bash
kdaf --metadata-store "$METADATA_STORE" \
  validation enqueue source <source-id>
```

Expected result: a validation item in `pending` state. Save its ID as `<validation-id>`.

Request corrections or more evidence:

```bash
kdaf --metadata-store "$METADATA_STORE" \
  validation comment <validation-id> \
  --reviewer controller \
  --comment "Recheck the source total against the close package"
```

This moves the item to `needs_changes`. Additional comments can keep it in that state. From
`pending` or `needs_changes`, approve it:

```bash
kdaf --metadata-store "$METADATA_STORE" \
  validation approve <validation-id> \
  --reviewer controller \
  --comment "Source total reconciles"
```

Or reject it:

```bash
kdaf --metadata-store "$METADATA_STORE" \
  validation reject <validation-id> \
  --reviewer controller \
  --comment "Source is not authoritative"
```

Inspect the queue and decision history:

```bash
kdaf --metadata-store "$METADATA_STORE" validation get <validation-id>
kdaf --metadata-store "$METADATA_STORE" validation list
kdaf --metadata-store "$METADATA_STORE" validation list --status approved
```

Every enqueue, comment, approval, and rejection appends a timestamped decision. `approved` and
`rejected` are terminal states; KDAF rejects attempts to reopen them.

## Use v0.3 and v0.4 Together

A practical combined workflow for a budget-versus-actuals use case is:

1. Create a project and load the v0.3 starter kit.
2. Select or create the budget-versus-actuals competency question.
3. Inspect its MVG to confirm the required concepts and DWH dependencies.
4. Register the actuals CSV with v0.4.
5. Extract it into the separate DWH adapter.
6. Inspect provenance to confirm which source and rows produced the extraction.
7. Queue the extraction for controller review.
8. Resolve comments and obtain an approved or rejected decision.

This combination is useful for a proof of concept, controlled data onboarding, or demonstrating how
business intent, semantic context, numerical data, source lineage, and human governance fit together.

Today, project/MVG records and source/extraction records coexist in the metadata store but do not
have a direct persisted association. Put the project ID, relevant question or MVG ID, source ID, and
extraction ID in your runbook or validation payload when you need that operational link:

```bash
kdaf --metadata-store "$METADATA_STORE" \
  validation enqueue extraction <extraction-id> \
  --payload-json '{"project_id":"<project-id>","mvg_id":"<mvg-id>","review_scope":"budget_vs_actuals"}'
```

Automatic project-to-source and MVG-to-extraction relationships are follow-on work.

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

Register and extract a v0.4 source:

```bash
printf '{"tool":"source.register","arguments":{"name":"January actuals","locator":"examples/v04_actuals.csv"}}\n' \
  | kdaf-tool-server \
      --metadata-store .kdaf/demo.sqlite3 \
      --dwh-store .kdaf/extraction_dwh.sqlite3 \
      --graph-store .kdaf/graph_context.sqlite3

printf '{"tool":"source.extract","arguments":{"id":"<source-id>"}}\n' \
  | kdaf-tool-server \
      --metadata-store .kdaf/demo.sqlite3 \
      --dwh-store .kdaf/extraction_dwh.sqlite3 \
      --graph-store .kdaf/graph_context.sqlite3
```

Queue and approve an extraction:

```bash
printf '{"tool":"validation.enqueue","arguments":{"subject_type":"extraction","subject_id":"<extraction-id>"}}\n' \
  | kdaf-tool-server --metadata-store .kdaf/demo.sqlite3

printf '{"tool":"validation.approve","arguments":{"id":"<validation-id>","reviewer":"controller","comment":"Source total reconciles"}}\n' \
  | kdaf-tool-server --metadata-store .kdaf/demo.sqlite3
```

The complete v0.4 tool set is `source.register`, `source.list`, `source.get`, `source.extract`,
`source.extractions`, `provenance.get`, `validation.enqueue`, `validation.list`, `validation.get`,
`validation.comment`, `validation.approve`, and `validation.reject`.

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

If a command returns `not_found`, confirm that you are passing the correct project, question, MVG,
source, extraction, or validation ID from the same metadata store file.

If expected metadata disappears between runs, check the `--metadata-store` path. Different store
paths are separate local workspaces.

If `source extract` returns `source_file_not_found`, confirm that the registered locator is still
reachable from your current working directory. Registration can succeed before the file exists.

If `provenance get` cannot find its DWH or graph records, pass the same `--dwh-store` and
`--graph-store` paths that you used for extraction.

If a validation transition returns `invalid_transition`, inspect the item first. Approved and
rejected items are terminal and cannot move back to pending or needs-changes.

## Retrieve Evidence and Generate an Answer with v0.5

First load the starter DWH and starter questions, then create a run. Keep the returned project,
budget-vs-actual question, and run IDs:

```bash
kdaf --metadata-store .kdaf/v05-metadata.sqlite3 project create "Grounded FP&A"
kdaf --metadata-store .kdaf/v05-metadata.sqlite3 \
  --dwh-store .kdaf/v05-financial-dwh.sqlite3 starter-dwh load
kdaf --metadata-store .kdaf/v05-metadata.sqlite3 starter-questions load <project-id>
kdaf --metadata-store .kdaf/v05-metadata.sqlite3 competency-question list \
  --project-id <project-id>
kdaf --metadata-store .kdaf/v05-metadata.sqlite3 run create <project-id> \
  --status retrieval
```

Inspect the controlled warehouse query and retrieve CARP context:

```bash
kdaf --metadata-store .kdaf/v05-metadata.sqlite3 \
  --dwh-store .kdaf/v05-financial-dwh.sqlite3 dwh query budget_vs_actuals
kdaf --metadata-store .kdaf/v05-metadata.sqlite3 carp retrieve <question-id>
```

The graph command uses Neo4j. For a Docker-free walkthrough, add `--offline-graph`; that adapter uses
the packaged semantic seed and never contains warehouse amounts.

Build the evidence packet and save the JSON output:

```bash
kdaf --metadata-store .kdaf/v05-metadata.sqlite3 \
  --dwh-store .kdaf/v05-financial-dwh.sqlite3 \
  evidence build <question-id> <run-id> --offline-graph > evidence.json

kdaf --metadata-store .kdaf/v05-metadata.sqlite3 answer generate evidence.json
```

The answer contains citations such as `[evidence:<entry-id>]`. A provider answer with missing or
unknown citations is replaced with an `insufficiently_supported` result. KDAF records the prompt,
provider, model, parameters, final output, packet ID, project ID, and run ID in metadata audit state.
API keys are not logged.

For one command that demonstrates graph retrieval, DWH execution, packet construction, a cited
answer, an unsupported-claim refusal, and the no-facts-in-graph boundary:

```bash
kdaf --metadata-store .kdaf/v05-metadata.sqlite3 \
  --dwh-store .kdaf/v05-financial-dwh.sqlite3 \
  grounded-demo <question-id> <run-id> --offline-graph
```

The tool server exposes the same workflow through `dwh.query`, `carp.retrieve`, `evidence.build`,
`answer.generate`, and `grounded_answer.demo`. All use the same core services as the CLI.

## Current Limits

KDAF does not yet provide:

- extractors for formats other than CSV
- automatic project-to-source, MVG-to-source, or MVG-to-extraction associations
- production Postgres/Neo4j persistence adapters for the v0.4 local extraction workflow
- production Postgres persistence for the local starter DWH query harness
- provider-specific retry, rate-limit, and streaming behavior
- evaluation benchmarks

Those are planned follow-on slices. The current value combines the reusable v0.3 modeling
foundation, v0.4 CSV ingestion and expert validation, and v0.5 DWH-aware retrieval, evidence
packets, citation enforcement, and grounded-answer auditing.
