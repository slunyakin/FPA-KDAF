from __future__ import annotations

import json
import shutil
import subprocess
from io import StringIO
from pathlib import Path

import pytest

from kdaf.cli import main as cli_main
from kdaf.core import KdafCore, KdafError
from kdaf.semantic_publication import (
    SemanticPublicationError,
    SemanticPublicationService,
    _build_publication_plan,
    graph_extension_proposal_digest,
)
from kdaf.starter_graph import finance_foundation_manifest
from kdaf.tool_server import handle_message, list_tools


def _handoff(*, disputed: bool = False) -> dict[str, object]:
    manifest = finance_foundation_manifest()
    return {
        "schema_version": 1,
        "decision_context": {
            "problem": "Revenue outlook lacks a shared driver definition.",
            "decision": "Select the renewal assumption for the forecast.",
            "scope": "Subscription portfolio",
            "business_context": "Forecast review",
            "trust_criteria": ["Trace published meaning to an accepted question"],
        },
        "questions": [
            {
                "id": "discovery-q-renewal",
                "text": "How does portfolio renewal rate affect revenue?",
                "status": "accepted",
                "business_context": "Forecast review",
                "terms": [
                    {
                        "term": "Revenue",
                        "meaning": "Recognized subscription revenue",
                        "source": "participant_statement",
                        "disputed": disputed,
                        "alternatives": [],
                    },
                    {
                        "term": "Portfolio renewal rate",
                        "meaning": "Share of eligible subscriptions renewed",
                        "source": "participant_statement",
                        "disputed": False,
                        "alternatives": [],
                        "proposed_concept": {
                            "id": "driver:portfolio_renewal_rate",
                            "name": "Portfolio renewal rate",
                            "labels": ["DriverConcept"],
                            "definition": "Share of eligible subscriptions renewed.",
                            "aliases": ["Renewal rate"],
                            "rationale": "Required by the accepted forecast question.",
                            "relationships": [
                                {
                                    "id": "relationship:renewal_drives_revenue",
                                    "type": "DRIVEN_BY",
                                    "source_id": "account:revenue",
                                    "target_id": "driver:portfolio_renewal_rate",
                                    "rationale": "The question asks how renewal drives revenue.",
                                }
                            ],
                        },
                    },
                ],
                "evidence_requirements": [
                    {
                        "id": "renewal-observation",
                        "description": "Observed renewal rate by period",
                        "availability": "unknown",
                        "source_hypotheses": ["Subscription warehouse"],
                    }
                ],
                "source_hypotheses": ["Planning model"],
            }
        ],
        "participant_terminology": [
            {
                "term": "Portfolio renewal rate",
                "meaning": "Share of eligible subscriptions renewed",
                "source": "participant_statement",
            }
        ],
        "disputed_terms": [],
        "base_graph": {
            "foundation_id": manifest["foundation_id"],
            "version": manifest["version"],
        },
        "provenance": {
            "source_id": "interview:renewal",
            "source_type": "confirmed_interview_handoff",
            "confirmed_by": "finance-owner",
            "confirmed_at": "2026-11-12T00:00:00Z",
        },
    }


def _proposal(core: KdafCore, *, disputed: bool = False) -> dict[str, object]:
    project = core.create_project("Semantic publication")
    handoff = core.import_discovery_handoff(project["id"], _handoff(disputed=disputed))
    return core.create_graph_extension_proposal(handoff["id"])


class RecordingPublisher:
    def __init__(self, *, failures: int = 0) -> None:
        self.failures = failures
        self.publish_calls = 0

    def plan(self, proposal, **kwargs):
        return {
            "action": "publish",
            "proposal_id": proposal.id,
            "graph_publication_id": kwargs["graph_publication_id"],
            "database": kwargs["expected_database"],
            "conflicts": [],
        }

    def publish(self, proposal, **kwargs):
        self.publish_calls += 1
        if self.publish_calls <= self.failures:
            raise SemanticPublicationError("Neo4j is unavailable", "neo4j_unavailable")
        return {
            "status": "published",
            "action": "publish",
            "proposal_id": proposal.id,
            "graph_publication_id": kwargs["graph_publication_id"],
            "published_concept_count": len(proposal.payload["proposed_concepts"]),
            "published_relationship_count": len(proposal.payload["proposed_relationships"]),
            "published_question_scope_count": len(proposal.payload["question_mappings"]),
        }

    def question_scope(self, project_id, **kwargs):
        return {
            "project_id": project_id,
            "question_id": kwargs["question_id"],
            "scopes": [{"publication_state": "published"}],
        }


