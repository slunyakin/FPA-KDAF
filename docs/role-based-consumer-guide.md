# How KDAF Helps Each Role

KDAF is a framework for producing finance answers that are useful to decision-makers and
traceable by the people responsible for data, controls, and software. It connects four kinds of
evidence without collapsing them into one system:

- financial facts and measures from the DWH
- semantic meaning and relationships from Neo4j
- project, run, validation, and audit state from the metadata database
- cited answers produced from evidence packets

This guide explains what that operating model means for each consumer of KDAF.

## The Shared Flow

Every role participates in, builds on, or consumes the same flow:

```text
business question
  -> competency question and MVG scope
  -> governed source extraction and validation
  -> CARP semantic-context retrieval
  -> read-only DWH query
  -> evidence packet
  -> cited answer or explicit refusal
  -> auditable run record
```

KDAF keeps responsibilities visible throughout the flow. Neo4j explains what financial data means;
the DWH stores and calculates the numbers; metadata records the workflow; and the evidence packet
binds those components into a reviewable answer.

## Role Overview

| Role | Primary need | How KDAF helps | Main output |
| --- | --- | --- | --- |
| FP&A analyst | Answer recurring finance questions efficiently | Retrieves relevant context and warehouse facts for a defined competency question | Cited analysis with inspectable evidence |
| Finance leader or controller | Trust the answer and understand its control status | Exposes source lineage, validation decisions, and unsupported-claim refusals | Reviewable answer and control trail |
| Business leader | Understand performance without navigating technical systems | Presents concise answers grounded in governed finance data | Decision-ready explanation with citations |
| Data or analytics engineer | Serve reliable financial facts without duplicating them into the graph | Provides allow-listed, parameterized, read-only DWH access | Controlled query results and query metadata |
| Finance domain modeler | Make finance terminology and analytical relationships explicit | Connects competency questions and MVGs to semantic concepts in Neo4j | Reusable metric, dimension, and relationship context |
| AI or application developer | Embed finance answers in applications and agents safely | Offers aligned core, CLI, and tool-server interfaces with stable errors | Machine-readable evidence and grounded-answer APIs |
| Auditor, risk, or governance reviewer | Reconstruct how an answer was produced | Records provenance, validation state, prompts, models, parameters, outputs, and run IDs | End-to-end audit evidence |
| Platform or operations engineer | Run the framework with clear system boundaries | Separates Neo4j, metadata Postgres, and financial DWH responsibilities | Operable services with reduced data-boundary ambiguity |

## FP&A Analyst

### What the analyst needs

An FP&A analyst typically starts with a recurring question: Where is revenue above or below budget?
Which departments are driving spend? How has the forecast moved? The difficult part is rarely the
arithmetic alone. The analyst must also locate the right measure, scenario, period, source, and
business definition.

### How KDAF helps

KDAF turns the business question into a competency question and uses its minimum viable graph (MVG)
to identify the relevant metrics, dimensions, scenarios, and DWH dependencies. CARP retrieval brings
back that semantic context, while the read-only query service retrieves the actual numbers from the
DWH. The evidence packet keeps the two sides connected.

### Typical workflow

1. Select a starter question or create a project-specific competency question.
2. Confirm the MVG contains the relevant concepts.
3. Build an evidence packet for a project run.
4. Review the DWH rows, semantic context, provenance, and validation state.
5. Generate or consume the cited answer.
6. Investigate an individual citation when more detail is needed.

### What the analyst receives

- a direct answer to the finance question
- citations to individual evidence entries
- the underlying DWH query and result rows
- definitions and relationships for the metrics and dimensions used
- a visible refusal when available evidence cannot support a claim

KDAF reduces the time spent rediscovering context while keeping the underlying analysis available
for review.

## Finance Leader or Controller

### What the leader needs

A controller or finance leader needs more than a plausible explanation. They need to know whether
the source was governed, whether a reviewer approved it, which assumptions shaped the analysis, and
whether the system is making claims beyond the evidence.

### How KDAF helps

KDAF carries source provenance and validation state into retrieval and evidence construction. The
answer service accepts only citations that resolve to the supplied evidence packet. A requested
claim that is outside the packet is returned as `insufficiently_supported` instead of being presented
as fact.

### What the leader can review

