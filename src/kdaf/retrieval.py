"""DWH-aware CARP retrieval and auditable evidence packet construction."""

from __future__ import annotations

import hashlib
import re
import sqlite3
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any, Protocol
from uuid import uuid4

from kdaf.metadata import MetadataError, MetadataRepository
from kdaf.starter_graph import Neo4jConnectionSettings, starter_graph_model
from kdaf.starter_questions import StarterQuestion, starter_question_catalog

EVIDENCE_SCHEMA_VERSION = 1
_WRITE_SQL = re.compile(
    r"\b(ALTER|ATTACH|CREATE|DELETE|DETACH|DROP|INSERT|PRAGMA|REINDEX|REPLACE|UPDATE|VACUUM)\b",
    re.IGNORECASE,
)


class RetrievalError(ValueError):
    """Stable retrieval-domain failure."""

    def __init__(self, message: str, code: str = "retrieval_error") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class DwhQueryDefinition:
    id: str
    sql: str
    defaults: dict[str, Any]
    allowed_parameters: frozenset[str]


@dataclass(frozen=True)
class DwhQueryResult:
    id: str
    query_id: str
    statement_fingerprint: str
    parameters: dict[str, Any]
    rows: list[dict[str, Any]]
    row_count: int
    duration_ms: float
    executed_at: str
    store: str = "financial_dwh"
    mode: str = "read_only"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def dwh_query_catalog() -> dict[str, DwhQueryDefinition]:
    """Return controlled parameterized finance queries; callers cannot submit arbitrary SQL."""

    definitions = (
        DwhQueryDefinition(
            "budget_vs_actuals",
            """
            SELECT period_id, account_name, actual_amount, budget_amount, variance_amount
            FROM fpna_budget_vs_actual_monthly
            WHERE account_id = :account_id
            ORDER BY period_id
            """,
            {"account_id": "revenue"},
            frozenset({"account_id"}),
        ),
        DwhQueryDefinition(
            "department_spend",
            """
            SELECT period_id, department_name, actual_spend
            FROM fpna_department_spend_monthly
            WHERE period_id = :period_id
            ORDER BY actual_spend DESC, department_name
            """,
            {"period_id": "2026-03"},
            frozenset({"period_id"}),
        ),
        DwhQueryDefinition(
            "forecast_movement",
            """
            SELECT actual.period_id, SUM(actual.amount) AS actual_amount,
                   SUM(forecast.amount) AS forecast_amount,
                   SUM(forecast.amount - actual.amount) AS movement_amount
            FROM fpna_facts AS actual
            JOIN fpna_facts AS forecast
              ON forecast.entity_id = actual.entity_id
             AND forecast.department_id = actual.department_id
             AND forecast.account_id = actual.account_id
             AND forecast.period_id = actual.period_id
             AND forecast.scenario_id = 'forecast'
            WHERE actual.scenario_id = 'actual' AND actual.account_id = :account_id
            GROUP BY actual.period_id ORDER BY actual.period_id
            """,
            {"account_id": "revenue"},
            frozenset({"account_id"}),
        ),
        DwhQueryDefinition(
            "variance",
            """
            SELECT actual.period_id, actual.department_id, actual.account_id,
                   actual.amount AS actual_amount, budget.amount AS budget_amount,
                   actual.amount - budget.amount AS variance_amount
            FROM fpna_facts AS actual
            JOIN fpna_facts AS budget
              ON budget.entity_id = actual.entity_id
             AND budget.department_id = actual.department_id
             AND budget.account_id = actual.account_id
             AND budget.period_id = actual.period_id
             AND budget.scenario_id = 'budget'
            WHERE actual.scenario_id = 'actual'
            ORDER BY ABS(actual.amount - budget.amount) DESC, actual.period_id
            """,
            {},
            frozenset(),
        ),
        DwhQueryDefinition(
            "revenue_driver",
            """
            SELECT period_id, SUM(amount) AS actual_revenue
            FROM fpna_facts
            WHERE account_id = :account_id AND scenario_id = 'actual'
            GROUP BY period_id ORDER BY period_id
            """,
            {"account_id": "revenue"},
            frozenset({"account_id"}),
        ),
    )
    return {definition.id: definition for definition in definitions}


