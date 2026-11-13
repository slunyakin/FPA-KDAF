# Question mapping and minimal graph proposals

KDAF accepts a confirmed discovery handoff after an interview or other business
discovery process. Discovery and graph design remain separate phases: the
handoff contains accepted, revise, parked, and rejected questions, while only
accepted questions can create active competency questions or graph scope.

The mapping service compares accepted terminology with an existing scoped graph.
It classifies exact reuse, ambiguity, a proposed project extension, and unresolved
terms. It produces a versioned proposal for review; it never executes generated
Cypher or publishes graph meaning directly.

## Handoff contract

A handoff is a JSON object with:

- `decision_context`: the problem, decision, scope, and trust criteria.
- `questions`: candidates with stable discovery IDs, status, terminology,
  evidence requirements, and source hypotheses.
- `participant_terminology` and `disputed_terms` with explicit provenance.
- `base_graph`: the foundation ID and version used during discovery.
- `provenance`: the source artifact and the person who confirmed it.

Term provenance must distinguish `participant_statement`,
`facilitator_summary`, and `discovery_artifact`. Unsupported fields such as
instructions or executable queries are rejected. Text remains untrusted domain
content when an optional model proposer is used.

An accepted term can carry an explicit `concept_id`. For deterministic testing,
an unmatched term can carry a `proposed_concept` hint. That hint remains a
proposer inference and still passes the same validation and review contract as a
model-produced proposal.

Import a handoff:

```bash
kdaf --metadata-store .kdaf/metadata.sqlite3 \
  discovery-handoff import PROJECT_ID confirmed-handoff.json
```

Import creates framework competency-question records only for accepted
questions. Other statuses remain preserved in the handoff.

## Create and inspect a proposal

The default CLI path uses the packaged finance foundation and the deterministic
proposer. It runs offline:

```bash
kdaf --metadata-store .kdaf/metadata.sqlite3 \
  graph-proposal create HANDOFF_ID

kdaf --metadata-store .kdaf/metadata.sqlite3 \
  graph-proposal coverage PROPOSAL_ID
```

Use `--live-graph` to read the installed foundation plus published extensions
scoped to the handoff project. If the foundation version differs from the
handoff, KDAF returns `stale_base_graph` and requires a rebase.

The proposal contains:

- one mapping for every accepted competency question;
- reused concept IDs and question-level mapping rationale;
- proposed concepts, relationships, definitions, scope, and provenance;
- unresolved terms and explicit alternative mappings;
- evidence requirements, including unknown availability;
- an independently calculated coverage report.

`ready_for_review` means the structural proposal is complete. It does not mean
that definitions are approved. `needs_clarification` preserves ambiguity or
unresolved terms for the consumer to resolve.

## External and model-assisted proposers

An application can generate the proposal JSON and submit it with provenance:

```bash
kdaf graph-proposal create HANDOFF_ID \
  --proposal-file model-proposal.json \
  --provider local-model-gateway \
  --model configured-model
```

Python consumers can use an existing answer provider directly:

```python
from kdaf import (
    KdafCore,
    OpenAICompatibleProvider,
    ProviderBackedQuestionMappingProposer,
)

core = KdafCore()
provider = OpenAICompatibleProvider("http://localhost:11434")
proposer = ProviderBackedQuestionMappingProposer(
    provider=provider,
    model="configured-model",
    parameters={"temperature": 0},
)
proposal = core.create_graph_extension_proposal(
    "HANDOFF_ID",
    proposer=proposer,
)
```

KDAF records provider and model provenance but does not treat model output as an
approved ontology. It rejects unknown existing IDs, duplicate meaning, unsafe
relationship types, missing endpoints, cross-project scope, elements without
accepted-question justification, incomplete dependency closure, and excessive
per-question additions.

## Publication boundary

This service records draft proposals only. Review and publication are handled by
the [semantic publication workflow](semantic-publication.md). It reviews the exact
proposal version, digest, purpose, and base graph version; it does not reconstruct
meaning from display text or execute proposer-authored Cypher.
