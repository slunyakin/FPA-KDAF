# Contributing to KDAF

Thank you for helping build KDAF.

## Contribution Path

1. Open or pick a GitHub issue that describes the proposed change.
2. Keep changes scoped to the issue and the current milestone.
3. Add or update tests for behavior that changes.
4. Run the static foundation test command before opening a pull request:

```bash
pytest -m "not integration"
```

5. Include the optional Docker integration result when the change touches local infrastructure:

```bash
pytest -m integration
```

## Development Setup

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
```

## Code Style

KDAF uses Ruff for linting and formatting:

```bash
ruff format .
ruff check .
```

## Architectural Guardrails

- Keep KDAF framework-neutral, global, reusable, and finance-focused.
- Keep Neo4j for semantic graph context.
- Keep Postgres metadata separate from the Postgres financial DWH.
- Do not store financial numbers in the graph.
