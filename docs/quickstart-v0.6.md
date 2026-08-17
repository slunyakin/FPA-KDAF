# KDAF v0.6 Quickstart

This path starts from a fresh clone and proves the complete local project-to-cited-answer workflow.
It does not require Docker, Neo4j, Postgres, or an external model provider.

## 1. Clone and install

```bash
git clone https://github.com/slunyakin/FPA-KDAF.git
cd FPA-KDAF
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
```

## 2. Run the static smoke tests

```bash
pytest -m smoke
```

Expected result: every selected smoke test passes. Docker is not used by this command.

## 3. Run the public demo

```bash
python scripts/run_public_demo.py \
  --metadata-store .kdaf/quickstart-metadata.sqlite3 \
  --dwh-store .kdaf/quickstart-financial-dwh.sqlite3 \
  --graph-store .kdaf/quickstart-graph.sqlite3 \
  --project-name "KDAF v0.6 Quickstart" \
  --offline-graph
```

Expected result: one JSON object with `ok: true`. Within `result`, verify:

- `starter_kit.status` is `loaded`
- `answer.status` is `grounded`
- `answer.citations` is non-empty
- `unsupported_claim.status` is `insufficiently_supported`
- `evaluation_result.status` is `passed`
- `architecture.graph_stores_financial_facts` is `false`

Generated IDs, timestamps, and evidence packet IDs vary between runs.

## 4. Inspect persisted evaluation metadata

Copy `evaluation_result.id` and `run.id` from the demo output:

```bash
kdaf --metadata-store .kdaf/quickstart-metadata.sqlite3 eval get <evaluation-result-id>
kdaf --metadata-store .kdaf/quickstart-metadata.sqlite3 eval list --run-id <run-id>
```

The evaluation record contains IDs and boolean grades. Financial values remain in the separate DWH.

## 5. Continue evaluating

- [Public demo tutorial](public-demo-v0.6.md): detailed output and troubleshooting
- [FP&A benchmark](fpna-benchmark-v0.6.md): seven public cases and grading rubric
- [Release readiness](release-readiness-v0.6.md): test baseline, Docker status, and limitations
- [Architecture](architecture-v0.6.md): storage ownership and shared service flow
- [Six-stage approach](six-stage-approach.md): why KDAF is needed and how the methodology works
- [Role-based guide](role-based-consumer-guide.md): adoption paths by responsibility

To use live Neo4j, start it with `docker compose up -d --wait neo4j` and omit `--offline-graph`.
Optional integration tests skip cleanly when Docker is unavailable.
