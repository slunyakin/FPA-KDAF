# Execute registered question bindings

KDAF executes custom competency questions through explicit, project-scoped
bindings. A binding identifies one competency question, one published Neo4j
question scope, the required concepts, and—only for quantitative questions—one
versioned read-only data operation. Execution never reconstructs a binding from
the question's display wording or the starter-question catalog.

## Contract and lifecycle

| Record | Stable key | Versioned content | Lifecycle |
| --- | --- | --- | --- |
| Data operation | project + operation ID | SQL template, parameter schema, result schema, evidence eligibility, row limit | Registered as active and referenced by exact version |
| Question binding | project + binding ID | question ID, evidence mode, concept IDs, publication ID, optional operation version | Draft → active → superseded |

Activation validates the exact published question scope against the configured
Neo4j database. Every required concept must be present in that question's
approved publication. A quantitative binding must also reference an
evidence-eligible operation in the same project. Activating a newer version
supersedes the previously active version without deleting its history.

Execution resolves IDs and versions only. Changing the competency question's
display wording does not change the binding. The evidence packet records the
binding version, graph publication ID, question-scope ID, data-operation version,
statement fingerprint, parameters, and returned query ID.

## Semantic-only questions

A semantic-only binding retrieves its approved Neo4j scope and does not execute
a DWH operation.

```bash
kdaf question-binding register PROJECT_ID renewal-impact QUESTION_ID \
  --evidence-mode semantic_only \
  --concept-id account:revenue \
  --concept-id driver:portfolio_renewal_rate \
  --publication-id GRAPH_PUBLICATION_ID

kdaf question-binding activate BINDING_RECORD_ID --database neo4j

kdaf question-binding execute PROJECT_ID renewal-impact RUN_ID \
  --database neo4j > evidence.json
```

The deterministic answer provider is a network-free test fixture and only
summarizes `financial_fact` entries. It therefore reports insufficient evidence
for a semantic-only packet. Use a configured provider when an answer should be
generated from `semantic_context` entries.

## Quantitative questions

Quantitative execution uses an operator-registered statement, not unrestricted
text-to-SQL. Named placeholders must exactly match the parameter schema. KDAF
accepts only `SELECT` or `WITH` statements, runs the DWH adapter read-only, and
rejects statements with write operations or multiple statements. The operation
also sets a maximum result count.

Example `parameters.json`:

```json
{
  "type": "object",
  "properties": {
    "account_id": {"type": "string", "maxLength": 40}
  },
  "required": ["account_id"],
  "additionalProperties": false
}
```

Example `results.json`:

```json
{
  "type": "object",
  "properties": {
    "period_id": {"type": "string"},
    "actual_revenue": {"type": "number"}
  },
  "required": ["period_id", "actual_revenue"],
  "additionalProperties": false
}
```

Register the SQL and then bind its exact version:

```bash
kdaf data-operation register PROJECT_ID actual-revenue-by-account \
  --statement-file actual-revenue.sql \
  --parameter-schema-file parameters.json \
  --result-schema-file results.json \
  --max-rows 24

kdaf data-operation get PROJECT_ID actual-revenue-by-account --version 1

kdaf question-binding register PROJECT_ID renewal-revenue QUESTION_ID \
  --evidence-mode quantitative \
  --concept-id account:revenue \
  --concept-id driver:portfolio_renewal_rate \
  --publication-id GRAPH_PUBLICATION_ID \
  --operation-id actual-revenue-by-account \
  --operation-version 1

kdaf question-binding activate BINDING_RECORD_ID --database neo4j

kdaf --dwh-store finance.sqlite3 \
  question-binding execute PROJECT_ID renewal-revenue RUN_ID \
  --database neo4j \
  --parameters-json '{"account_id":"revenue"}' > evidence.json
```

No rows returns `missing_data`; KDAF does not substitute starter or sample facts.
Rows that do not match the registered result schema return
`invalid_result_schema`.

## Generate an answer with a configured provider

The existing answer-provider interface accepts the generated evidence packet.
For an OpenAI-compatible endpoint:

```bash
kdaf answer generate evidence.json \
  --provider openai-compatible \
  --base-url https://provider.example \
  --api-key "$PROVIDER_API_KEY" \
  --model configured-model \
  --parameters-json '{"temperature":0}'
```

The answer record contains `provider`, `model`, `evidence_packet_id`, and an
audit-event ID. The packet itself contains graph and data lineage. Provider output
is accepted as grounded only when it cites valid packet entries; that citation
check does not by itself prove the correctness of every claim.

## Structured failures

Public core, CLI, and tool-server surfaces return stable codes including:

- `binding_not_found` for an unknown or inactive binding version;
- `missing_context` or `ambiguous_context` for an unavailable published scope;
- `missing_parameter` and `invalid_parameter` for typed input failures;
- `missing_data_binding` or `unauthorized_data_operation` for invalid data access;
- `unsafe_query` and `result_too_large` for operation safety failures;
- `missing_data` and `invalid_result_schema` for unusable quantitative results.

## Current limits

This first slice executes explicitly registered custom bindings and preserves the
existing starter workflow. Migrating starter catalog entries onto the same
registration records, richer JSON Schema features, operation retirement, and
natural-language selection among bindings remain follow-up work. Intent
selection is a consumer concern and is not required to execute a known binding.

Live graph execution requires the Neo4j extra and an explicitly configured
database. Authentication, authorization, backups, and production approval policy
remain deployment responsibilities.
