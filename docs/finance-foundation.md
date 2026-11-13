# Versioned finance foundation

KDAF provides a small finance foundation as a reusable starting point for
question-driven graph development. It is a seeded vocabulary, not a complete
finance ontology and not an automatically approved source of organizational
meaning.

The packaged manifest records stable concept and relationship IDs, descriptions,
provenance, ownership, and version. It separates three components:

- `kdaf.finance.foundation.core` contains portable finance meaning.
- `kdaf.finance.foundation.starter_profile` contains example organizational
  concepts retained for starter-kit compatibility.
- `kdaf.finance.foundation.starter_dwh_bindings` connects concepts to the
  packaged example warehouse. These bindings are not loaded with the core.

## Inspect the manifest and plan a change

Manifest inspection is offline:

```bash
kdaf finance-foundation manifest
```

Before writing to Neo4j, name the expected database explicitly. The command
fails if it differs from the configured database.

```bash
kdaf --config config/kdaf.example.toml \
  finance-foundation plan --database neo4j
```

The plan reports missing concepts and relationships, adoptable legacy elements,
and ownership or meaning conflicts. `review_required` means KDAF will not apply
the manifest until the conflict has been resolved through an upgrade/review
workflow.

## Initialize and inspect

Live planning, initialization, and inspection require the Neo4j client extra:

```bash
python -m pip install "kdaf[neo4j]"
```

If it is absent, KDAF returns the stable `neo4j_driver_missing` error. Connection,
authentication, and explicit database-target failures use separate bounded error
codes so operators can distinguish installation from deployment configuration.

```bash
kdaf --config config/kdaf.example.toml \
  finance-foundation initialize --database neo4j

kdaf --config config/kdaf.example.toml \
  finance-foundation inspect --database neo4j
```

Initialization creates only missing managed elements and records one installation
record per component. Repeating the same version returns `noop`. It does not
clear the database, load starter questions, or load financial facts.

To reproduce the complete starter graph while keeping the components explicit:

```bash
kdaf --config config/kdaf.example.toml \
  finance-foundation initialize \
  --database neo4j \
  --include-starter-profile \
  --include-starter-bindings
```

The existing `starter-graph load` command remains supported and delegates to
this full safe initialization path.

## Ownership and local knowledge

Managed nodes and relationships carry `kdaf_owner`, `kdaf_component_id`, and
`kdaf_foundation_version`. Seeded concepts start with `validation_state=seeded`.
Changing review state or adding project properties does not make them owned by
the seed loader, and identical reinitialization leaves those properties intact.

Project-specific meaning should be represented as a scoped extension or override
that references a shared concept. Do not rewrite a universal concept to fit one
organization. When a managed name, description, type, component, or owner no
longer matches the manifest, planning returns a conflict and initialization
refuses to overwrite it.

The compatibility `seed.cypher` artifact now uses create-only property updates,
but direct execution does not create version installation records. The public
core, CLI, or tool-server operations are the supported managed path.

## Current limits

- The manifest is intentionally small and its descriptions still require domain
  review before use as approved organizational meaning.
- The current planner detects version, ownership, type, name, description, and
  binding conflicts. Applying a reviewed cross-version upgrade is a later slice.
- Database provisioning and deletion are outside this operation.
- Authentication and authorization remain responsibilities of the configured
  Neo4j deployment.
