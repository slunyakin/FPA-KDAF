from __future__ import annotations

import json
import shutil
import subprocess
from io import StringIO
from pathlib import Path

import pytest

from kdaf.cli import main as cli_main
from kdaf.core import KdafCore
from kdaf.starter_graph import starter_graph_cypher_artifacts, starter_graph_model
from kdaf.tool_server import handle_message, list_tools

EXPECTED_CONCEPT_COUNTS = {
    "AccountConcept": 6,
    "DepartmentConcept": 4,
    "FinanceDomain": 1,
    "MetricConcept": 5,
    "ScenarioConcept": 3,
}

EXPECTED_RELATIONSHIP_COUNTS = {
    "DEPENDS_ON": 19,
    "HAS_CONCEPT": 18,
    "REFERENCES_DWH_DIMENSION": 13,
}


def test_starter_graph_model_has_stable_finance_concept_ids() -> None:
    model = starter_graph_model()

    assert [account["id"] for account in model["accounts"]] == [
        "account:revenue",
        "account:cogs",
        "account:payroll",
        "account:cloud_hosting",
        "account:marketing_spend",
        "account:headcount",
    ]
    assert [department["id"] for department in model["departments"]] == [
        "department:sales",
        "department:marketing",
        "department:engineering",
        "department:g_and_a",
    ]
    assert [scenario["id"] for scenario in model["scenarios"]] == [
        "scenario:actual",
        "scenario:budget",
        "scenario:forecast",
    ]
    assert "metric:budget_vs_actuals" in {metric["id"] for metric in model["metrics"]}
    assert all(
        concept["validation_state"] == "seeded"
        for group in ("accounts", "departments", "scenarios", "metrics")
        for concept in model[group]
    )


def test_starter_graph_artifacts_link_to_dwh_dimensions_not_fact_tables() -> None:
    artifacts = starter_graph_cypher_artifacts()
    combined = "\n".join(artifacts.values())

    assert "SemanticConcept" in combined
    assert "REFERENCES_DWH_DIMENSION" in combined
    assert "DwhDimension" in combined
    assert "fpna_accounts" in combined
    assert "fpna_departments" in combined
    assert "fpna_scenarios" in combined
    assert "fpna_facts" not in combined


def test_core_returns_starter_graph_cypher_schema(tmp_path) -> None:
    core = KdafCore(metadata_store_path=tmp_path / "metadata.sqlite3")

    schema = core.starter_graph_schema()

    assert schema["dialect"] == "cypher"
    assert "account:revenue" in schema["seed_cypher"]
    assert "metric:department_spend" in schema["seed_cypher"]
    assert "REFERENCES_DWH_DIMENSION" in schema["sample_queries_cypher"]


def test_cli_prints_starter_graph_schema(tmp_path) -> None:
    stdout = StringIO()

    exit_code = cli_main(
        ["--metadata-store", str(tmp_path / "metadata.sqlite3"), "starter-graph", "schema"],
        stdout=stdout,
    )

    assert exit_code == 0
    payload = json.loads(stdout.getvalue())
    assert payload["dialect"] == "cypher"
    assert "scenario:forecast" in payload["seed_cypher"]


def test_tool_server_exposes_starter_graph_schema(tmp_path) -> None:
    core = KdafCore(metadata_store_path=tmp_path / "metadata.sqlite3")

    assert {"name": "starter_graph.load"} in list_tools()

    response = handle_message({"tool": "starter_graph.schema", "arguments": {}}, core)

    assert response["ok"] is True
    assert response["result"]["dialect"] == "cypher"