def test_exact_review_and_publication_are_idempotent(tmp_path) -> None:
    core = KdafCore(metadata_store_path=tmp_path / "metadata.sqlite3")
    proposal = _proposal(core)
    publisher = RecordingPublisher()
    service = SemanticPublicationService(core.metadata, publisher)  # type: ignore[arg-type]

    review = service.review_proposal(
        proposal["id"],
        decision="approved",
        reviewer="finance-reviewer",
        reason="Definition and question scope are confirmed.",
    )
    repeated_review = service.review_proposal(
        proposal["id"],
        decision="approved",
        reviewer="finance-reviewer",
        reason="Retry",
    )
    first = service.publish_proposal(proposal["id"], expected_database="kdaf")
    second = service.publish_proposal(proposal["id"], expected_database="kdaf")

    assert review["id"] == repeated_review["id"]
    assert review["payload"]["proposal_digest"] == graph_extension_proposal_digest(
        core.metadata.get_graph_extension_proposal(proposal["id"])
    )
    assert review["payload"]["snapshot"]["payload"]["proposed_relationships"]
    assert review["payload"]["snapshot"]["payload"]["data_reference_requirements"]
    assert first["status"] == "published"
    assert second["id"] == first["id"]
    assert second["attempt_count"] == 1
    assert publisher.publish_calls == 1


def test_rejected_or_wrong_purpose_review_does_not_activate_proposal(tmp_path) -> None:
    core = KdafCore(metadata_store_path=tmp_path / "metadata.sqlite3")
    proposal = _proposal(core)
    publisher = RecordingPublisher()
    service = SemanticPublicationService(core.metadata, publisher)  # type: ignore[arg-type]

    service.review_proposal(
        proposal["id"],
        decision="approved",
        reviewer="analyst",
        reason="Approved for exploration only.",
        purpose="analysis_experiment",
    )
    with pytest.raises(SemanticPublicationError) as wrong_purpose:
        service.publish_proposal(proposal["id"], expected_database="kdaf")
    assert wrong_purpose.value.code == "proposal_not_approved"

    service.review_proposal(
        proposal["id"],
        decision="rejected",
        reviewer="semantic-owner",
        reason="Definition requires revision.",
    )
    with pytest.raises(SemanticPublicationError) as rejected:
        service.publish_proposal(proposal["id"], expected_database="kdaf")
    assert rejected.value.code == "proposal_not_approved"
    assert publisher.publish_calls == 0


def test_ambiguous_proposal_cannot_be_approved(tmp_path) -> None:
    core = KdafCore(metadata_store_path=tmp_path / "metadata.sqlite3")
    proposal = _proposal(core, disputed=True)
    service = SemanticPublicationService(  # type: ignore[arg-type]
        core.metadata,
        RecordingPublisher(),
    )

    with pytest.raises(SemanticPublicationError) as error:
        service.review_proposal(
            proposal["id"],
            decision="approved",
            reviewer="semantic-owner",
            reason="Should not pass",
        )

    assert error.value.code == "proposal_not_reviewable"


def test_failed_publication_is_recoverable_and_does_not_report_success(tmp_path) -> None:
    core = KdafCore(metadata_store_path=tmp_path / "metadata.sqlite3")
    proposal = _proposal(core)
    publisher = RecordingPublisher(failures=1)
    service = SemanticPublicationService(core.metadata, publisher)  # type: ignore[arg-type]
    service.review_proposal(
        proposal["id"],
        decision="approved",
        reviewer="semantic-owner",
        reason="Approved for publication.",
    )

    with pytest.raises(SemanticPublicationError) as error:
        service.publish_proposal(proposal["id"], expected_database="kdaf")
    assert error.value.code == "neo4j_unavailable"
    failed = service.list_publications(proposal_id=proposal["id"])[0]
    assert failed["status"] == "failed"
    assert failed["error_code"] == "neo4j_unavailable"
    assert failed["published_at"] is None

    recovered = service.publish_proposal(proposal["id"], expected_database="kdaf")
    assert recovered["status"] == "published"
    assert recovered["attempt_count"] == 2


