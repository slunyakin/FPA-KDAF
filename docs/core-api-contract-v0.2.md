# KDAF v0.2 Shared Core API Contract

KDAF v0.2 keeps human CLI commands and MCP-style agent tools behind the same core service
boundary. The `kdaf.cli` and `kdaf.tool_server` modules are adapters only; framework behavior
lives in `kdaf.core.KdafCore` and `kdaf.metadata.MetadataRepository`.

## Shared APIs

- `KdafCore.health()` returns a stable health payload with `status`, `service`, and `version`.
- `KdafCore.config_summary()` returns a non-secret runtime summary. Passwords and connection URLs
  are intentionally excluded.
- `KdafCore.create_project(name, description)`, `list_projects()`, and `get_project(project_id)`
  own project metadata behavior.
- `KdafCore.create_run(project_id, status)`, `list_runs(project_id)`, and `get_run(run_id)` own run
  metadata behavior.
- `MetadataRepository.initialize_schema()` owns schema creation and records the local schema version.

## Stable v0.2 Interfaces

- CLI commands emit JSON with sorted keys and newline termination.
- Tool server requests accept JSON lines using either `{"tool": "...", "arguments": {...}}` or the
  MCP-style `{"method": "tools/call", "params": {"name": "...", "arguments": {...}}}` shape.
- Tool server responses use `{"ok": true, "result": ...}` or `{"ok": false, "error": "..."}`.
- Project and run records expose string IDs, ISO-8601 UTC `created_at` timestamps, and stable field
  names.
- The metadata store defaults to `.kdaf/metadata.sqlite3` and can be overridden with
  `KDAF_METADATA_STORE_PATH`, `--metadata-store`, or direct `KdafCore` construction.

## Error Model

Core-facing adapters catch `KdafError` and convert it to their transport format. Repository-specific
failures use `MetadataError` internally and are normalized by `KdafCore`. v0.2 does not expose typed
error codes yet.

## Stubbed Areas

- SQLite is the v0.2 local metadata implementation. The existing Postgres metadata service remains
  configured but is not used by the repository yet.
- Audit logs, source registry, validation queue, and evaluation results have schema extension tables
  but no service methods.
- Tool metadata is intentionally minimal: tools are discoverable by name, with schemas deferred to a
  later MCP-compliance milestone.
- Authentication, authorization, and remote multi-user state are out of scope for v0.2.

## Extension Points

- New CLI commands and agent tools should add behavior to `KdafCore` first, then expose thin adapter
  methods.
- Plugin and agent integrations should call the tool server or import `KdafCore`; they should not
  write directly to the metadata database.
- Future repository implementations can replace `MetadataRepository` behind the same project/run
  methods when Postgres-backed persistence is introduced.
- Additional metadata domains should follow the schema pattern already reserved for audit logs,
  source registry records, validation queue items, and evaluation results.

## Local Parity Sequence

Create a project through the CLI:

```bash
kdaf --metadata-store .kdaf/v02-demo.sqlite3 project create "Demo Project"
```

Read it through the tool server by passing the returned project ID:

```bash
printf '{"tool":"project.get","arguments":{"id":"<project-id>"}}\n' \
  | kdaf-tool-server --metadata-store .kdaf/v02-demo.sqlite3
```

Create a project through the tool server:

```bash
printf '{"tool":"project.create","arguments":{"name":"Agent Project"}}\n' \
  | kdaf-tool-server --metadata-store .kdaf/v02-demo.sqlite3
```

Read it through the CLI:

```bash
kdaf --metadata-store .kdaf/v02-demo.sqlite3 project get <project-id>
```

Both paths use the same SQLite metadata file and the same `KdafCore` project APIs.