@pytest.mark.integration
def test_starter_graph_loads_and_queries_real_neo4j(tmp_path) -> None:
    neo4j = pytest.importorskip("neo4j")
    docker = shutil.which("docker")
    if docker is None:
        pytest.skip("Docker CLI is not available")

    info = subprocess.run([docker, "info"], check=False, capture_output=True, text=True, timeout=30)
    if info.returncode != 0:
        pytest.skip("Docker daemon is not available")

    compose_file = Path("docker-compose.yml")
    up = subprocess.run(
        [docker, "compose", "-f", str(compose_file), "up", "-d", "--wait", "neo4j"],
        check=False,
        capture_output=True,
        text=True,
        timeout=180,
    )
    if up.returncode != 0:
        pytest.fail(f"docker compose up neo4j failed:\nSTDOUT:\n{up.stdout}\nSTDERR:\n{up.stderr}")

    try:
        core = KdafCore(
            config_path=Path("config/kdaf.example.toml"),
            metadata_store_path=tmp_path / "metadata.sqlite3",
        )

        foundation_first = core.initialize_finance_foundation("neo4j")
        foundation_plan = core.plan_finance_foundation("neo4j")
        foundation_context = core.inspect_finance_foundation("neo4j")

        assert foundation_first["status"] == "initialize"
        assert foundation_first["concept_counts"] == {
            "AccountConcept": 4,
            "FinanceDomain": 1,
            "MetricConcept": 4,
            "ScenarioConcept": 3,
        }
        assert foundation_first["relationship_counts"] == {
            "DEPENDS_ON": 11,
            "HAS_CONCEPT": 11,
        }
        assert foundation_plan["action"] == "noop"
        assert foundation_context["foundation_version"] == "1.0.0"
        assert foundation_context["owned_concept_count"] == 12

        settings = core._neo4j_connection_settings()
        with (
            neo4j.GraphDatabase.driver(
                settings.uri,
                auth=(settings.user, settings.password),
            ) as driver,
            driver.session(database=settings.database) as session,
        ):
            session.run(
                """
                MATCH (concept:SemanticConcept {id: 'account:revenue'})
                SET concept.validation_state = 'reviewed',
                    concept.review_note = 'project review survives initialization'
                """
            ).consume()
            session.run(
                """
                MERGE (extension:ProjectExtension {id: 'project:test:extension'})
                ON CREATE SET extension.name = 'Unmanaged project extension'
                """
            ).consume()

        foundation_second = core.initialize_finance_foundation("neo4j")
        assert foundation_second["status"] == "noop"

        with (
            neo4j.GraphDatabase.driver(
                settings.uri,
                auth=(settings.user, settings.password),
            ) as driver,
            driver.session(database=settings.database) as session,
        ):
            preserved = session.run(
                """
                MATCH (concept:SemanticConcept {id: 'account:revenue'})
                MATCH (extension:ProjectExtension {id: 'project:test:extension'})
                RETURN concept.validation_state AS state,
                       concept.review_note AS note,
                       extension.name AS extension_name
                """
            ).single()
            binding_count = session.run(
                "MATCH (:SemanticConcept)-[r:REFERENCES_DWH_DIMENSION]->() "
                "RETURN count(r) AS count"
            ).single()["count"]
        assert preserved["state"] == "reviewed"
        assert preserved["note"] == "project review survives initialization"
        assert preserved["extension_name"] == "Unmanaged project extension"
        assert binding_count == 0

        first = core.load_starter_graph()
        second = core.load_starter_graph()
        context = core.starter_graph_context()

        assert first["concept_counts"] == EXPECTED_CONCEPT_COUNTS
        assert first["relationship_counts"] == EXPECTED_RELATIONSHIP_COUNTS
        assert second["concept_counts"] == first["concept_counts"]
        assert second["relationship_counts"] == first["relationship_counts"]
        assert len(context["dwh_references"]) == 13
        assert {row["dwh_table"] for row in context["dwh_references"]} == {
            "fpna_accounts",
            "fpna_departments",
            "fpna_scenarios",
        }
        assert context["metric_dependencies"][0]["metric_id"] == "metric:budget_vs_actuals"

        with (
            neo4j.GraphDatabase.driver(
                settings.uri,
                auth=(settings.user, settings.password),
            ) as driver,
            driver.session(database=settings.database) as session,
        ):
            preserved_after_profile = session.run(
                """
                MATCH (concept:SemanticConcept {id: 'account:revenue'})
                MATCH (extension:ProjectExtension {id: 'project:test:extension'})
                RETURN concept.validation_state AS state,
                       concept.review_note AS note,
                       extension.name AS extension_name
                """
            ).single()
        assert preserved_after_profile["state"] == "reviewed"
        assert preserved_after_profile["note"] == "project review survives initialization"
        assert preserved_after_profile["extension_name"] == "Unmanaged project extension"
    finally:
        subprocess.run(
            [docker, "compose", "-f", str(compose_file), "down"],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