def test_stale_review_digest_is_rejected(tmp_path) -> None:
    core = KdafCore(metadata_store_path=tmp_path / "metadata.sqlite3")
    proposal = _proposal(core)
    service = SemanticPublicationService(  # type: ignore[arg-type]
        core.metadata,
        RecordingPublisher(),
    )
    review = service.review_proposal(
        proposal["id"],
        decision="approved",
        reviewer="semantic-owner",
        reason="Approved.",
    )
    with core.metadata._connect() as connection:
        payload = dict(review["payload"])
        payload["proposal_digest"] = "0" * 64
        connection.execute(
            "UPDATE kdaf_validation_queue SET payload_json = ? WHERE id = ?",
            (json.dumps(payload), review["id"]),
        )

    with pytest.raises(SemanticPublicationError) as error:
        service.publish_proposal(proposal["id"], expected_database="kdaf")
    assert error.value.code == "stale_approval"


def test_publication_plan_checks_foundation_scope_conflicts_and_noop(tmp_path) -> None:
    core = KdafCore(metadata_store_path=tmp_path / "metadata.sqlite3")
    proposal_dict = _proposal(core)
    proposal = core.metadata.get_graph_extension_proposal(proposal_dict["id"])
    digest = graph_extension_proposal_digest(proposal)
    manifest = finance_foundation_manifest()
    base_state = {
        "foundation": {
            "foundation_id": manifest["foundation_id"],
            "version": manifest["version"],
            "owner": "kdaf",
        },
        "publication": None,
        "concepts": {
            "account:revenue": {
                "labels": ["SemanticConcept", "AccountConcept"],
                "properties": {"id": "account:revenue", "kdaf_owner": "kdaf"},
            }
        },
        "relationships": {},
    }

    plan = _build_publication_plan(
        proposal,
        base_state,
        graph_publication_id="publication:test",
        proposal_digest=digest,
        database="kdaf",
    )
    assert plan["action"] == "publish"

    stale = {**base_state, "foundation": {**base_state["foundation"], "version": "2.0.0"}}
    with pytest.raises(SemanticPublicationError) as stale_error:
        _build_publication_plan(
            proposal,
            stale,
            graph_publication_id="publication:test",
            proposal_digest=digest,
            database="kdaf",
        )
    assert stale_error.value.code == "stale_base_graph"

    wrong_owner = {
        **base_state,
        "foundation": {**base_state["foundation"], "owner": "another-loader"},
    }
    with pytest.raises(SemanticPublicationError) as owner_error:
        _build_publication_plan(
            proposal,
            wrong_owner,
            graph_publication_id="publication:test",
            proposal_digest=digest,
            database="kdaf",
        )
    assert owner_error.value.code == "foundation_ownership_conflict"

    conflict = {
        **base_state,
        "concepts": {
            **base_state["concepts"],
            "driver:portfolio_renewal_rate": {
                "labels": ["SemanticConcept", "DriverConcept"],
                "properties": {"id": "driver:portfolio_renewal_rate"},
            },
        },
    }
    with pytest.raises(SemanticPublicationError) as conflict_error:
        _build_publication_plan(
            proposal,
            conflict,
            graph_publication_id="publication:test",
            proposal_digest=digest,
            database="kdaf",
        )
    assert conflict_error.value.code == "publication_conflict"

    noop = {
        **base_state,
        "publication": {"status": "published", "proposal_digest": digest},
    }
    assert (
        _build_publication_plan(
            proposal,
            noop,
            graph_publication_id="publication:test",
            proposal_digest=digest,
            database="kdaf",
        )["action"]
        == "noop"
    )


def test_cli_and_tool_server_expose_exact_review_contract(tmp_path) -> None:
    store = tmp_path / "metadata.sqlite3"
    core = KdafCore(metadata_store_path=store)
    proposal = _proposal(core)
    stdout = StringIO()

    assert (
        cli_main(
            [
                "--metadata-store",
                str(store),
                "graph-proposal",
                "review",
                proposal["id"],
                "approved",
                "--reviewer",
                "finance-owner",
                "--reason",
                "Confirmed meaning and scope",
            ],
            stdout=stdout,
        )
        == 0
    )
    assert json.loads(stdout.getvalue())["status"] == "approved"

    tool_names = {item["name"] for item in list_tools()}
    assert {
        "graph_proposal.review",
        "graph_publication.plan",
        "graph_publication.publish",
        "graph_publication.question_scope",
    }.issubset(tool_names)
    response = handle_message(
        {
            "tool": "graph_proposal.review_get",
            "arguments": {"id": proposal["id"]},
        },
        core,
    )
    assert response["ok"] is True
    assert response["result"]["payload"]["purpose"] == "semantic_publication"


