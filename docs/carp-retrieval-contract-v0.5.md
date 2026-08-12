# CARP Retrieval, DWH, and Grounded Answer Contract v0.5

## Storage boundaries

Context-Aware Relevance Propagation (CARP) uses each store for one kind of responsibility:

- The separate financial DWH is the only source queried for financial facts, amounts, measures,
  and tabular analytical results. Its public service exposes allow-listed, parameterized,
  read-only queries. Arbitrary SQL and write operations are not part of the interface.
- Neo4j stores meaning, semantic concepts, relationships, relevance context, provenance links,
  and validation state. Neo4j must not store financial amounts, fact rows, or time-series values.
- The metadata database stores projects, runs, competency questions, workflow state, query audit
  metadata, evidence-packet audit metadata, and complete prompt/provider/output audit records.

The dependency-free local harness uses separate SQLite files for metadata and the starter financial
DWH, plus the packaged graph seed when `--offline-graph` is explicitly requested. The production
graph provider queries Neo4j. These adapters preserve the same ownership boundaries.

## CARP retrieval contract

Input is a stored competency-question ID. Relevance starts from the question's MVG concept IDs, or
from its canonical starter-question mapping when no MVG is present. Output always includes:

- `question_id`, `project_id`, and ordered `concept_ids`
- relevant metric and dimension nodes
- semantic relationships, including metric dependencies and DWH-dimension references
- source provenance links and applicable validation states
- a required `provenance` object identifying the provider, question, and retrieval time

Unknown question or concept IDs return a stable `not_found` error. Neo4j connection failures return
`graph_unavailable` without returning credentials, connection strings, paths, or stack traces.

## Read-only DWH contract

`dwh query` and `dwh.query` accept a named query and a JSON object of parameters. Query definitions
are controlled by KDAF, use bound parameters, begin with `SELECT` or `WITH`, and are executed using a
read-only database connection. Unknown queries return `not_found`; unexpected parameters return
`invalid_parameter`; an unloaded store returns `dwh_not_loaded`.

Without an explicit local DWH store path, the shared core uses the configured Postgres DWH and sets
both the connection's `default_transaction_read_only` option and `SET TRANSACTION READ ONLY` before
executing the allow-listed query. Supplying a DWH store path selects the SQLite local harness.

Every successful execution returns and audits the query ID, a statement fingerprint, bound
parameters, row count, duration, execution time, store name, and read-only mode. Financial rows are
returned from the DWH but are not copied into the graph or into DWH-query audit metadata.

## Evidence packet schema

An evidence packet binds one competency question and one run from the same project. It references:

- `project_id`, `run_id`, and `competency_question_id`
- DWH query executions and addressable financial-fact entries
- graph nodes and relationships
- source records through provenance-link IDs
- validation decisions and their IDs
- build time and a complete provenance summary

Each entry has a stable packet-local address used by grounded answers as
`[evidence:<entry-id>]`. Packets are data artifacts; the metadata database records packet audit
metadata, not a duplicate copy of warehouse facts.

## Grounded answer contract

The answer service accepts an evidence packet. Provider choices are the deterministic offline demo,
Ollama's native API, and an OpenAI-compatible chat-completions endpoint. The prompt requires every
factual claim to cite an evidence entry. Output is accepted as `grounded` only when it contains at
least one citation and every citation resolves to an entry in the supplied packet. Otherwise KDAF
returns `insufficiently_supported` and does not pass through the unsupported provider claim.

For every attempt, the metadata audit log captures prompt, model, provider, parameters, final
output, status, evidence packet ID, project ID, and run ID. API keys are neither returned nor logged.
Provider and server failures use stable error envelopes and omit configuration details.

## Public surfaces

CLI commands:

```text
kdaf dwh query <query-id> [--parameters-json '{}']
kdaf carp retrieve <question-id> [--offline-graph]
kdaf evidence build <question-id> <run-id> [--offline-graph]
kdaf answer generate <evidence.json> [--provider ...] [--model ...]
kdaf grounded-demo <question-id> <run-id> [--offline-graph]
```

Tool-server equivalents are `dwh.query`, `carp.retrieve`, `evidence.build`, `answer.generate`, and
`grounded_answer.demo`. Both surfaces call the same `KdafCore` services and return the existing
machine-readable error shape.
