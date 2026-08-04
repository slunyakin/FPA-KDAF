# KDAF v0.4 Provenance and Validation Lifecycle Contract

This contract defines the minimum durable source lineage and expert-review model. Public CLI and
tool-server adapters call `KdafCore`; they do not write to a backing store directly.

## Storage boundaries

| Boundary | Durable records | Explicitly excluded |
| --- | --- | --- |
| Postgres metadata DB | source registry, extraction status, provenance references, validation queue, decisions, audit events | extracted financial values |
| Separate Postgres DWH | extracted row values, batch/source reference, row number, content hash | validation workflow state |
| Neo4j | semantic context identifiers, `DERIVED_FROM` relationships, source and batch references | amounts, measures, row payloads, financial facts |

The dependency-free local runtime uses separate SQLite files as adapters for these three production
boundaries. Separation is physical: the metadata, DWH, and graph adapters never share a database
file. The graph schema has no value, amount, measure, or payload property.

## Source registry

A source record contains:

- `id`: stable UUID.
- `name`: human-readable required name.
- `source_type`: extractor selector; v0.4 supports `csv`.
- `locator`: local source location.
- `metadata`: JSON object for non-numeric ownership or classification metadata.
- `content_hash`: SHA-256 populated after a successful read.
- `created_at` and `updated_at`: ISO-8601 UTC timestamps.

Registration does not require the locator to be reachable. This permits workflows to register a
planned source. Extraction captures an unreachable or malformed source as a failed batch with a
safe `error_code` and `error_message`.

## Extracted artifacts and provenance

An extraction batch contains `id`, `source_id`, `status`, `row_count`, safe error fields,
`started_at`, and `completed_at`. Its state is `running`, `completed`, or `failed`.

On success, the DWH stores one batch record and one row record per CSV row. Every DWH record retains
the source and batch identifiers. The metadata DB stores references to the DWH batch, DWH row IDs,
and graph context. Neo4j stores a semantic context node linked back to source and batch references
with `DERIVED_FROM`. A provenance read joins those references without returning financial row
values from the graph.

## Validation queue and state machine

The v0.4 queue accepts registered `source` and completed or failed `extraction` identifiers as
subjects. Each item contains `id`, subject type and ID, status, JSON review payload, current reviewer
and comment, `created_at`, `updated_at`, `decided_at`, and an ordered decision history.

```text
enqueue -> pending
pending -> needs_changes  (comment)
needs_changes -> needs_changes  (additional comment)
pending | needs_changes -> approved  (approve)
pending | needs_changes -> rejected  (reject)
approved | rejected -> no transition
```

`needs_changes` is serialized with an underscore in APIs. CLI status input also accepts
`needs-changes` and normalizes it.

## Reviewer decisions and audit expectations

Every enqueue, comment, approval, and rejection appends an immutable validation-decision record.
It records the action, previous and resulting states, reviewer, comment, and UTC timestamp. An
approval or rejection also sets `decided_at` on the queue item.

The general metadata audit log appends source registration, extraction start/completion/failure,
and validation actions. Audit payloads contain identifiers and workflow metadata, not extracted
financial row values. Public failures use stable `{code, message}` fields and omit stack traces,
configuration secrets, source row contents, and filesystem paths from extraction errors.
