# Install and Release KDAF Through PyPI

This guide defines KDAF's installed-package path and the maintainer-controlled publication process.
The repository README is a protected research and project record; PyPI uses the dedicated
`PYPI.md` description instead.

## Consumer installation

Create an isolated environment and install the base package:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install kdaf
```

The base package supports the complete offline SQLite workflow:

```bash
kdaf public-demo "My FP&A Trial" --offline-graph
```

The command writes documented local state beneath `.kdaf/` in the current directory. Run it from a
dedicated working directory when you want each evaluation to have an isolated set of stores.
Repeated runs in the same directory append new projects, runs, audit events, and evaluations.

## Optional integrations

Install live database drivers only when required:

```bash
python -m pip install "kdaf[neo4j]"
python -m pip install "kdaf[postgres]"
python -m pip install "kdaf[all]"
```

The extras install client drivers. They do not provision Neo4j or Postgres. Configure services with
a KDAF TOML file or `KDAF_*` environment variables and continue to keep secrets outside source
control.

## Python and automation surfaces

Python applications import the shared facade:

```python
from kdaf import KdafCore

core = KdafCore()
result = core.run_public_demo("Application Trial", offline_graph=True)
```

Automation can call the `kdaf` CLI or start the JSON-line tool server:

```bash
printf '{"tool":"health","arguments":{}}\n' | kdaf-tool-server
```

CLI and tool-server results remain machine-readable JSON. Provider and database failures use stable
error codes and do not include credentials or connection strings.

## Version management

Pin a release for reproducible evaluation:

```bash
python -m pip install "kdaf==0.6.0"
```

Upgrade after reviewing the corresponding release notes:

```bash
python -m pip install --upgrade kdaf
```

Uninstalling the Python package leaves `.kdaf/` data in place. Remove or archive those files only
after applying your own retention requirements.

## Maintainer publication gates

Pull requests run supported-Python tests and package checks. The package job builds an sdist and
wheel, validates metadata, checks archive boundaries, and executes the installed package from a
clean environment outside the source tree.

The publication workflow supports two protected environments:

- `testpypi` is selected by a manual workflow dispatch for a rehearsal; and
- `pypi` is selected only by publishing a GitHub release whose tag matches the package version.

Both environments use PyPI Trusted Publishing through GitHub's OIDC identity. Do not add a PyPI API
token to repository secrets. The workflow builds once, verifies those artifacts, and passes the same
artifacts to the selected publisher.

Before the first release, a maintainer must:

1. confirm the `kdaf` project name remains available on PyPI and TestPyPI;
2. create accounts with MFA and configure pending Trusted Publisher records;
3. create protected GitHub environments named `testpypi` and `pypi`;
4. run the TestPyPI workflow and smoke-test the index-installed package;
5. publish an immutable version tag and matching GitHub release; and
6. install the pinned production version from PyPI and repeat the offline demo.

PyPI versions are immutable. If a candidate has already been uploaded to either index, increment the
version before retrying rather than attempting to overwrite it.

## Troubleshooting

- If the CLI cannot write `.kdaf/`, run it from a writable directory or provide explicit store paths.
- If a live adapter reports a missing driver, install the extra named in the error.
- If a live service is unavailable, verify its connection settings without printing credentials.
- If publication reports an existing version, create a new version; do not delete or replace an
  immutable release.
- If the protected README fingerprint changes, stop the release and move that change into a separate,
  explicitly approved review.

## Scope boundary

The package distributes KDAF's code and runtime resources. It does not operate a hosted service,
provision databases, or supply production identity, authorization, monitoring, backup, recovery, or
retention controls.
