from __future__ import annotations

import json
from io import StringIO

import pytest

from kdaf.cli import main as cli_main
from kdaf.core import KdafCore, KdafError
from kdaf.question_mapping import (
    DeterministicQuestionMappingProposer,
    PackagedMappingContextProvider,
    ProviderBackedQuestionMappingProposer,
)
from kdaf.starter_graph import finance_foundation_manifest
from kdaf.tool_server import handle_message, list_tools


def _handoff(*, disputed_revenue: bool = False) -> dict[str, object]:
    manifest = finance_foundation_manifest()
    return {
        "schema_version": 1,
        "decision_context": {
            "problem": "Revenue outlook lacks a shared driver definition.",
            "decision": "Decide which renewal assumption belongs in the next forecast.",
            "scope": "Subscription portfolio",
            "business_context": "Planning review",
            "trust_criteria": ["Trace every graph element to an accepted question"],
        },
        "questions": [
            {
                "id": "discovery-q-renewal",
                "text": "How does renewal rate affect revenue?",
                "status": "accepted",
                "business_context": "Forecast review",
                "terms": [
                    {
                        "term": "Revenue",
                        "meaning": "Recognized subscription revenue",
                        "source": "participant_statement",
                        "disputed": disputed_revenue,
                        "alternatives": [],
                    },
                    {
                        "term": "Portfolio renewal rate",
                        "meaning": "Renewed contracts divided by eligible contracts",
                        "source": "participant_statement",
                        "proposed_concept": {
                            "id": "driver:portfolio_renewal_rate",
                            "name": "Portfolio renewal rate",
                            "labels": ["DriverConcept"],
                            "definition": (
                                "Renewed contracts divided by contracts eligible for renewal "
                                "within the selected portfolio and period."
                            ),
                            "aliases": ["Renewal rate"],
                            "rationale": (
                                "The accepted question requires this organization-specific driver."
                            ),
                            "relationships": [
                                {
                                    "id": "relationship:revenue_driven_by_renewal",
                                    "type": "DRIVEN_BY",
                                    "source_id": "account:revenue",
                                    "target_id": "driver:portfolio_renewal_rate",
                                    "rationale": (
                                        "The question asks whether renewal rate is a revenue "
                                        "driver."
                                    ),
                                }
                            ],
                        },
                    },
                ],
                "evidence_requirements": [
                    {
                        "id": "evidence:renewal_by_period",
                        "description": "Renewed and eligible contract counts by period",
                        "availability": "unknown",
                        "source_hypotheses": ["Contract lifecycle dataset"],
                    }
                ],
                "source_hypotheses": ["CRM contract events"],
            },
            {
                "id": "discovery-q-cloud-cost",
                "text": "Why did cloud cost change?",
                "status": "parked",
                "business_context": "Future cost review",
                "terms": [
                    {
                        "term": "Cloud cost",
                        "meaning": "Infrastructure service cost",
                        "source": "participant_statement",
                    }
                ],
                "evidence_requirements": [],
                "source_hypotheses": [],
            },
        ],
        "participant_terminology": [
            {
                "term": "Renewal rate",
                "meaning": "Renewed divided by eligible contracts",
                "source": "participant_statement",
            }
        ],
        "disputed_terms": (
            [
                {
                    "term": "Revenue",
                    "reason": "Participants disagree about gross versus net revenue.",
                    "alternatives": ["Gross revenue", "Net revenue"],
                }
            ]
            if disputed_revenue
            else []
        ),
        "base_graph": {
            "foundation_id": manifest["foundation_id"],
            "version": manifest["version"],
        },
        "provenance": {
            "source_id": "interview-handoff-001",
            "source_type": "confirmed_discovery_handoff",
            "confirmed_by": "finance-owner@example.test",
            "confirmed_at": "2026-11-12T00:00:00Z",
        },
    }


