# KDAF

KDAF is a Knowledge-Driven Analytics Framework for finance-focused analytical systems. It is a neutral, reusable foundation for combining semantic financial context with governed numerical analytics.

## Purpose

KDAF separates meaning from measures:

- Neo4j stores semantic graph context such as entities, relationships, taxonomy, lineage, definitions, and analytical concepts.
- A Postgres metadata database stores framework metadata such as jobs, datasets, ingestion state, and operational records.
- A separate Postgres data warehouse stores financial numbers, facts, measures, and tabular analytical outputs.

Financial numbers must not be stored in the graph. The graph explains what financial data means and how concepts relate; the DWH stores the numeric values used for analysis.

## Architecture

The v0.1 local runtime contains three backing services:

| Service | Purpose | Default local connection |
| --- | --- | --- |
| Neo4j | Semantic graph | `bolt://localhost:7687`, browser `http://localhost:7474` |
| Postgres metadata DB | Framework metadata | `localhost:5432/kdaf_metadata` |
| Postgres financial DWH | Financial numbers and facts | `localhost:5433/kdaf_financial_dwh` |

Configuration loads from built-in defaults, optionally from `config/kdaf.example.toml`, and then from `KDAF_*` environment variables.

## Local-First Posture

KDAF starts as a local-first framework. The default Docker Compose stack is suitable for development and smoke testing without depending on managed cloud services. Secrets in `.env.example` are development placeholders only.

## Non-Goals

- KDAF v0.1 is not a production deployment template.
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

KDAF is in v0.1 foundation scope: package scaffold, project identity, local infrastructure, typed configuration, and smoke tests.
