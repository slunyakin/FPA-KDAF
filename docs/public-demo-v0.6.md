# KDAF v0.6 Public Demo

This tutorial proves the complete local KDAF workflow from a new project to an evaluation-ready,
cited FP&A answer. The offline path requires no Docker or external model provider.

## Run it

From an installed development checkout:

```bash
python scripts/run_public_demo.py \
  --metadata-store .kdaf/public-demo-metadata.sqlite3 \
  --dwh-store .kdaf/public-demo-financial-dwh.sqlite3 \
  --graph-store .kdaf/public-demo-graph.sqlite3 \
  --project-name "KDAF v0.6 Public Demo" \
  --offline-graph
```

The equivalent CLI command is:

```bash
kdaf \
  --metadata-store .kdaf/public-demo-metadata.sqlite3 \
  --dwh-store .kdaf/public-demo-financial-dwh.sqlite3 \
  --graph-store .kdaf/public-demo-graph.sqlite3 \
  public-demo "KDAF v0.6 Public Demo" --offline-graph
```

Remove `--offline-graph` after starting Neo4j when you want to exercise the live semantic graph.

## Workflow and expected output

One invocation:

1. creates project metadata;
2. loads starter DWH facts, semantic graph context, questions, and MVGs;
3. creates a demo run;
4. retrieves CARP semantic context;
5. builds a DWH-backed evidence packet;
6. generates a deterministic answer with valid evidence citations;
7. verifies unsupported-claim refusal; and
8. stores evaluation-ready metrics in the metadata database.

A successful response has `ok: true`. Under `result`, expect `project`, `starter_kit`, `run`,
`question`, `carp_context`, `evidence_packet`, `answer`, `unsupported_claim`, `evaluation_result`, and
`architecture`. Generated IDs and timestamps vary. `answer.status` is `grounded`,
`answer.citations` is non-empty, `unsupported_claim.status` is `insufficiently_supported`, and
`evaluation_result.status` is `passed`.

Financial values appear only in DWH-backed evidence and the cited answer. The metadata result stores
IDs and boolean grades. Neo4j stores concepts, relationships, provenance links, and validation state,
not financial facts.

## Agent tool

The same core workflow is available as `public_demo.run`:

```bash
printf '%s\n' \
  '{"tool":"public_demo.run","arguments":{"project_name":"Agent Demo","dwh_store_path":".kdaf/public-demo-financial-dwh.sqlite3","offline_graph":true}}' \
  | kdaf-tool-server --metadata-store .kdaf/public-demo-metadata.sqlite3
```

## Troubleshooting

- `starter_dwh_not_loaded`: confirm the DWH path is writable and rerun the single demo command.
- `starter_graph_error` or `starter_graph_not_loaded`: use `--offline-graph`, or start Neo4j and
  verify the configured URI and credentials.
- `not_found` for a question category: use one of `budget_vs_actuals`, `forecast_movement`,
  `department_spend`, `revenue_driver`, or `variance`.
- Existing demo files are safe to reuse, but each invocation creates a new project and run. Use new
  file paths when you want a completely fresh demonstration.
- Errors always use `{"ok": false, "error": {"code": "...", "message": "..."}}`; server-side
  paths, credentials, and stack traces are not returned.