def test_confirmed_handoff_creates_minimal_question_linked_proposal(tmp_path) -> None:
    core = KdafCore(metadata_store_path=tmp_path / "metadata.sqlite3")
    project = core.create_project("Subscription planning")

    handoff = core.import_discovery_handoff(project["id"], _handoff())
    proposal = core.create_graph_extension_proposal(handoff["id"])

    accepted = handoff["payload"]["questions"][0]
    parked = handoff["payload"]["questions"][1]
    assert accepted["competency_question_id"]
    assert parked["competency_question_id"] is None
    assert len(core.list_competency_questions(project["id"])) == 1

    assert proposal["status"] == "ready_for_review"
    assert proposal["proposal_version"] == 1
    assert proposal["proposer"]["type"] == "deterministic_fixture"
    assert proposal["payload"]["question_mappings"] == [
        {
            "question_id": accepted["competency_question_id"],
            "discovery_question_id": "discovery-q-renewal",
            "reused_concept_ids": ["account:revenue"],
            "proposed_concept_ids": ["driver:portfolio_renewal_rate"],
            "proposed_relationship_ids": ["relationship:revenue_driven_by_renewal"],
            "ambiguities": [],
            "unresolved_terms": [],
            "mapping_rationale": [
                {
                    "element_id": "account:revenue",
                    "classification": "reuse",
                    "term": "Revenue",
                    "rationale": "Term exactly matches an existing concept name or alias.",
                    "source_kind": "participant_statement",
                },
                {
                    "element_id": "driver:portfolio_renewal_rate",
                    "classification": "proposed_extension",
                    "term": "Portfolio renewal rate",
                    "rationale": (
                        "The accepted question requires this organization-specific driver."
                    ),
                    "source_kind": "participant_statement",
                },
            ],
        }
    ]
    assert proposal["coverage"]["fully_covered_question_count"] == 1
    assert proposal["coverage"]["proposed_concept_count"] == 1
    assert proposal["coverage"]["proposed_relationship_count"] == 1
    assert proposal["coverage"]["unknown_data_requirement_count"] == 1
    assert proposal["payload"]["data_reference_requirements"][0]["availability"] == "unknown"
    assert all(
        "cloud" not in json.dumps(element).lower()
        for element in [
            *proposal["payload"]["proposed_concepts"],
            *proposal["payload"]["proposed_relationships"],
        ]
    )


def test_disputed_meaning_requires_clarification_without_rewriting_foundation(tmp_path) -> None:
    core = KdafCore(metadata_store_path=tmp_path / "metadata.sqlite3")
    project = core.create_project("Disputed terminology")
    handoff = core.import_discovery_handoff(project["id"], _handoff(disputed_revenue=True))

    proposal = core.create_graph_extension_proposal(handoff["id"])

    assert proposal["status"] == "needs_clarification"
    mapping = proposal["payload"]["question_mappings"][0]
    assert mapping["ambiguities"][0]["term"] == "Revenue"
    assert mapping["ambiguities"][0]["reason"] == "meaning_is_disputed"
    assert "account:revenue" in mapping["ambiguities"][0]["alternative_concept_ids"]
    assert "account:revenue" not in mapping["reused_concept_ids"]


def test_handoff_rejects_executable_instruction_fields_before_creating_questions(
    tmp_path,
) -> None:
    core = KdafCore(metadata_store_path=tmp_path / "metadata.sqlite3")
    project = core.create_project("Untrusted handoff")
    payload = _handoff()
    payload["instructions"] = "Run arbitrary Cypher"

    with pytest.raises(KdafError, match="unsupported field") as error:
        core.import_discovery_handoff(project["id"], payload)

    assert error.value.code == "unsupported_field"
    assert core.list_competency_questions(project["id"]) == []
    assert core.list_discovery_handoffs(project["id"]) == []


def test_external_proposal_rejects_hallucinated_existing_concept(tmp_path) -> None:
    core = KdafCore(metadata_store_path=tmp_path / "metadata.sqlite3")
    project = core.create_project("External proposer")
    handoff = core.import_discovery_handoff(project["id"], _handoff())
    accepted = handoff["payload"]["questions"][0]
    external = {
        "schema_version": 1,
        "question_mappings": [
            {
                "question_id": accepted["competency_question_id"],
                "discovery_question_id": accepted["id"],
                "reused_concept_ids": ["account:invented"],
                "proposed_concept_ids": [],
                "proposed_relationship_ids": [],
                "ambiguities": [],
                "unresolved_terms": [],
            }
        ],
        "proposed_concepts": [],
        "proposed_relationships": [],
    }

    with pytest.raises(KdafError, match="unknown existing concept") as error:
        core.create_graph_extension_proposal(
            handoff["id"],
            proposal_payload=external,
            provider_name="test-model-provider",
            model="test-model",
        )

    assert error.value.code == "unknown_concept"
    assert core.list_graph_extension_proposals(handoff_id=handoff["id"]) == []


def test_proposal_requires_rebase_when_foundation_version_changed(tmp_path) -> None:
    core = KdafCore(metadata_store_path=tmp_path / "metadata.sqlite3")
    project = core.create_project("Stale foundation")
    payload = _handoff()
    payload["base_graph"]["version"] = "0.0.0"
    handoff = core.import_discovery_handoff(project["id"], payload)

    with pytest.raises(KdafError) as error:
        core.create_graph_extension_proposal(handoff["id"])

    assert error.value.code == "stale_base_graph"