class ReadOnlyDwhQueryService:
    """Execute allow-listed parameterized queries against the separate DWH store."""

    def __init__(self, store_path: str | Path) -> None:
        self.store_path = Path(store_path)

    def execute(self, query_id: str, parameters: dict[str, Any] | None = None) -> DwhQueryResult:
        definition, params = _prepare_query(query_id, parameters)
        _assert_read_only(definition.sql)
        started = perf_counter()
        try:
            with self._connect() as connection:
                rows = connection.execute(definition.sql, params).fetchall()
        except sqlite3.OperationalError as exc:
            raise RetrievalError("Financial DWH is not loaded", "dwh_not_loaded") from exc
        elapsed = round((perf_counter() - started) * 1000, 3)
        result_id = f"dwh-query:{uuid4()}"
        return DwhQueryResult(
            id=result_id,
            query_id=definition.id,
            statement_fingerprint=hashlib.sha256(
                " ".join(definition.sql.split()).encode("utf-8")
            ).hexdigest(),
            parameters=params,
            rows=[dict(row) for row in rows],
            row_count=len(rows),
            duration_ms=elapsed,
            executed_at=_timestamp(),
        )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.store_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")
        return connection


class PostgresDwhQueryService:
    """Production adapter for allow-listed queries in a read-only Postgres transaction."""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        database: str,
        user: str,
        password: str,
    ) -> None:
        self.connection_settings = {
            "host": host,
            "port": port,
            "dbname": database,
            "user": user,
            "password": password,
        }

    def execute(self, query_id: str, parameters: dict[str, Any] | None = None) -> DwhQueryResult:
        definition, params = _prepare_query(query_id, parameters)
        _assert_read_only(definition.sql)
        postgres_sql = re.sub(r":([a-zA-Z_][a-zA-Z0-9_]*)", r"%(\1)s", definition.sql)
        try:
            import psycopg
        except ImportError as exc:
            raise RetrievalError("Postgres driver is not installed", "dwh_unavailable") from exc
        started = perf_counter()
        try:
            with (
                psycopg.connect(
                    **self.connection_settings,
                    row_factory=psycopg.rows.dict_row,
                    options="-c default_transaction_read_only=on",
                ) as connection,
                connection.cursor() as cursor,
            ):
                cursor.execute("SET TRANSACTION READ ONLY")
                cursor.execute(postgres_sql, params)
                rows = cursor.fetchall()
        except Exception as exc:
            raise RetrievalError("Financial DWH is unavailable", "dwh_unavailable") from exc
        elapsed = round((perf_counter() - started) * 1000, 3)
        return DwhQueryResult(
            id=f"dwh-query:{uuid4()}",
            query_id=definition.id,
            statement_fingerprint=hashlib.sha256(
                " ".join(definition.sql.split()).encode("utf-8")
            ).hexdigest(),
            parameters=params,
            rows=[dict(row) for row in rows],
            row_count=len(rows),
            duration_ms=elapsed,
            executed_at=_timestamp(),
        )


def _assert_read_only(sql: str) -> None:
    normalized = sql.strip()
    if not normalized or not normalized.upper().startswith(("SELECT", "WITH")):
        raise RetrievalError("DWH service accepts read-only queries only", "unsafe_query")
    without_trailing = normalized.rstrip("; ")
    if ";" in without_trailing or _WRITE_SQL.search(without_trailing):
        raise RetrievalError("DWH service accepts read-only queries only", "unsafe_query")


def _prepare_query(
    query_id: str, parameters: dict[str, Any] | None
) -> tuple[DwhQueryDefinition, dict[str, Any]]:
    if not isinstance(query_id, str) or not query_id.strip():
        raise RetrievalError("DWH query ID is required", "missing_field")
    supplied = {} if parameters is None else parameters
    if not isinstance(supplied, dict):
        raise RetrievalError("DWH query parameters must be an object", "invalid_input")
    definition = dwh_query_catalog().get(query_id.strip())
    if definition is None:
        raise RetrievalError(f"DWH query not found: {query_id}", "not_found")
    unexpected = sorted(set(supplied) - definition.allowed_parameters)
    if unexpected:
        raise RetrievalError(
            f"Unsupported DWH query parameter: {unexpected[0]}", "invalid_parameter"
        )
    return definition, {**definition.defaults, **supplied}