- project, run, and competency-question identity
- source and extraction provenance
- validation status and reviewer decision history
- the exact controlled DWH query used
- the semantic context that explains the measures
- the final answer and its evidence citations
- prompt, provider, model, parameters, and output audit metadata

This makes the answer suitable for review conversations: the leader can challenge the evidence,
definition, validation decision, or conclusion separately.

## Business Leader

### What the business leader needs

A business leader usually wants a concise explanation of performance, not a database workflow. They
still need confidence that the answer is based on the recognized finance model and current governed
data.

### How KDAF helps

Applications can present the grounded answer as the primary experience and keep citations available
for drill-down. The evidence packet gives finance and data teams a shared artifact when the leader
asks a follow-up question or challenges a result.

### What the business leader receives

- a concise, contextual finance answer
- visible citations instead of an unsupported narrative
- consistent definitions across recurring questions
- an explicit indication when the system lacks enough evidence

KDAF does not require business consumers to understand Neo4j or SQL. It makes those systems
inspectable by the supporting teams without exposing their complexity as the main user experience.

## Data or Analytics Engineer

### What the engineer needs

The data engineer must keep the DWH authoritative for financial values, expose useful queries, and
prevent analytical applications from gaining an accidental write path or copying fact tables into
other stores.

### How KDAF helps

KDAF exposes named, parameterized DWH queries. The Postgres adapter sets both connection-level and
transaction-level read-only controls. The local adapter offers the same controlled interface for
tests and demonstrations. Query metadata is audited without duplicating returned fact rows into
Neo4j.

### Engineering responsibilities

- maintain the DWH schema, dimensions, facts, and approved query definitions
- ensure query parameters and result shapes remain stable
- monitor query performance and warehouse availability
- preserve identifiers that semantic graph concepts use to reference DWH dimensions
- verify that financial amounts never become graph properties

### What the engineer receives

- a narrow, controlled consumer boundary instead of arbitrary SQL access
- query fingerprints, parameters, row counts, timing, and run association
- public-interface tests for malformed input and unsupported parameters
- separation between production Postgres access and the local test harness

## Finance Domain Modeler

### What the modeler needs

The domain modeler needs a durable place to define what terms such as budget, actuals, variance,
department spend, and forecast movement mean and how they relate. Those definitions must be useful
to retrieval without becoming another copy of the warehouse.

### How KDAF helps

Neo4j stores semantic concepts, relationships, relevance context, provenance links, and validation
state. Competency questions and MVGs identify the smallest useful graph scope for a consumer need.
Graph concepts reference DWH dimensions through stable identifiers, while financial values remain in
the DWH.

### Typical workflow

1. Review the consumer's competency question.
2. Identify the metrics, dimensions, scenarios, and dependencies required to answer it.
3. Add or refine graph concepts and relationships.
4. Link concepts to the appropriate DWH dimensions.
5. Record or update semantic validation state.
6. Test that CARP retrieval returns the intended context without unrelated concepts.

### What the modeler receives

- evidence that semantic modeling affects a real consumer workflow
- a question-to-MVG-to-concept trace
- repeatable retrieval behavior for starter and project-specific questions
- a clean boundary between meaning in the graph and numbers in the DWH

## AI or Application Developer

### What the developer needs

The developer needs to embed finance retrieval and answer generation without rebuilding governance,
database boundaries, error handling, and citation logic in every interface.

### How KDAF helps

The Python core, CLI, and JSON-line tool server call the same services. Applications and agents can
retrieve CARP context, run controlled DWH queries, build evidence packets, and generate answers using
Ollama or an OpenAI-compatible provider. Public errors have a stable machine-readable shape.

### Available integration surfaces

- shared Python services through `KdafCore`
- operator workflows through the `kdaf` CLI
- agent workflows through the tool server
- deterministic offline provider for tests and demonstrations
- Ollama and OpenAI-compatible HTTP providers for generated answers

### What the developer receives

- one business implementation across human and agent entrypoints
- addressable evidence entries and validated citation IDs
- explicit grounded versus insufficiently-supported status
- stable errors for invalid arguments, missing fields, unknown IDs, and unavailable services
- sanitized provider failures that do not expose API keys or configuration

KDAF supplies the trust and evidence layer. The surrounding application remains responsible for
authentication, authorization, user experience, rate limits, and production deployment controls.

## Auditor, Risk, or Governance Reviewer

### What the reviewer needs

