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

Call the tool server with JSON-line requests:

```bash
printf '{"tool":"health","arguments":{}}\n' \
  | kdaf-tool-server --metadata-store .kdaf/v02-demo.sqlite3

printf '{"tool":"project.create","arguments":{"name":"Agent Project"}}\n' \
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

KDAF is in v0.2 agent/tooling scope: v0.1 local infrastructure, typed configuration, shared core
APIs, project/run metadata persistence, a CLI shell, an MCP-style tool server, and parity tests.
