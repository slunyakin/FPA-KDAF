# Review and publish graph extensions

KDAF keeps proposal generation, expert review, and graph publication as separate
steps. A proposal from the question-mapping workflow is inactive until a reviewer
approves that exact proposal for the `semantic_publication` purpose and a
controlled publisher activates it in Neo4j.

Approval covers the proposal version, base foundation version, question mappings,
definitions, aliases, relationships, rationale, provenance, and data-reference
requirements. KDAF stores a canonical snapshot and SHA-256 digest with the review.
Changing any reviewed material makes the approval stale.

## Review an exact proposal

Only proposals in `ready_for_review` state can be approved. A proposal with
ambiguities or unresolved terminology must be clarified and regenerated.

```bash
kdaf --metadata-store .kdaf/metadata.sqlite3 \
  graph-proposal review PROPOSAL_ID approved \
  --reviewer REVIEWER_ID \
  --reason "Definitions and question scope are confirmed"

kdaf --metadata-store .kdaf/metadata.sqlite3 \
  graph-proposal review-get PROPOSAL_ID
```

Review purpose is explicit. Approval for an experiment, extraction, or another
consumer does not authorize semantic publication. A rejected exact proposal stays
inactive; revise the handoff or proposal and create a new proposal version.

## Plan and publish

The target Neo4j database must be named explicitly and match configuration.
Install the live driver with `pip install "kdaf[neo4j]"` and initialize the
finance foundation before planning publication.

```bash
kdaf --config config/kdaf.example.toml \
  --metadata-store .kdaf/metadata.sqlite3 \
  graph-publication plan PROPOSAL_ID --database neo4j

kdaf --config config/kdaf.example.toml \
  --metadata-store .kdaf/metadata.sqlite3 \
  graph-publication publish PROPOSAL_ID --database neo4j
```

KDAF validates the installed foundation ID, version, and owner; project scope;
reused concepts; proposed IDs; relationship endpoints; and existing graph state.
A stale foundation returns `stale_base_graph`. Ownership or ID collisions return
a bounded conflict instead of overwriting existing meaning.

The publisher never executes proposal-authored Cypher. It emits controlled Cypher
from allow-listed concept labels and relationship types. Proposed concepts and
relationships remain project-scoped and retain their proposal, question, review,
and provenance links.

## Idempotency and recovery

One deterministic graph publication ID represents an exact proposal version and
digest. Repeating a completed publication is a no-op and does not create duplicate
nodes, relationships, or question scopes.

Neo4j activates the publication marker, concepts, relationships, and question
scope in one graph transaction. SQLite records the attempt separately. If Neo4j
fails, the metadata record is marked `failed` and no success is reported. If the
graph commit succeeds but metadata finalization is interrupted, rerunning the
same command detects the published graph marker and completes the metadata record
without rewriting the graph.

Inspect durable records and published question scope:

```bash
kdaf graph-publication list --proposal-id PROPOSAL_ID
kdaf graph-publication get PUBLICATION_RECORD_ID
kdaf graph-publication question-scope PROJECT_ID \
  --database neo4j --question-id COMPETENCY_QUESTION_ID
```

Question-scope results contain the approved concepts and relationships required
by that competency question. Data-reference requirements remain semantic
requirements; this workflow does not load financial values into Neo4j.

An approved scope can be made executable through a stable, versioned
[question binding](question-bindings.md). Semantic-only bindings use this graph
scope without forcing a DWH query; quantitative bindings attach an explicitly
registered read-only data operation.

## Current slice and limits

This slice publishes reviewed graph-extension proposals from the question-mapping
workflow. It preserves proposal and review history and exposes recovery metadata.
Standalone definition authoring, formula version supersession, historical
definition resolution, and replay automation remain later lifecycle slices.

Authentication, authorization, backup, and production operator policy remain the
responsibility of the configured Neo4j and metadata deployments.