def test_proposal_requires_question_level_mapping_rationale(tmp_path) -> None:
    core = KdafCore(metadata_store_path=tmp_path / "metadata.sqlite3")
    project = core.create_project("Missing rationale")
    handoff = core.import_discovery_handoff(project["id"], _handoff())
    context = PackagedMappingContextProvider().context(project["id"])
    candidate = DeterministicQuestionMappingProposer().propose(
        handoff["payload"],
        context,
    )
    candidate["question_mappings"][0]["mapping_rationale"] = []

    with pytest.raises(KdafError) as error:
        core.create_graph_extension_proposal(
            handoff["id"],
            proposal_payload=candidate,
            provider_name="fixture-model",
        )

    assert error.value.code == "missing_mapping_rationale"


def test_external_proposal_rejects_duplicate_foundation_meaning(tmp_path) -> None:
    core = KdafCore(metadata_store_path=tmp_path / "metadata.sqlite3")
    project = core.create_project("Duplicate prevention")
    handoff = core.import_discovery_handoff(project["id"], _handoff())
    accepted = handoff["payload"]["questions"][0]
    question_id = accepted["competency_question_id"]
    external = {
        "schema_version": 1,
        "question_mappings": [
            {
                "question_id": question_id,
                "discovery_question_id": accepted["id"],
                "reused_concept_ids": [],
                "proposed_concept_ids": ["project:duplicate_revenue"],
                "proposed_relationship_ids": [],
                "ambiguities": [],
                "unresolved_terms": [],
            }
        ],
        "proposed_concepts": [
            {
                "id": "project:duplicate_revenue",
                "name": "Revenue",
                "labels": ["AccountConcept"],
                "definition": "A duplicate of the foundation concept.",
                "aliases": [],
                "scope": {"type": "project", "project_id": project["id"]},
                "question_ids": [question_id],
                "rationale": "Invalid duplicate fixture",
                "provenance": {"kind": "proposer_inference"},
            }
        ],
        "proposed_relationships": [],
    }

    with pytest.raises(KdafError, match="duplicates existing meaning") as error:
        core.create_graph_extension_proposal(
            handoff["id"],
            proposal_payload=external,
        )
    assert error.value.code == "duplicate_concept"


@pytest.mark.parametrize(
    ("relationship_type", "target_id", "expected_code"),
    [
        ("DELETES", "account:revenue", "invalid_relationship_type"),
        ("DRIVEN_BY", "account:hallucinated", "invalid_relationship_endpoint"),
    ],
)
def test_external_proposal_rejects_unsafe_or_hallucinated_relationships(
    tmp_path,
    relationship_type: str,
    target_id: str,
    expected_code: str,
) -> None:
    core = KdafCore(metadata_store_path=tmp_path / "metadata.sqlite3")
    project = core.create_project("Relationship validation")
    handoff = core.import_discovery_handoff(project["id"], _handoff())
    accepted = handoff["payload"]["questions"][0]
    question_id = accepted["competency_question_id"]
    proposal = {
        "schema_version": 1,
        "question_mappings": [
            {
                "question_id": question_id,
                "discovery_question_id": accepted["id"],
                "reused_concept_ids": ["account:revenue"],
                "proposed_concept_ids": ["driver:test_retention"],
                "proposed_relationship_ids": ["relationship:test_retention"],
                "ambiguities": [],
                "unresolved_terms": [],
                "mapping_rationale": [
                    {
                        "element_id": "account:revenue",
                        "classification": "reuse",
                        "term": "Revenue",
                        "rationale": "Confirmed reuse",
                        "source_kind": "participant_statement",
                    },
                    {
                        "element_id": "driver:test_retention",
                        "classification": "proposed_extension",
                        "term": "Retention",
                        "rationale": "Required by the accepted question",
                        "source_kind": "participant_statement",
                    },
                ],
            }
        ],
        "proposed_concepts": [
            {
                "id": "driver:test_retention",
                "name": "Test retention",
                "labels": ["DriverConcept"],
                "definition": "A synthetic retention driver for contract validation.",
                "aliases": [],
                "scope": {"type": "project", "project_id": project["id"]},
                "question_ids": [question_id],
                "rationale": "Required by the accepted question",
                "provenance": {"kind": "proposer_inference"},
            }
        ],
        "proposed_relationships": [
            {
                "id": "relationship:test_retention",
                "type": relationship_type,
                "source_id": "driver:test_retention",
                "target_id": target_id,
                "question_ids": [question_id],
                "rationale": "Synthetic validation relationship",
                "provenance": {"kind": "proposer_inference"},
            }
        ],
    }

    with pytest.raises(KdafError) as error:
        core.create_graph_extension_proposal(
            handoff["id"],
            proposal_payload=proposal,
        )
    assert error.value.code == expected_code