def test_core_rejects_publication_without_review_before_connecting_to_neo4j(tmp_path) -> None:
    core = KdafCore(metadata_store_path=tmp_path / "metadata.sqlite3")
    proposal = _proposal(core)

    with pytest.raises(KdafError) as error:
        core.publish_graph_extension_proposal(proposal["id"], "kdaf")

    assert error.value.code == "proposal_not_approved"


@pytest.mark.integration
def test_reviewed_extension_publishes_atomically_to_real_neo4j(tmp_path) -> None:
    neo4j = pytest.importorskip("neo4j")
    docker = shutil.which("docker")
    if docker is None:
        pytest.skip("Docker CLI is not available")
    info = subprocess.run(
        [docker, "info"],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
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
        pytest.fail(f"docker compose up neo4j failed:\n{up.stdout}\n{up.stderr}")

    project_id: str | None = None
    core = KdafCore(
        config_path=Path("config/kdaf.example.toml"),
        metadata_store_path=tmp_path / "metadata.sqlite3",
    )
    try:
        core.initialize_finance_foundation("neo4j")
        project = core.create_project("Live semantic publication")
        project_id = project["id"]
        suffix = project_id.replace("-", "_")
        payload = _handoff()
        proposed = payload["questions"][0]["terms"][1]["proposed_concept"]
        proposed["id"] = f"driver:renewal_{suffix}"
        proposed["relationships"][0]["id"] = f"relationship:renewal_{suffix}"
        proposed["relationships"][0]["target_id"] = proposed["id"]
        handoff = core.import_discovery_handoff(project_id, payload)
        proposal = core.create_graph_extension_proposal(handoff["id"])
        question_id = proposal["payload"]["question_mappings"][0]["question_id"]

        core.review_graph_extension_proposal(
            proposal["id"],
            decision="approved",
            reviewer="integration-reviewer",
            reason="Fixture definition and scope are accepted.",
        )
        plan = core.plan_graph_extension_publication(proposal["id"], "neo4j")
        first = core.publish_graph_extension_proposal(proposal["id"], "neo4j")
        second = core.publish_graph_extension_proposal(proposal["id"], "neo4j")
        scope = core.get_published_question_scope(
            project_id,
            "neo4j",
            question_id=question_id,
        )
        run = core.create_run(project_id)
        binding = core.register_question_binding(
            project_id,
            "live-renewal-scope",
            question_id,
            evidence_mode="semantic_only",
            required_concept_ids=["account:revenue", proposed["id"]],
            graph_publication_id=first["graph_publication_id"],
        )
        core.activate_question_binding(binding["id"], "neo4j")
        packet = core.execute_question_binding(
            project_id,
            "live-renewal-scope",
            run["id"],
            "neo4j",
        )

        assert plan["action"] == "publish"
        assert first["status"] == "published"
        assert second["id"] == first["id"]
        assert len(scope["scopes"]) == 1
        assert {item["id"] for item in scope["scopes"][0]["concepts"]} == {
            "account:revenue",
            proposed["id"],
        }
        assert scope["scopes"][0]["relationships"][0]["id"] == (proposed["relationships"][0]["id"])
        assert packet["binding"]["version"] == 1
        assert packet["dwh_queries"] == []
        assert {item["id"] for item in packet["graph_nodes"]} == {
            "account:revenue",
            proposed["id"],
        }
    finally:
        if project_id is not None:
            settings = core._neo4j_connection_settings()
            with (
                neo4j.GraphDatabase.driver(
                    settings.uri,
                    auth=(settings.user, settings.password),
                ) as driver,
                driver.session(database=settings.database) as session,
            ):
                session.run(
                    "MATCH (scope:KdafQuestionScope {project_id: $project_id}) DETACH DELETE scope",
                    project_id=project_id,
                ).consume()
                session.run(
                    "MATCH (publication:KdafGraphPublication {project_id: $project_id}) "
                    "DETACH DELETE publication",
                    project_id=project_id,
                ).consume()
                session.run(
                    "MATCH (record:KdafSemanticRelationshipRecord "
                    "{project_id: $project_id}) DETACH DELETE record",
                    project_id=project_id,
                ).consume()
                session.run(
                    "MATCH (concept:SemanticConcept {project_id: $project_id}) "
                    "DETACH DELETE concept",
                    project_id=project_id,
                ).consume()
        subprocess.run(
            [docker, "compose", "-f", str(compose_file), "down"],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
