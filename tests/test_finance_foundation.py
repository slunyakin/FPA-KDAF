from __future__ import annotations

import json
from io import StringIO

import pytest

import kdaf.starter_graph as starter_graph
from kdaf.cli import main as cli_main
from kdaf.core import KdafCore
from kdaf.starter_graph import (
    CORE_COMPONENT,
    STARTER_BINDINGS_COMPONENT,
    STARTER_PROFILE_COMPONENT,
    Neo4jConnectionSettings,
    StarterGraphError,
    StarterGraphRepository,
    finance_foundation_manifest,
)
from kdaf.tool_server import handle_message, list_tools


def test_finance_foundation_manifest_separates_portable_and_starter_content() -> None:
    manifest = finance_foundation_manifest()

    assert manifest["foundation_id"] == "kdaf.finance.foundation"
    assert manifest["version"] == "1.0.0"
    assert manifest["owner"] == "kdaf"
    assert manifest["provenance"]["source"].endswith("foundation_manifest.json")

    concepts_by_component: dict[str, set[str]] = {}
    for concept in manifest["concepts"]:
        concepts_by_component.setdefault(concept["component_id"], set()).add(concept["id"])
        assert concept["description"]

    assert "account:revenue" in concepts_by_component[CORE_COMPONENT]
    assert "scenario:budget" in concepts_by_component[CORE_COMPONENT]
    assert "department:sales" not in concepts_by_component[CORE_COMPONENT]
    assert "department:sales" in concepts_by_component[STARTER_PROFILE_COMPONENT]
    assert manifest["starter_dwh_bindings"]
    assert all("dwh_table" not in concept for concept in manifest["concepts"])


def test_repository_requires_an_exact_explicit_database_target() -> None:
    calls: list[tuple[object, object]] = []

    def driver_factory(*args: object, **kwargs: object) -> object:
        calls.append((args, kwargs))
        raise AssertionError("driver must not be created for an invalid target")

    repository = StarterGraphRepository(
        Neo4jConnectionSettings(
            uri="bolt://example.invalid:7687",
            user="neo4j",
            password="secret",
            database="kdaf",
        ),
        driver_factory=driver_factory,
    )

    with pytest.raises(StarterGraphError, match="must be supplied") as missing:
        repository.initialize_foundation(expected_database="")
    assert missing.value.code == "missing_database_target"

    with pytest.raises(StarterGraphError, match="does not match") as mismatch:
        repository.plan_foundation(expected_database="neo4j")
    assert mismatch.value.code == "database_target_mismatch"
    assert calls == []


def test_starter_bindings_require_the_starter_profile() -> None:
    repository = StarterGraphRepository(
        Neo4jConnectionSettings(
            uri="bolt://example.invalid:7687",
            user="neo4j",
            password="secret",
            database="kdaf",
        ),
        driver_factory=lambda *args, **kwargs: None,
    )

    with pytest.raises(StarterGraphError, match="require the starter profile") as error:
        repository.initialize_foundation(
            expected_database="kdaf",
            include_starter_bindings=True,
        )
    assert error.value.code == "invalid_component_selection"


def test_reinitialization_plan_preserves_review_and_custom_properties() -> None:
    manifest = finance_foundation_manifest()
    selection = starter_graph._manifest_selection(
        manifest,
        include_starter_profile=False,
        include_starter_bindings=False,
    )
    digest = starter_graph._component_digests(manifest, selection)[CORE_COMPONENT]
    state = {
        "concepts": {
            concept["id"]: {
                "labels": ["SemanticConcept", *concept["labels"]],
                "properties": {
                    "id": concept["id"],
                    "name": concept["name"],
                    "description": concept["description"],
                    "kdaf_owner": "kdaf",
                    "kdaf_component_id": CORE_COMPONENT,
                    "kdaf_foundation_version": manifest["version"],
                    "validation_state": "reviewed",
                    "project_review_note": "keep me",
                },
            }
            for concept in selection["concepts"]
        },
        "references": {},
        "relationships": {
            (
                relationship["source_id"],
                relationship["type"],
                relationship["target_id"],
            ): {"kdaf_owner": "kdaf", "project_review_note": "keep me"}
            for relationship in selection["relationships"]
        },
        "installations": {
            CORE_COMPONENT: {
                "owner": "kdaf",
                "version": manifest["version"],
                "manifest_digest": digest,
            }
        },
    }

    plan = starter_graph._build_foundation_plan(manifest, selection, state)

    assert plan["action"] == "noop"
    assert plan["conflicts"] == []

    state["concepts"]["account:revenue"]["properties"]["name"] = "Local revenue meaning"
    conflict_plan = starter_graph._build_foundation_plan(manifest, selection, state)
    assert conflict_plan["action"] == "review_required"
    assert {item["reason"] for item in conflict_plan["conflicts"]} == {
        "concept_name_conflict"
    }


def test_known_seeded_legacy_concepts_receive_a_reviewable_migration_plan() -> None:
    manifest = finance_foundation_manifest()
    selection = starter_graph._manifest_selection(
        manifest,
        include_starter_profile=False,
        include_starter_bindings=False,
    )
    state = {
        "concepts": {
            concept["id"]: {
                "labels": ["SemanticConcept", *concept["labels"]],
                "properties": {
                    "id": concept["id"],
                    "name": concept.get("legacy_names", [concept["name"]])[0],
                    "description": concept.get("legacy_descriptions", [None])[0],
                    "validation_state": "seeded",
                },
            }
            for concept in selection["concepts"]
        },
        "references": {},
        "relationships": {
            (
                relationship["source_id"],
                relationship["type"],
                relationship["target_id"],
            ): {}
            for relationship in selection["relationships"]
        },
        "installations": {},
    }

    plan = starter_graph._build_foundation_plan(manifest, selection, state)

    assert plan["action"] == "migrate_legacy"
    assert plan["conflicts"] == []
    assert set(plan["adoptable_concepts"]) == {
        concept["id"] for concept in selection["concepts"]
    }


def test_core_and_cli_expose_manifest_without_neo4j(tmp_path) -> None:
    core = KdafCore(metadata_store_path=tmp_path / "metadata.sqlite3")
    assert core.finance_foundation_manifest()["version"] == "1.0.0"

    stdout = StringIO()
    exit_code = cli_main(
        [
            "--metadata-store",
            str(tmp_path / "cli-metadata.sqlite3"),
            "finance-foundation",
            "manifest",
        ],
        stdout=stdout,
    )
    assert exit_code == 0
    assert json.loads(stdout.getvalue())["foundation_id"] == "kdaf.finance.foundation"


def test_tool_server_exposes_foundation_contract(tmp_path) -> None:
    core = KdafCore(metadata_store_path=tmp_path / "metadata.sqlite3")

    tool_names = {tool["name"] for tool in list_tools()}
    assert {
        "finance_foundation.manifest",
        "finance_foundation.plan",
        "finance_foundation.initialize",
        "finance_foundation.inspect",
    }.issubset(tool_names)

    response = handle_message(
        {"tool": "finance_foundation.manifest", "arguments": {}},
        core,
    )
    assert response["ok"] is True
    assert response["result"]["owner"] == "kdaf"
    assert {component["id"] for component in response["result"]["components"]} == {
        CORE_COMPONENT,
        STARTER_PROFILE_COMPONENT,
        STARTER_BINDINGS_COMPONENT,
    }