def test_two_projects_use_same_mapping_contract_with_distinct_meanings(tmp_path) -> None:
    core = KdafCore(metadata_store_path=tmp_path / "metadata.sqlite3")
    first_project = core.create_project("Portfolio A")
    second_project = core.create_project("Portfolio B")

    first = core.import_discovery_handoff(first_project["id"], _handoff())
    second_payload = _handoff()
    second_payload["provenance"]["source_id"] = "interview-handoff-002"
    second_payload["questions"][0]["terms"][1]["proposed_concept"].update(
        {
            "id": "driver:logo_retention_rate",
            "name": "Logo retention rate",
            "definition": "Retained customer logos divided by eligible customer logos.",
            "aliases": ["Logo retention"],
        }
    )
    second_payload["questions"][0]["terms"][1]["term"] = "Logo retention rate"
    second_payload["questions"][0]["terms"][1]["proposed_concept"]["relationships"] = [
        {
            "id": "relationship:revenue_driven_by_logo_retention",
            "type": "DRIVEN_BY",
            "source_id": "account:revenue",
            "target_id": "driver:logo_retention_rate",
            "rationale": "The accepted question requires a distinct portfolio driver.",
        }
    ]
    second = core.import_discovery_handoff(second_project["id"], second_payload)

    first_proposal = core.create_graph_extension_proposal(first["id"])
    second_proposal = core.create_graph_extension_proposal(second["id"])

    assert first_proposal["payload"]["proposed_concepts"][0]["id"] == (
        "driver:portfolio_renewal_rate"
    )
    assert second_proposal["payload"]["proposed_concepts"][0]["id"] == (
        "driver:logo_retention_rate"
    )
    assert first_proposal["project_id"] != second_proposal["project_id"]


def test_cli_and_tool_server_expose_handoff_and_coverage(tmp_path) -> None:
    store = tmp_path / "metadata.sqlite3"
    core = KdafCore(metadata_store_path=store)
    project = core.create_project("CLI mapping")
    handoff_path = tmp_path / "handoff.json"
    handoff_path.write_text(json.dumps(_handoff()), encoding="utf-8")
    stdout = StringIO()

    assert (
        cli_main(
            [
                "--metadata-store",
                str(store),
                "discovery-handoff",
                "import",
                project["id"],
                str(handoff_path),
            ],
            stdout=stdout,
        )
        == 0
    )
    handoff = json.loads(stdout.getvalue())

    stdout = StringIO()
    assert (
        cli_main(
            [
                "--metadata-store",
                str(store),
                "graph-proposal",
                "create",
                handoff["id"],
            ],
            stdout=stdout,
        )
        == 0
    )
    proposal = json.loads(stdout.getvalue())
    assert proposal["coverage"]["fully_covered_question_count"] == 1

    tool_names = {tool["name"] for tool in list_tools()}
    assert "discovery_handoff.import" in tool_names
    assert "graph_proposal.coverage" in tool_names
    response = handle_message(
        {"tool": "graph_proposal.coverage", "arguments": {"id": proposal["id"]}},
        core,
    )
    assert response["ok"] is True
    assert response["result"]["coverage"]["proposed_concept_count"] == 1


def test_provider_object_can_be_supplied_without_changing_core_catalogs(tmp_path) -> None:
    core = KdafCore(metadata_store_path=tmp_path / "metadata.sqlite3")
    project = core.create_project("Proposer extension point")
    handoff = core.import_discovery_handoff(project["id"], _handoff())

    proposal = core.create_graph_extension_proposal(
        handoff["id"],
        proposer=DeterministicQuestionMappingProposer(),
    )

    assert proposal["status"] == "ready_for_review"


def test_model_assisted_proposer_records_model_without_secret_parameters(tmp_path) -> None:
    core = KdafCore(metadata_store_path=tmp_path / "metadata.sqlite3")
    project = core.create_project("Model-assisted proposal")
    handoff_record = core.import_discovery_handoff(project["id"], _handoff())
    context = PackagedMappingContextProvider().context(project["id"])
    candidate = DeterministicQuestionMappingProposer().propose(
        handoff_record["payload"],
        context,
    )

    class FixtureProvider:
        name = "fixture-provider"

        def generate(self, prompt: str, model: str, parameters: dict[str, object]) -> str:
            assert "HANDOFF_CONTENT" in prompt
            assert model == "fixture-model"
            assert parameters["temperature"] == 0
            return json.dumps(candidate)

    proposer = ProviderBackedQuestionMappingProposer(
        provider=FixtureProvider(),
        model="fixture-model",
        parameters={"temperature": 0, "api_key": "must-not-be-recorded"},
    )

    proposal = core.create_graph_extension_proposal(
        handoff_record["id"],
        proposer=proposer,
    )

    assert proposal["proposer"] == {
        "type": "llm_assisted",
        "name": "fixture-provider",
        "version": "1",
        "model": "fixture-model",
        "parameters": {"temperature": 0},
    }