class GraphContextProvider(Protocol):
    def retrieve(self, concept_ids: list[str]) -> dict[str, Any]: ...


class PackagedGraphContextProvider:
    """Offline adapter over the same semantic seed model used to populate Neo4j."""

    def retrieve(self, concept_ids: list[str]) -> dict[str, Any]:
        model = starter_graph_model()
        concepts = {
            item["id"]: {**item, "kind": group.removesuffix("s")}
            for group, items in model.items()
            if group != "domains"
            for item in items
        }
        missing = [concept_id for concept_id in concept_ids if concept_id not in concepts]
        if missing:
            raise RetrievalError(f"Graph concept not found: {missing[0]}", "not_found")
        nodes = [concepts[concept_id] for concept_id in concept_ids]
        relationships: list[dict[str, str]] = []
        dimensions: list[dict[str, str]] = []
        for node in nodes:
            for dependency_id in node.get("depends_on", []):
                relationships.append(
                    {"type": "DEPENDS_ON", "from_id": node["id"], "to_id": dependency_id}
                )
            if "dwh_table" in node:
                reference_id = f"dwh-dimension:{node['dwh_table']}:{node['dwh_value']}"
                relationships.append(
                    {
                        "type": "REFERENCES_DWH_DIMENSION",
                        "from_id": node["id"],
                        "to_id": reference_id,
                    }
                )
                dimensions.append(
                    {
                        "id": reference_id,
                        "table": node["dwh_table"],
                        "key": node["dwh_key"],
                        "value": node["dwh_value"],
                    }
                )
        return {"nodes": nodes, "relationships": relationships, "dimensions": dimensions}


class Neo4jGraphContextProvider:
    """Retrieve semantic context from Neo4j without reading or writing financial facts."""

    def __init__(self, settings: Neo4jConnectionSettings) -> None:
        self.settings = settings

    def retrieve(self, concept_ids: list[str]) -> dict[str, Any]:
        try:
            from neo4j import GraphDatabase
        except ImportError as exc:
            raise RetrievalError("Neo4j driver is not installed", "graph_unavailable") from exc
        try:
            with (
                GraphDatabase.driver(
                    self.settings.uri, auth=(self.settings.user, self.settings.password)
                ) as driver,
                driver.session(database=self.settings.database) as session,
            ):
                nodes = [
                    dict(record)
                    for record in session.run(
                        """
                        MATCH (concept:SemanticConcept) WHERE concept.id IN $concept_ids
                        RETURN concept.id AS id, concept.name AS name,
                               coalesce(concept.description, '') AS description,
                               coalesce(concept.validation_state, 'unvalidated')
                                   AS validation_state,
                               labels(concept) AS labels
                        ORDER BY id
                        """,
                        concept_ids=concept_ids,
                    )
                ]
                relationships = [
                    dict(record)
                    for record in session.run(
                        """
                        MATCH (source:SemanticConcept)-[relationship]->(target)
                        WHERE source.id IN $concept_ids
                        RETURN type(relationship) AS type, source.id AS from_id,
                               coalesce(target.id, target.table + ':' + target.value) AS to_id
                        ORDER BY from_id, type, to_id
                        """,
                        concept_ids=concept_ids,
                    )
                ]
                dimensions = [
                    dict(record)
                    for record in session.run(
                        """
                        MATCH (concept:SemanticConcept)-[:REFERENCES_DWH_DIMENSION]->(dimension)
                        WHERE concept.id IN $concept_ids
                        RETURN 'dwh-dimension:' + dimension.table + ':' + dimension.value AS id,
                               dimension.table AS table, dimension.key AS key,
                               dimension.value AS value
                        ORDER BY id
                        """,
                        concept_ids=concept_ids,
                    )
                ]
        except RetrievalError:
            raise
        except Exception as exc:
            raise RetrievalError("Neo4j graph context is unavailable", "graph_unavailable") from exc
        found_ids = {node["id"] for node in nodes}
        missing = [concept_id for concept_id in concept_ids if concept_id not in found_ids]
        if missing:
            raise RetrievalError(f"Graph concept not found: {missing[0]}", "not_found")
        return {"nodes": nodes, "relationships": relationships, "dimensions": dimensions}


