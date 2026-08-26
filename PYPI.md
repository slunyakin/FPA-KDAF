# KDAF

KDAF is a local-first, finance-focused Knowledge-Driven Analytics Framework. It combines governed
semantic context with financial warehouse evidence so an answer can cite what supports it—or refuse
a claim that the available evidence does not support.

## Install and run the offline evaluation

KDAF supports Python 3.11 through 3.14. The base package uses SQLite and the Python standard library
for its complete offline evaluation path.

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install kdaf
kdaf public-demo "My FP&A Trial" --offline-graph
```

The demo creates a project, loads a small FP&A starter model, retrieves packaged semantic context,
queries a separate local financial DWH, builds an evidence packet, produces a cited answer, refuses
an unsupported claim, and stores a passing or failing evaluation result.

By default, local state is stored under `.kdaf/` in the current directory:

- `metadata.sqlite3` stores projects, runs, audit events, validation state, and evaluations;
- `starter_dwh.sqlite3` stores the starter financial facts used by the demo;
- `extraction_dwh.sqlite3` is created when local extraction workflows persist financial rows; and
- `graph_context.sqlite3` is created when local provenance workflows persist semantic references,
  never financial facts.

Repeated demo runs append distinct projects, runs, and evaluations. They do not silently replace an
existing project. Uninstalling KDAF does not delete the `.kdaf/` directory.

## Use KDAF from Python

```python
from kdaf import KdafCore

kdaf = KdafCore()
result = kdaf.run_public_demo("Embedded FP&A Trial", offline_graph=True)

print(result["answer"]["answer"])
print(result["answer"]["citations"])
print(result["unsupported_claim"]["status"])
```

`KdafCore` is the shared service facade behind the Python API, CLI, scripts, and tool server.

## Use the tool server

The `kdaf-tool-server` command provides KDAF's machine-readable JSON-line interface:

```bash
printf '{"tool":"health","arguments":{}}\n' | kdaf-tool-server
```

This is an MCP-style JSON-line protocol, not yet a fully compliant MCP server with complete tool
discovery schemas.

## Optional live integrations

The offline path does not require external database drivers. Install only the live integrations you
need:

```bash
python -m pip install "kdaf[neo4j]"
python -m pip install "kdaf[postgres]"
python -m pip install "kdaf[all]"
```

Selecting a live adapter without its driver returns an actionable error naming the required extra.
Neo4j and Postgres must still be provisioned and configured separately.

## Upgrade, pin, and uninstall

```bash
python -m pip install --upgrade kdaf
python -m pip install "kdaf==0.6.0"
python -m pip uninstall kdaf
```

Pin an exact version in reproducible environments. Review release notes before upgrading a pre-1.0
installation.

## Boundaries

KDAF is ready for public local evaluation and early-adopter inspection. It is not a production
deployment template. Identity, authorization, multi-tenancy, retention, monitoring, backup,
recovery, managed database provisioning, and deployment hardening remain adopter responsibilities.
A valid citation proves linkage to supplied evidence; it does not by itself prove that a source or
analysis is correct.

## Documentation

- [PyPI installation and release guide](https://github.com/slunyakin/FPA-KDAF/blob/main/docs/pypi-installation.md)
- [Architecture](https://github.com/slunyakin/FPA-KDAF/blob/main/docs/architecture-v0.6.md)
- [Public demo](https://github.com/slunyakin/FPA-KDAF/blob/main/docs/public-demo-v0.6.md)
- [FP&A benchmark](https://github.com/slunyakin/FPA-KDAF/blob/main/docs/fpna-benchmark-v0.6.md)
- [Release readiness](https://github.com/slunyakin/FPA-KDAF/blob/main/docs/release-readiness-v0.6.md)
- [Security policy](https://github.com/slunyakin/FPA-KDAF/blob/main/SECURITY.md)
- [Source and issue tracker](https://github.com/slunyakin/FPA-KDAF)

KDAF is licensed under the MIT License.