The reviewer needs to reconstruct an answer after the fact and determine whether the correct data,
definitions, controls, and model behavior were used.

### How KDAF helps

Evidence packets and metadata audit events provide linked records rather than an unstructured chat
transcript. The reviewer can move from answer citation to packet entry, DWH query, source link,
validation decision, project, and run.

### Audit evidence available

- evidence packet ID and schema version
- project, run, and competency-question IDs
- DWH query ID, fingerprint, parameters, row count, and execution metadata
- graph nodes and relationships used as context
- source provenance links
- validation items and decision histories
- prompt, provider, model, parameters, final output, and grounding status

API keys are not included in audit events or public errors. Financial facts may appear in the
evidence supplied to the model and in the logged prompt/output as required for answer
reconstruction, but they are not stored in Neo4j.

## Platform or Operations Engineer

### What the operator needs

The operator needs a deployable mental model, clear ownership of credentials, predictable failures,
and services that survive malformed consumer requests.

### How KDAF helps

KDAF separates the semantic graph, metadata database, and financial DWH at configuration and service
boundaries. The tool server returns a bounded error for a bad request and continues processing the
next request. Production adapters sanitize connection and provider failures.

### Operational responsibilities

- configure and secure Neo4j, metadata Postgres, and DWH Postgres independently
- provision a read-only DWH identity
- manage LLM-provider endpoints and secrets
- monitor graph, DWH, metadata, and provider availability
- retain audit data according to organizational policy
- choose whether local adapters are appropriate for a given environment

### What the operator receives

- clear service ownership and credential boundaries
- health and non-secret configuration summaries
- stable failure codes for unavailable graph, DWH, and provider services
- Docker-optional unit tests and clean integration-test skips when Docker is unavailable

## Example: Monthly Budget Review Across Roles

The following scenario shows how the roles collaborate around one question: “Where is actual revenue
above or below budget by month?”

1. The **FP&A analyst** selects the starter competency question and reviews its MVG.
2. The **finance domain modeler** confirms that budget-vs-actuals, variance, revenue, actual, and
   budget concepts are related correctly.
3. The **data engineer** maintains the revenue actual and budget facts and the controlled DWH query.
4. The **controller** ensures the relevant source extraction has an acceptable validation state.
5. KDAF retrieves graph context and DWH rows and builds an evidence packet for the run.
6. The **AI application** generates an answer whose factual statements cite packet entries.
7. The **business leader** reads the answer and follows a citation when detail is needed.
8. The **auditor** can later reconstruct the query, evidence, prompt, model, output, and validation
   history.
9. The **platform operator** keeps the services and credentials isolated throughout the process.

The evidence packet is the handoff artifact between these roles. It lets each role inspect the part
they own without requiring every consumer to become an expert in every KDAF subsystem.

## Adoption Paths

### Evaluate KDAF locally

Use the starter question catalog, starter DWH, packaged semantic graph, deterministic provider, and
`--offline-graph` workflow. This path demonstrates the complete evidence flow without requiring live
Neo4j, Postgres, or an LLM provider.

### Introduce governed finance retrieval

Connect project-specific questions and MVGs to live Neo4j, use the configured read-only Postgres DWH
adapter, and bring validated source provenance into retrieval. Keep deterministic answer generation
until the evidence and controls are accepted.

### Embed grounded answers

Integrate the shared core or tool server into an application, configure Ollama or an
OpenAI-compatible provider, and present citations and insufficient-evidence states in the user
experience. Add organization-specific authorization, retention, evaluation, and monitoring around
the KDAF services.

## Current Boundaries

KDAF v0.5 provides the first complete question-to-grounded-answer slice, but consumers should plan
for the following boundaries:

- the starter catalog and query set cover a small FP&A domain rather than every finance workflow
- project-specific graph curation and DWH query definitions still require domain and data ownership
- source-to-project and MVG-to-source relevance is not yet fully automated
- production applications must add identity, access control, retention, and operational monitoring
- provider-specific streaming, retry, rate-limit, and evaluation behavior remains application work
- a grounded citation proves that an answer points to supplied evidence; organizations must still
  validate source quality, semantic definitions, and analytical methodology

These boundaries are deliberate places for consumer governance and future framework extension—not a
reason to blur the core separation between semantic meaning, financial facts, workflow metadata, and
answer evidence.
