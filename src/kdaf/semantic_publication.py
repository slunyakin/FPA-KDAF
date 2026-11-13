"""Purpose-specific review and controlled publication of graph extension proposals."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from kdaf.metadata import (
    GraphExtensionProposalRecord,
    MetadataError,
    MetadataRepository,
    ValidationItem,
)
from kdaf.question_mapping import ALLOWED_CONCEPT_LABELS, ALLOWED_RELATIONSHIP_TYPES
from kdaf.starter_graph import CORE_COMPONENT, Neo4jConnectionSettings

SEMANTIC_PUBLICATION_PURPOSE = "semantic_publication"
REVIEW_CONTRACT_VERSION = 1
PUBLICATION_CONTRACT_VERSION = 1


class SemanticPublicationError(ValueError):
    """Stable review and publication error."""

    def __init__(self, message: str, code: str = "semantic_publication_error") -> None:
        super().__init__(message)
        self.code = code


def graph_extension_proposal_snapshot(
    proposal: GraphExtensionProposalRecord,
) -> dict[str, Any]:
    """Return the immutable material a reviewer approves or rejects."""

    return {
        "proposal_id": proposal.id,
        "proposal_version": proposal.proposal_version,
        "project_id": proposal.project_id,
        "handoff_id": proposal.handoff_id,
        "base_graph_version": proposal.base_graph_version,
        "proposer": proposal.proposer,
        "payload": proposal.payload,
        "coverage": proposal.coverage,
    }


def graph_extension_proposal_digest(proposal: GraphExtensionProposalRecord) -> str:
    encoded = json.dumps(
        graph_extension_proposal_snapshot(proposal),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class Neo4jGraphExtensionPublisher:
    """Publish only validated proposal fields using controlled Cypher templates."""

    settings: Neo4jConnectionSettings
    driver_factory: Any | None = None

    def plan(
        self,
        proposal: GraphExtensionProposalRecord,
        *,
        expected_database: str,
        graph_publication_id: str,
        proposal_digest: str,
    ) -> dict[str, Any]:
        self._validate_target(expected_database)
        driver = self._driver()
        try:
            with driver:
                self._verify_connectivity(driver)
                with driver.session(database=self.settings.database) as session:
                    state = _read_publication_state(
                        session,
                        proposal,
                        graph_publication_id=graph_publication_id,
                    )
            return _build_publication_plan(
                proposal,
                state,
                graph_publication_id=graph_publication_id,
                proposal_digest=proposal_digest,
                database=self.settings.database,
            )
        except SemanticPublicationError:
            raise
        except Exception as exc:
            raise SemanticPublicationError(
                _safe_neo4j_failure("Publication planning", exc),
                _neo4j_error_code(exc),
            ) from exc

    def publish(
        self,
        proposal: GraphExtensionProposalRecord,
        *,
        expected_database: str,
        graph_publication_id: str,
        proposal_digest: str,
        review_id: str,
    ) -> dict[str, Any]:
        self._validate_target(expected_database)
        driver = self._driver()
        try:
            with driver:
                self._verify_connectivity(driver)
                with driver.session(database=self.settings.database) as session:
                    _ensure_publication_constraints(session)
                    transaction = getattr(session, "execute_write", None)
                    if transaction is None:
                        transaction = session.write_transaction
                    return transaction(
                        _publish_transaction,
                        proposal,
                        graph_publication_id,
                        proposal_digest,
                        review_id,
                        self.settings.database,
                    )
        except SemanticPublicationError:
            raise
        except Exception as exc:
            raise SemanticPublicationError(
                _safe_neo4j_failure("Graph extension publication", exc),
                _neo4j_error_code(exc),
            ) from exc

    def question_scope(
        self,
        project_id: str,
        *,
        expected_database: str,
        question_id: str | None = None,
        graph_publication_id: str | None = None,
    ) -> dict[str, Any]:
        self._validate_target(expected_database)
        driver = self._driver()
        try:
            with driver:
                self._verify_connectivity(driver)
                with driver.session(database=self.settings.database) as session:
                    scopes = _read_question_scopes(
                        session,
                        project_id=project_id,
                        question_id=question_id,
                        graph_publication_id=graph_publication_id,
                    )
            return {
                "database": self.settings.database,
                "project_id": project_id,
                "question_id": question_id,
                "graph_publication_id": graph_publication_id,
                "scopes": scopes,
            }
        except SemanticPublicationError:
            raise
        except Exception as exc:
            raise SemanticPublicationError(
                _safe_neo4j_failure("Question scope retrieval", exc),
                _neo4j_error_code(exc),
            ) from exc

    def _validate_target(self, expected_database: str) -> None:
        if not isinstance(expected_database, str) or not expected_database.strip():
            raise SemanticPublicationError(
                "The expected Neo4j database must be supplied explicitly",
                "missing_database_target",
            )
        if expected_database.strip() != self.settings.database:
            raise SemanticPublicationError(
                "The expected Neo4j database does not match the configured target",
                "database_target_mismatch",
            )

    def _driver(self) -> Any:
        factory = self.driver_factory
        if factory is None:
            try:
                from neo4j import GraphDatabase
            except ImportError as exc:
                raise SemanticPublicationError(
                    "Neo4j driver is not installed. Install 'kdaf[neo4j]' and retry.",
                    "neo4j_driver_missing",
                ) from exc
            factory = GraphDatabase.driver
        try:
            return factory(
                self.settings.uri,
                auth=(self.settings.user, self.settings.password),
            )
        except SemanticPublicationError:
            raise
        except Exception as exc:
            raise SemanticPublicationError(
                _safe_neo4j_failure("Neo4j driver creation", exc),
                _neo4j_error_code(exc),
            ) from exc

    @staticmethod
    def _verify_connectivity(driver: Any) -> None:
        verifier = getattr(driver, "verify_connectivity", None)
        if verifier is not None:
            verifier()


class SemanticPublicationService:
    """Coordinate exact review, metadata recovery, and graph publication."""

    def __init__(
        self,
        metadata: MetadataRepository,
        publisher: Neo4jGraphExtensionPublisher,
    ) -> None:
        self.metadata = metadata
        self.publisher = publisher

    def review_proposal(
        self,
        proposal_id: str,
        *,
        decision: str,
        reviewer: str,
        reason: str,
        purpose: str = SEMANTIC_PUBLICATION_PURPOSE,
    ) -> dict[str, Any]:
        cleaned_decision = decision.strip().lower() if isinstance(decision, str) else ""
        if cleaned_decision not in {"approved", "rejected"}:
            raise SemanticPublicationError(
                "Review decision must be approved or rejected",
                "invalid_review_decision",
            )
        if not isinstance(reviewer, str) or not reviewer.strip():
            raise SemanticPublicationError("Reviewer is required", "invalid_input")
        if not isinstance(reason, str) or not reason.strip():
            raise SemanticPublicationError("Review reason is required", "invalid_input")
        if not isinstance(purpose, str) or not purpose.strip():
            raise SemanticPublicationError("Review purpose is required", "invalid_input")
        cleaned_purpose = purpose.strip()
        try:
            proposal = self.metadata.get_graph_extension_proposal(proposal_id)
            if cleaned_decision == "approved" and proposal.status != "ready_for_review":
                raise SemanticPublicationError(
                    "A proposal requiring clarification cannot be approved",
                    "proposal_not_reviewable",
                )
            digest = graph_extension_proposal_digest(proposal)
            review_payload = {
                "review_contract_version": REVIEW_CONTRACT_VERSION,
                "purpose": cleaned_purpose,
                "proposal_id": proposal.id,
                "proposal_version": proposal.proposal_version,
                "proposal_digest": digest,
                "base_graph_version": proposal.base_graph_version,
                "snapshot": graph_extension_proposal_snapshot(proposal),
            }
            review = self.metadata.enqueue_graph_extension_review(
                proposal.id,
                cleaned_purpose,
                review_payload,
            )
            _validate_exact_review(review, proposal, purpose=cleaned_purpose)
            if review.status == cleaned_decision:
                return review.to_dict()
            if review.status != "pending":
                raise SemanticPublicationError(
                    "This exact proposal already has a different terminal review decision",
                    "review_already_decided",
                )
            return self.metadata.decide_validation(
                review.id,
                cleaned_decision,
                reviewer,
                reason,
            ).to_dict()
        except SemanticPublicationError:
            raise
        except MetadataError as exc:
            raise SemanticPublicationError(str(exc), exc.code) from exc

    def get_review(
        self,
        proposal_id: str,
        *,
        purpose: str = SEMANTIC_PUBLICATION_PURPOSE,
    ) -> dict[str, Any] | None:
        try:
            review = self.metadata.get_graph_extension_review(proposal_id, purpose)
            return None if review is None else review.to_dict()
        except MetadataError as exc:
            raise SemanticPublicationError(str(exc), exc.code) from exc

    def plan_publication(
        self,
        proposal_id: str,
        *,
        expected_database: str,
        purpose: str = SEMANTIC_PUBLICATION_PURPOSE,
    ) -> dict[str, Any]:
        proposal, review, digest, graph_id = self._approved_material(
            proposal_id,
            purpose=purpose,
        )
        plan = self.publisher.plan(
            proposal,
            expected_database=expected_database,
            graph_publication_id=graph_id,
            proposal_digest=digest,
        )
        return {**plan, "review_id": review.id, "purpose": purpose}

    def publish_proposal(
        self,
        proposal_id: str,
        *,
        expected_database: str,
        purpose: str = SEMANTIC_PUBLICATION_PURPOSE,
    ) -> dict[str, Any]:
        proposal, review, digest, graph_id = self._approved_material(
            proposal_id,
            purpose=purpose,
        )
        self.publisher.plan(
            proposal,
            expected_database=expected_database,
            graph_publication_id=graph_id,
            proposal_digest=digest,
        )
        try:
            publication = self.metadata.reserve_graph_extension_publication(
                proposal_id=proposal.id,
                database_name=expected_database,
                graph_publication_id=graph_id,
                proposal_digest=digest,
                review_id=review.id,
            )
            if publication.status == "published":
                return publication.to_dict()
            publication = self.metadata.begin_graph_extension_publication(publication.id)
            try:
                summary = self.publisher.publish(
                    proposal,
                    expected_database=expected_database,
                    graph_publication_id=graph_id,
                    proposal_digest=digest,
                    review_id=review.id,
                )
            except SemanticPublicationError as exc:
                self.metadata.fail_graph_extension_publication(
                    publication.id,
                    error_code=exc.code,
                    error_message=str(exc),
                )
                raise
            return self.metadata.complete_graph_extension_publication(
                publication.id,
                summary,
            ).to_dict()
        except SemanticPublicationError:
            raise
        except MetadataError as exc:
            raise SemanticPublicationError(str(exc), exc.code) from exc

    def get_publication(self, publication_id: str) -> dict[str, Any]:
        try:
            return self.metadata.get_graph_extension_publication(publication_id).to_dict()
        except MetadataError as exc:
            raise SemanticPublicationError(str(exc), exc.code) from exc

    def list_publications(
        self,
        *,
        project_id: str | None = None,
        proposal_id: str | None = None,
    ) -> list[dict[str, Any]]:
        try:
            return [
                item.to_dict()
                for item in self.metadata.list_graph_extension_publications(
                    project_id=project_id,
                    proposal_id=proposal_id,
                )
            ]
        except MetadataError as exc:
            raise SemanticPublicationError(str(exc), exc.code) from exc

    def question_scope(
        self,
        project_id: str,
        *,
        expected_database: str,
        question_id: str | None = None,
        graph_publication_id: str | None = None,
    ) -> dict[str, Any]:
        try:
            self.metadata.get_project(project_id)
        except MetadataError as exc:
            raise SemanticPublicationError(str(exc), exc.code) from exc
        return self.publisher.question_scope(
            project_id,
            expected_database=expected_database,
            question_id=question_id,
            graph_publication_id=graph_publication_id,
        )

    def _approved_material(
        self,
        proposal_id: str,
        *,
        purpose: str,
    ) -> tuple[GraphExtensionProposalRecord, ValidationItem, str, str]:
        if not isinstance(purpose, str) or not purpose.strip():
            raise SemanticPublicationError("Review purpose is required", "invalid_input")
        cleaned_purpose = purpose.strip()
        try:
            proposal = self.metadata.get_graph_extension_proposal(proposal_id)
            if proposal.status != "ready_for_review":
                raise SemanticPublicationError(
                    "Proposal still requires clarification",
                    "proposal_not_reviewable",
                )
            review = self.metadata.get_graph_extension_review(proposal.id, cleaned_purpose)
            if review is None or review.status != "approved":
                raise SemanticPublicationError(
                    "Proposal is not approved for semantic publication",
                    "proposal_not_approved",
                )
            digest = _validate_exact_review(
                review,
                proposal,
                purpose=cleaned_purpose,
            )
            graph_id = _graph_publication_id(proposal, digest)
            return proposal, review, digest, graph_id
        except SemanticPublicationError:
            raise
        except MetadataError as exc:
            raise SemanticPublicationError(str(exc), exc.code) from exc


def _validate_exact_review(
    review: ValidationItem,
    proposal: GraphExtensionProposalRecord,
    *,
    purpose: str,
) -> str:
    digest = graph_extension_proposal_digest(proposal)
    payload = review.payload
    if (
        review.subject_type != "graph_extension_proposal"
        or review.subject_id != proposal.id
        or payload.get("purpose") != purpose
        or payload.get("proposal_version") != proposal.proposal_version
        or payload.get("proposal_digest") != digest
        or payload.get("snapshot") != graph_extension_proposal_snapshot(proposal)
    ):
        raise SemanticPublicationError(
            "Review no longer matches the exact proposal",
            "stale_approval",
        )
    return digest


def _graph_publication_id(proposal: GraphExtensionProposalRecord, digest: str) -> str:
    return f"graph-publication:{proposal.id}:v{proposal.proposal_version}:{digest[:16]}"


def _read_publication_state(
    runner: Any,
    proposal: GraphExtensionProposalRecord,
    *,
    graph_publication_id: str,
) -> dict[str, Any]:
    foundation = runner.run(
        """
        MATCH (installation:KdafFoundationInstallation {id: $component_id})
        RETURN installation.foundation_id AS foundation_id,
               installation.version AS version,
               installation.owner AS owner
        """,
        component_id=CORE_COMPONENT,
    ).single()
    publication = runner.run(
        """
        MATCH (publication:KdafGraphPublication {id: $publication_id})
        RETURN properties(publication) AS properties
        """,
        publication_id=graph_publication_id,
    ).single()
    proposed_ids = [item["id"] for item in proposal.payload["proposed_concepts"]]
    reused_ids = sorted(
        {
            concept_id
            for mapping in proposal.payload["question_mappings"]
            for concept_id in mapping["reused_concept_ids"]
        }
    )
    concepts = {
        row["id"]: {"labels": list(row["labels"]), "properties": dict(row["properties"])}
        for row in runner.run(
            """
            MATCH (concept:SemanticConcept)
            WHERE concept.id IN $concept_ids
            RETURN concept.id AS id, labels(concept) AS labels,
                   properties(concept) AS properties
            """,
            concept_ids=sorted({*proposed_ids, *reused_ids}),
        )
    }
    relationship_ids = [item["id"] for item in proposal.payload["proposed_relationships"]]
    relationships = {
        row["id"]: {
            "type": row["type"],
            "source_id": row["source_id"],
            "target_id": row["target_id"],
            "properties": dict(row["properties"]),
        }
        for row in runner.run(
            """
            MATCH (record:KdafSemanticRelationshipRecord)
            WHERE record.id IN $relationship_ids
            RETURN record.id AS id, record.relationship_type AS type,
                   record.source_id AS source_id, record.target_id AS target_id,
                   properties(record) AS properties
            """,
            relationship_ids=relationship_ids,
        )
    }
    relationships.update(
        {
            row["id"]: {
                "type": row["type"],
                "source_id": row["source_id"],
                "target_id": row["target_id"],
                "properties": dict(row["properties"]),
            }
            for row in runner.run(
                """
            MATCH (source:SemanticConcept)-[relationship]->(target:SemanticConcept)
            WHERE relationship.kdaf_id IN $relationship_ids
            RETURN relationship.kdaf_id AS id, type(relationship) AS type,
                   source.id AS source_id, target.id AS target_id,
                   properties(relationship) AS properties
            """,
                relationship_ids=relationship_ids,
            )
        }
    )
    return {
        "foundation": None if foundation is None else dict(foundation),
        "publication": None if publication is None else dict(publication["properties"]),
        "concepts": concepts,
        "relationships": relationships,
    }


def _build_publication_plan(
    proposal: GraphExtensionProposalRecord,
    state: dict[str, Any],
    *,
    graph_publication_id: str,
    proposal_digest: str,
    database: str,
) -> dict[str, Any]:
    conflicts: list[dict[str, str]] = []
    if proposal.payload.get("project_id") != proposal.project_id:
        raise SemanticPublicationError(
            "Proposal project scope changed after validation",
            "invalid_scope",
        )
    if proposal.payload["base_graph"].get("version") != proposal.base_graph_version:
        raise SemanticPublicationError(
            "Proposal base graph metadata is inconsistent",
            "stale_base_graph",
        )
    foundation = state.get("foundation")
    expected_foundation = proposal.payload["base_graph"]["foundation_id"]
    if foundation is None:
        raise SemanticPublicationError(
            "Finance foundation is not installed",
            "foundation_not_installed",
        )
    if foundation.get("foundation_id") != expected_foundation:
        raise SemanticPublicationError(
            "Foundation ID changed; proposal review is stale",
            "stale_base_graph",
        )
    if foundation.get("owner") != "kdaf":
        raise SemanticPublicationError(
            "Foundation installation ownership is invalid",
            "foundation_ownership_conflict",
        )
    if foundation.get("version") != proposal.base_graph_version:
        raise SemanticPublicationError(
            "Foundation version changed; proposal review is stale",
            "stale_base_graph",
        )

    publication = state.get("publication")
    if publication is not None:
        if publication.get("proposal_digest") != proposal_digest:
            raise SemanticPublicationError(
                "Graph publication ID is already bound to different proposal content",
                "publication_conflict",
            )
        if publication.get("status") == "published":
            return {
                "contract_version": PUBLICATION_CONTRACT_VERSION,
                "action": "noop",
                "database": database,
                "graph_publication_id": graph_publication_id,
                "proposal_id": proposal.id,
                "proposal_version": proposal.proposal_version,
                "proposal_digest": proposal_digest,
                "conflicts": [],
            }
        raise SemanticPublicationError(
            "A graph publication attempt is already in progress",
            "publication_in_progress",
        )

    proposed = {item["id"]: item for item in proposal.payload["proposed_concepts"]}
    concepts = state.get("concepts", {})
    for concept_id, concept in proposed.items():
        _publication_labels(concept["labels"])
        if concept.get("scope") != {
            "type": "project",
            "project_id": proposal.project_id,
        }:
            raise SemanticPublicationError(
                f"Proposed concept has invalid project scope: {concept_id}",
                "invalid_scope",
            )
        if concept_id in concepts:
            conflicts.append({"id": concept_id, "reason": "concept_id_already_exists"})

    reused_ids = {
        concept_id
        for mapping in proposal.payload["question_mappings"]
        for concept_id in mapping["reused_concept_ids"]
    }
    for concept_id in reused_ids:
        concept = concepts.get(concept_id)
        if concept is None:
            conflicts.append({"id": concept_id, "reason": "reused_concept_missing"})
            continue
        properties = concept["properties"]
        is_foundation = properties.get("kdaf_owner") == "kdaf"
        is_same_project = (
            properties.get("scope_type") == "project"
            and properties.get("project_id") == proposal.project_id
            and properties.get("publication_state") == "published"
        )
        if not (is_foundation or is_same_project):
            conflicts.append({"id": concept_id, "reason": "reused_concept_wrong_scope"})

    for relationship in proposal.payload["proposed_relationships"]:
        _publication_relationship_type(relationship["type"])
        existing = state.get("relationships", {}).get(relationship["id"])
        if existing is not None:
            conflicts.append({"id": relationship["id"], "reason": "relationship_id_already_exists"})
        for endpoint in (relationship["source_id"], relationship["target_id"]):
            if endpoint not in proposed and endpoint not in reused_ids:
                conflicts.append({"id": endpoint, "reason": "endpoint_outside_question_scope"})

    if conflicts:
        raise SemanticPublicationError(
            f"Graph publication conflicts with existing semantic state: {conflicts[0]['reason']}",
            "publication_conflict",
        )
    return {
        "contract_version": PUBLICATION_CONTRACT_VERSION,
        "action": "publish",
        "database": database,
        "graph_publication_id": graph_publication_id,
        "proposal_id": proposal.id,
        "proposal_version": proposal.proposal_version,
        "proposal_digest": proposal_digest,
        "new_concept_ids": sorted(proposed),
        "new_relationship_ids": sorted(
            item["id"] for item in proposal.payload["proposed_relationships"]
        ),
        "question_ids": sorted(
            item["question_id"] for item in proposal.payload["question_mappings"]
        ),
        "conflicts": [],
    }


def _ensure_publication_constraints(session: Any) -> None:
    for statement in (
        "CREATE CONSTRAINT kdaf_graph_publication_id IF NOT EXISTS FOR "
        "(publication:KdafGraphPublication) REQUIRE publication.id IS UNIQUE",
        "CREATE CONSTRAINT kdaf_question_scope_id IF NOT EXISTS FOR "
        "(scope:KdafQuestionScope) REQUIRE scope.id IS UNIQUE",
        "CREATE CONSTRAINT kdaf_semantic_relationship_record_id IF NOT EXISTS FOR "
        "(record:KdafSemanticRelationshipRecord) REQUIRE record.id IS UNIQUE",
    ):
        session.run(statement).consume()


def _publish_transaction(
    transaction: Any,
    proposal: GraphExtensionProposalRecord,
    graph_publication_id: str,
    proposal_digest: str,
    review_id: str,
    database: str,
) -> dict[str, Any]:
    state = _read_publication_state(
        transaction,
        proposal,
        graph_publication_id=graph_publication_id,
    )
    plan = _build_publication_plan(
        proposal,
        state,
        graph_publication_id=graph_publication_id,
        proposal_digest=proposal_digest,
        database=database,
    )
    if plan["action"] == "noop":
        return {
            **plan,
            "status": "noop",
            "published_concept_count": len(proposal.payload["proposed_concepts"]),
            "published_relationship_count": len(proposal.payload["proposed_relationships"]),
            "published_question_scope_count": len(proposal.payload["question_mappings"]),
        }

    attempt_token = str(uuid4())
    marker = transaction.run(
        """
        MERGE (publication:KdafGraphPublication {id: $publication_id})
        ON CREATE SET publication.attempt_token = $attempt_token,
                      publication.status = 'publishing',
                      publication.proposal_id = $proposal_id,
                      publication.proposal_version = $proposal_version,
                      publication.proposal_digest = $proposal_digest,
                      publication.project_id = $project_id,
                      publication.review_id = $review_id,
                      publication.database_name = $database,
                      publication.base_graph_version = $base_graph_version,
                      publication.created_at = datetime()
        RETURN publication.attempt_token AS attempt_token,
               publication.status AS status,
               publication.proposal_digest AS proposal_digest
        """,
        publication_id=graph_publication_id,
        attempt_token=attempt_token,
        proposal_id=proposal.id,
        proposal_version=proposal.proposal_version,
        proposal_digest=proposal_digest,
        project_id=proposal.project_id,
        review_id=review_id,
        database=database,
        base_graph_version=proposal.base_graph_version,
    ).single()
    if marker["attempt_token"] != attempt_token:
        if marker["status"] == "published" and marker["proposal_digest"] == proposal_digest:
            return {**plan, "status": "noop"}
        raise SemanticPublicationError(
            "A graph publication attempt is already in progress",
            "publication_in_progress",
        )

    for concept in proposal.payload["proposed_concepts"]:
        labels = _publication_labels(concept["labels"])
        properties = {
            "name": concept["name"],
            "description": concept["definition"],
            "definition": concept["definition"],
            "aliases": concept["aliases"],
            "scope_type": "project",
            "project_id": proposal.project_id,
            "kdaf_owner": f"project:{proposal.project_id}",
            "publication_state": "published",
            "graph_publication_id": graph_publication_id,
            "proposal_id": proposal.id,
            "proposal_version": proposal.proposal_version,
            "question_ids": concept["question_ids"],
            "rationale": concept["rationale"],
            "provenance_json": _canonical_json(concept["provenance"]),
        }
        transaction.run(
            f"""
            CREATE (concept:SemanticConcept:{labels} {{id: $concept_id}})
            SET concept += $properties
            """,
            concept_id=concept["id"],
            properties=properties,
        ).consume()

    for relationship in proposal.payload["proposed_relationships"]:
        relationship_type = _publication_relationship_type(relationship["type"])
        relationship_properties = {
            "relationship_type": relationship_type,
            "source_id": relationship["source_id"],
            "target_id": relationship["target_id"],
            "scope_type": "project",
            "project_id": proposal.project_id,
            "kdaf_owner": f"project:{proposal.project_id}",
            "publication_state": "published",
            "graph_publication_id": graph_publication_id,
            "proposal_id": proposal.id,
            "proposal_version": proposal.proposal_version,
            "question_ids": relationship["question_ids"],
            "rationale": relationship["rationale"],
            "provenance_json": _canonical_json(relationship["provenance"]),
        }
        transaction.run(
            """
            MATCH (publication:KdafGraphPublication {id: $publication_id})
            CREATE (record:KdafSemanticRelationshipRecord {id: $relationship_id})
            SET record += $properties
            CREATE (publication)-[:PUBLISHED_RELATIONSHIP]->(record)
            """,
            publication_id=graph_publication_id,
            relationship_id=relationship["id"],
            properties=relationship_properties,
        ).consume()
        result = transaction.run(
            f"""
            MATCH (source:SemanticConcept {{id: $source_id}})
            MATCH (target:SemanticConcept {{id: $target_id}})
            CREATE (source)-[relationship:{relationship_type}
                {{kdaf_id: $relationship_id}}]->(target)
            SET relationship += $properties
            RETURN count(relationship) AS count
            """,
            source_id=relationship["source_id"],
            target_id=relationship["target_id"],
            relationship_id=relationship["id"],
            properties=relationship_properties,
        ).single()
        if result is None or int(result["count"]) != 1:
            raise SemanticPublicationError(
                f"Relationship endpoint disappeared during publication: {relationship['id']}",
                "invalid_relationship_endpoint",
            )

    requirements_by_question: dict[str, list[dict[str, Any]]] = {}
    for requirement in proposal.payload["data_reference_requirements"]:
        requirements_by_question.setdefault(requirement["question_id"], []).append(requirement)
    for mapping in proposal.payload["question_mappings"]:
        question_id = mapping["question_id"]
        scope_id = f"question-scope:{graph_publication_id}:{question_id}"
        concept_ids = sorted(
            {
                *mapping["reused_concept_ids"],
                *mapping["proposed_concept_ids"],
            }
        )
        transaction.run(
            """
            MATCH (publication:KdafGraphPublication {id: $publication_id})
            CREATE (scope:KdafQuestionScope {id: $scope_id})
            SET scope.project_id = $project_id,
                scope.question_id = $question_id,
                scope.discovery_question_id = $discovery_question_id,
                scope.graph_publication_id = $publication_id,
                scope.proposal_id = $proposal_id,
                scope.proposal_version = $proposal_version,
                scope.concept_ids = $concept_ids,
                scope.relationship_ids = $relationship_ids,
                scope.data_reference_requirements_json = $requirements_json,
                scope.publication_state = 'published',
                scope.published_at = datetime()
            CREATE (publication)-[:PUBLISHED_SCOPE]->(scope)
            WITH scope
            MATCH (concept:SemanticConcept)
            WHERE concept.id IN $concept_ids
            CREATE (scope)-[:USES_CONCEPT {graph_publication_id: $publication_id}]->(concept)
            """,
            publication_id=graph_publication_id,
            scope_id=scope_id,
            project_id=proposal.project_id,
            question_id=question_id,
            discovery_question_id=mapping["discovery_question_id"],
            proposal_id=proposal.id,
            proposal_version=proposal.proposal_version,
            concept_ids=concept_ids,
            relationship_ids=mapping["proposed_relationship_ids"],
            requirements_json=_canonical_json(requirements_by_question.get(question_id, [])),
        ).consume()
        transaction.run(
            """
            MATCH (scope:KdafQuestionScope {id: $scope_id})
            MATCH (record:KdafSemanticRelationshipRecord)
            WHERE record.id IN $relationship_ids
            CREATE (scope)-[:USES_RELATIONSHIP
                {graph_publication_id: $publication_id}]->(record)
            """,
            scope_id=scope_id,
            relationship_ids=mapping["proposed_relationship_ids"],
            publication_id=graph_publication_id,
        ).consume()

    transaction.run(
        """
        MATCH (publication:KdafGraphPublication {id: $publication_id})
        SET publication.status = 'published',
            publication.published_at = datetime(),
            publication.concept_count = $concept_count,
            publication.relationship_count = $relationship_count,
            publication.question_scope_count = $question_scope_count
        """,
        publication_id=graph_publication_id,
        concept_count=len(proposal.payload["proposed_concepts"]),
        relationship_count=len(proposal.payload["proposed_relationships"]),
        question_scope_count=len(proposal.payload["question_mappings"]),
    ).consume()
    return {
        **plan,
        "status": "published",
        "published_concept_count": len(proposal.payload["proposed_concepts"]),
        "published_relationship_count": len(proposal.payload["proposed_relationships"]),
        "published_question_scope_count": len(proposal.payload["question_mappings"]),
    }


def _read_question_scopes(
    session: Any,
    *,
    project_id: str,
    question_id: str | None,
    graph_publication_id: str | None,
) -> list[dict[str, Any]]:
    rows = session.run(
        """
        MATCH (publication:KdafGraphPublication {status: 'published'})
              -[:PUBLISHED_SCOPE]->(scope:KdafQuestionScope {publication_state: 'published'})
        WHERE scope.project_id = $project_id
          AND ($question_id IS NULL OR scope.question_id = $question_id)
          AND ($publication_id IS NULL OR publication.id = $publication_id)
        RETURN properties(scope) AS scope
        ORDER BY scope.published_at, scope.id
        """,
        project_id=project_id,
        question_id=question_id,
        publication_id=graph_publication_id,
    )
    scopes: list[dict[str, Any]] = []
    for row in rows:
        scope = _json_safe_mapping(dict(row["scope"]))
        requirements_json = scope.pop("data_reference_requirements_json", "[]")
        concepts = [
            _json_safe_mapping(dict(item))
            for item in session.run(
                """
                MATCH (scope:KdafQuestionScope {id: $scope_id})-[:USES_CONCEPT]
                      ->(concept:SemanticConcept)
                RETURN concept.id AS id, concept.name AS name,
                       concept.description AS description,
                       concept.aliases AS aliases,
                       labels(concept) AS labels,
                       concept.scope_type AS scope_type,
                       concept.project_id AS project_id
                ORDER BY id
                """,
                scope_id=scope["id"],
            )
        ]
        relationships = [
            _json_safe_mapping(dict(item))
            for item in session.run(
                """
                MATCH (source:SemanticConcept)-[relationship]->(target:SemanticConcept)
                WHERE relationship.kdaf_id IN $relationship_ids
                RETURN relationship.kdaf_id AS id, type(relationship) AS type,
                       source.id AS source_id, target.id AS target_id,
                       relationship.rationale AS rationale
                ORDER BY id
                """,
                relationship_ids=scope.get("relationship_ids", []),
            )
        ]
        scopes.append(
            {
                **scope,
                "data_reference_requirements": json.loads(requirements_json),
                "concepts": concepts,
                "relationships": relationships,
            }
        )
    return scopes


def _publication_labels(labels: list[str]) -> str:
    if not labels or any(label not in ALLOWED_CONCEPT_LABELS for label in labels):
        raise SemanticPublicationError(
            "Proposal contains an unsupported concept label",
            "invalid_concept_type",
        )
    return ":".join(sorted(set(labels)))


def _publication_relationship_type(value: str) -> str:
    if value not in ALLOWED_RELATIONSHIP_TYPES:
        raise SemanticPublicationError(
            "Proposal contains an unsupported relationship type",
            "invalid_relationship_type",
        )
    return value


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _json_safe_mapping(value: dict[str, Any]) -> dict[str, Any]:
    return {key: _json_safe_value(item) for key, item in value.items()}


def _json_safe_value(value: Any) -> Any:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, list | tuple):
        return [_json_safe_value(item) for item in value]
    if isinstance(value, dict):
        return _json_safe_mapping(value)
    return str(value)


def _safe_neo4j_failure(action: str, error: Exception) -> str:
    error_name = type(error).__name__
    if error_name in {"AuthError", "AuthenticationError", "Unauthorized"}:
        return f"{action} failed: Neo4j authentication failed"
    if error_name in {"ServiceUnavailable", "SessionExpired", "ConnectionError"}:
        return f"{action} failed: Neo4j is unavailable"
    if error_name in {"ClientError", "DatabaseError", "ConstraintError"}:
        return f"{action} failed: Neo4j rejected the operation"
    return f"{action} failed ({error_name})"


def _neo4j_error_code(error: Exception) -> str:
    error_name = type(error).__name__
    if error_name in {"AuthError", "AuthenticationError", "Unauthorized"}:
        return "neo4j_authentication_failed"
    if error_name in {"ServiceUnavailable", "SessionExpired", "ConnectionError"}:
        return "neo4j_unavailable"
    if error_name in {"ConstraintError"}:
        return "publication_conflict"
    return "neo4j_operation_failed"