class CarpRetrievalService:
    """Propagate competency-question relevance into graph and provenance context."""

    def __init__(self, metadata: MetadataRepository, graph_provider: GraphContextProvider) -> None:
        self.metadata = metadata
        self.graph_provider = graph_provider

    def retrieve(self, question_id: str) -> dict[str, Any]:
        try:
            question = self.metadata.get_competency_question(question_id)
        except MetadataError as exc:
            raise RetrievalError(str(exc), exc.code) from exc
        concept_ids = _question_concept_ids(self.metadata, question.id, question.question_text)
        context = self.graph_provider.retrieve(concept_ids)
        provenance_links: list[dict[str, Any]] = []
        for batch in self.metadata.list_extractions():
            for link in self.metadata.list_provenance_links(batch.id):
                provenance_links.append(link.to_dict())
        relevant_subject_ids = {link["source_id"] for link in provenance_links} | {
            link["batch_id"] for link in provenance_links
        }
        validations = [
            validation.to_dict()
            for validation in self.metadata.list_validations()
            if validation.subject_id in relevant_subject_ids
        ]
        return {
            "schema_version": 1,
            "question_id": question.id,
            "project_id": question.project_id,
            "concept_ids": concept_ids,
            **context,
            "source_links": provenance_links,
            "validation_states": validations,
            "provenance": {
                "provider": self.graph_provider.__class__.__name__,
                "question_id": question.id,
                "retrieved_at": _timestamp(),
            },
        }


class EvidencePacketBuilder:
    """Combine DWH facts and graph context into a portable audit artifact."""

    def build(
        self,
        *,
        question: dict[str, Any],
        run: dict[str, Any],
        dwh_query: DwhQueryResult,
        graph_context: dict[str, Any],
    ) -> dict[str, Any]:
        if question.get("project_id") != run.get("project_id"):
            raise RetrievalError("Run and competency question must share a project", "invalid_id")
        entries = [
            {
                "id": f"{dwh_query.id}:row:{index}",
                "kind": "financial_fact",
                "query_id": dwh_query.id,
                "data": row,
            }
            for index, row in enumerate(dwh_query.rows, start=1)
        ]
        entries.extend(
            {
                "id": f"graph-node:{node['id']}",
                "kind": "semantic_context",
                "node_id": node["id"],
                "data": node,
            }
            for node in graph_context["nodes"]
        )
        return {
            "schema_version": EVIDENCE_SCHEMA_VERSION,
            "id": f"evidence-packet:{uuid4()}",
            "project_id": question["project_id"],
            "run_id": run["id"],
            "competency_question_id": question["id"],
            "question": question["question_text"],
            "dwh_queries": [dwh_query.to_dict()],
            "graph_nodes": graph_context["nodes"],
            "graph_relationships": graph_context["relationships"],
            "source_records": graph_context["source_links"],
            "validation_decisions": graph_context["validation_states"],
            "entries": entries,
            "provenance": {
                "dwh_query_ids": [dwh_query.id],
                "graph": graph_context["provenance"],
                "source_link_ids": [link["id"] for link in graph_context["source_links"]],
                "validation_ids": [item["id"] for item in graph_context["validation_states"]],
            },
            "built_at": _timestamp(),
        }


def starter_question_for_text(question_text: str) -> StarterQuestion:
    for question in starter_question_catalog().questions:
        if question.question_text == question_text:
            return question
    raise RetrievalError(
        "Competency question is not in the starter catalog", "unsupported_question"
    )


def _question_concept_ids(
    metadata: MetadataRepository, question_id: str, question_text: str
) -> list[str]:
    for artifact in metadata.list_mvg_artifacts():
        if question_id in artifact.question_ids:
            return artifact.concept_ids
    return starter_question_for_text(question_text).expected_graph_concepts


def _timestamp() -> str:
    return datetime.now(UTC).isoformat()
