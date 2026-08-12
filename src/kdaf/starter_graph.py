"""Starter FP&A semantic graph seed and Neo4j access helpers."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from importlib import resources
from typing import Any

STARTER_GRAPH_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class StarterGraphLoadSummary:
    schema_version: int
    database: str
    concept_counts: dict[str, int]
    relationship_counts: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class StarterGraphError(ValueError):
    """Raised when starter graph setup or queries cannot be completed."""


@dataclass(frozen=True)
class Neo4jConnectionSettings:
    uri: str
    user: str
    password: str
    database: str


class StarterGraphRepository:
    """Neo4j-backed repository for the FP&A starter semantic graph."""

    def __init__(self, settings: Neo4jConnectionSettings) -> None:
        self.settings = settings

    def load_seed_data(self) -> StarterGraphLoadSummary:
        try:
            with (
                self._driver() as driver,
                driver.session(database=self.settings.database) as session,
            ):
                for statement in _cypher_statements(_seed_cypher()):
                    session.run(statement).consume()
                return _summary_from_rows(
                    database=self.settings.database,
                    concept_rows=session.run(_concept_count_query()),
                    relationship_rows=session.run(_relationship_count_query()),
                )
        except StarterGraphError:
            raise
        except Exception as exc:
            raise StarterGraphError(f"Neo4j starter graph load failed: {exc}") from exc

    def inspect_context(self) -> dict[str, Any]:
        try:
            with (
                self._driver() as driver,
                driver.session(database=self.settings.database) as session,
            ):
                _require_loaded(session)
                return {
                    "concept_counts": _records_to_dict(session.run(_concept_count_query())),
                    "dwh_references": _records_to_list(session.run(_dwh_reference_query())),
                    "metric_dependencies": _records_to_list(
                        session.run(_metric_dependency_query())
                    ),
                }
        except StarterGraphError:
            raise
        except Exception as exc:
            raise StarterGraphError(f"Neo4j starter graph inspection failed: {exc}") from exc

    def _driver(self) -> Any:
        try:
            from neo4j import GraphDatabase
        except ImportError as exc:
            raise StarterGraphError(
                "Neo4j driver is not installed. Install the project dependencies and retry."
            ) from exc

        try:
            return GraphDatabase.driver(
                self.settings.uri,
                auth=(self.settings.user, self.settings.password),
            )
        except Exception as exc:
            raise StarterGraphError(f"Cannot create Neo4j driver: {exc}") from exc


def starter_graph_cypher_artifacts() -> dict[str, str]:
    """Return packaged Cypher artifacts for the starter semantic graph."""

    root = resources.files("kdaf").joinpath("resources/starter_graph")
    return {
        "seed": root.joinpath("seed.cypher").read_text(encoding="utf-8"),
        "sample_queries": root.joinpath("sample_queries.cypher").read_text(encoding="utf-8"),
    }


def starter_graph_model() -> dict[str, list[dict[str, Any]]]:
    """Return the structured seed model used by tests and future catalog mapping."""

    return {
        "domains": [{"id": "domain:fpna_starter", "name": "FP&A Starter Kit"}],
        "accounts": [
            _concept("account:revenue", "Revenue", "fpna_accounts", "account_id", "revenue"),
            _concept("account:cogs", "Cost of Goods Sold", "fpna_accounts", "account_id", "cogs"),
            _concept(
                "account:payroll",
                "Payroll Expense",
                "fpna_accounts",
                "account_id",
                "payroll",
            ),
            _concept(
                "account:cloud_hosting",
                "Cloud Hosting",
                "fpna_accounts",
                "account_id",
                "cloud_hosting",
            ),
            _concept(
                "account:marketing_spend",
                "Marketing Spend",
                "fpna_accounts",
                "account_id",
                "marketing_spend",
            ),
            _concept(
                "account:headcount",
                "Headcount",
                "fpna_accounts",
                "account_id",
                "headcount",
            ),
        ],
        "departments": [
            _concept("department:sales", "Sales", "fpna_departments", "department_id", "sales"),
            _concept(
                "department:marketing",
                "Marketing",
                "fpna_departments",
                "department_id",
                "marketing",
            ),
            _concept(
                "department:engineering",
                "Engineering",
                "fpna_departments",
                "department_id",
                "engineering",
            ),
            _concept("department:g_and_a", "G&A", "fpna_departments", "department_id", "g_and_a"),
        ],
        "scenarios": [
            _concept("scenario:actual", "Actuals", "fpna_scenarios", "scenario_id", "actual"),
            _concept("scenario:budget", "Board Budget", "fpna_scenarios", "scenario_id", "budget"),
            _concept(
                "scenario:forecast",
                "Q1 Forecast",
                "fpna_scenarios",
                "scenario_id",
                "forecast",
            ),
        ],
        "metrics": [
            {
                "id": "metric:budget_vs_actuals",
                "name": "Budget vs actuals",
                "description": "Compares actual financial performance against the board budget.",
                "validation_state": "seeded",
                "depends_on": ["account:revenue", "scenario:actual", "scenario:budget"],
            },
            {
                "id": "metric:forecast_movement",
                "name": "Forecast movement",
                "description": "Compares current forecast expectations against actuals.",
                "validation_state": "seeded",
                "depends_on": ["account:revenue", "scenario:actual", "scenario:forecast"],
            },
            {
                "id": "metric:department_spend",
                "name": "Department spend",
                "description": "Explains operating expense by department.",
                "validation_state": "seeded",
                "depends_on": [
                    "account:payroll",
                    "account:cloud_hosting",
                    "account:marketing_spend",
                    "department:sales",
                    "department:marketing",
                    "department:engineering",
                    "department:g_and_a",
                    "scenario:actual",
                ],
            },
            {
                "id": "metric:revenue_driver",
                "name": "Revenue driver",
                "description": "Connects revenue outcomes to operational drivers.",
                "validation_state": "seeded",
                "depends_on": ["account:revenue", "account:headcount", "scenario:actual"],
            },
            {
                "id": "metric:variance",
                "name": "Variance",
                "description": "Computes actual minus plan variance for finance review.",
                "validation_state": "seeded",
                "depends_on": ["scenario:actual", "scenario:budget"],
            },
        ],
    }


def _concept(
    concept_id: str,
    name: str,
    dwh_table: str,
    dwh_key: str,
    dwh_value: str,
) -> dict[str, str]:
    return {
        "id": concept_id,
        "name": name,
        "validation_state": "seeded",
        "dwh_table": dwh_table,
        "dwh_key": dwh_key,
        "dwh_value": dwh_value,
    }


def _seed_cypher() -> str:
    return starter_graph_cypher_artifacts()["seed"]


def _cypher_statements(cypher: str) -> list[str]:
    return [statement.strip() for statement in cypher.split(";") if statement.strip()]


def _concept_count_query() -> str:
    return """
    MATCH (concept:SemanticConcept)
    RETURN
        CASE
            WHEN concept:AccountConcept THEN 'AccountConcept'
            WHEN concept:DepartmentConcept THEN 'DepartmentConcept'
            WHEN concept:FinanceDomain THEN 'FinanceDomain'
            WHEN concept:MetricConcept THEN 'MetricConcept'
            WHEN concept:ScenarioConcept THEN 'ScenarioConcept'
            ELSE 'SemanticConcept'
        END AS concept_type,
        count(*) AS count
    ORDER BY concept_type
    """


def _relationship_count_query() -> str:
    return """
    MATCH (:SemanticConcept)-[relationship]->()
    RETURN type(relationship) AS relationship_type, count(*) AS count
    ORDER BY relationship_type
    """


def _dwh_reference_query() -> str:
    return """
    MATCH (concept:SemanticConcept)-[:REFERENCES_DWH_DIMENSION]->(reference:DwhDimension)
    RETURN
        concept.id AS concept_id,
        concept.name AS concept_name,
        reference.table AS dwh_table,
        reference.key AS dwh_key,
        reference.value AS dwh_value
    ORDER BY concept_id
    """


def _metric_dependency_query() -> str:
    return """
    MATCH (metric:MetricConcept)-[:DEPENDS_ON]->(dependency:SemanticConcept)
    WITH metric, dependency
    ORDER BY dependency.id
    RETURN
        metric.id AS metric_id,
        metric.name AS metric_name,
        collect(dependency.id) AS dependency_ids
    ORDER BY metric_id
    """


def _require_loaded(session: Any) -> None:
    row = session.run(
        "MATCH (domain:FinanceDomain {id: 'domain:fpna_starter'}) RETURN count(domain) AS count"
    ).single()
    if row is None or row["count"] == 0:
        raise StarterGraphError("Starter graph has not been loaded")


def _summary_from_rows(
    database: str,
    concept_rows: Any,
    relationship_rows: Any,
) -> StarterGraphLoadSummary:
    return StarterGraphLoadSummary(
        schema_version=STARTER_GRAPH_SCHEMA_VERSION,
        database=database,
        concept_counts=_records_to_dict(concept_rows),
        relationship_counts=_records_to_dict(relationship_rows),
    )


def _records_to_dict(records: Any) -> dict[str, int]:
    return {record[0]: record[1] for record in records}


def _records_to_list(records: Any) -> list[dict[str, Any]]:
    return [dict(record) for record in records]
