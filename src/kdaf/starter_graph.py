"""Versioned finance foundation and Neo4j starter-graph compatibility APIs."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass
from importlib import resources
from typing import Any

STARTER_GRAPH_SCHEMA_VERSION = 1
FOUNDATION_MANIFEST_SCHEMA_VERSION = 1
CORE_COMPONENT = "kdaf.finance.foundation.core"
STARTER_PROFILE_COMPONENT = "kdaf.finance.foundation.starter_profile"
STARTER_BINDINGS_COMPONENT = "kdaf.finance.foundation.starter_dwh_bindings"
_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class StarterGraphLoadSummary:
    schema_version: int
    database: str
    concept_counts: dict[str, int]
    relationship_counts: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FoundationInitializationSummary:
    foundation_id: str
    foundation_version: str
    database: str
    status: str
    installed_components: list[str]
    concept_counts: dict[str, int]
    relationship_counts: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class StarterGraphError(ValueError):
    """Raised when finance foundation or starter graph operations fail safely."""

    def __init__(self, message: str, code: str = "starter_graph_error") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Neo4jConnectionSettings:
    uri: str
    user: str
    password: str
    database: str


class StarterGraphRepository:
    """Neo4j repository for the versioned foundation and legacy starter surface."""

    def __init__(
        self,
        settings: Neo4jConnectionSettings,
        driver_factory: Callable[..., Any] | None = None,
    ) -> None:
        self.settings = settings
        self._driver_factory = driver_factory

    def initialize_foundation(
        self,
        *,
        expected_database: str,
        include_starter_profile: bool = False,
        include_starter_bindings: bool = False,
    ) -> FoundationInitializationSummary:
        """Install selected manifest components without replacing existing meaning."""

        self._validate_target(expected_database)
        manifest = finance_foundation_manifest()
        selection = _manifest_selection(
            manifest,
            include_starter_profile=include_starter_profile,
            include_starter_bindings=include_starter_bindings,
        )
        try:
            with self._driver() as driver:
                _verify_connectivity(driver)
                with driver.session(database=self.settings.database) as session:
                    _ensure_constraints(session)
                    plan = session.execute_write(
                        _initialize_foundation_transaction,
                        manifest,
                        selection,
                    )
                    counts = _summary_from_rows(
                        database=self.settings.database,
                        concept_rows=session.run(_concept_count_query()),
                        relationship_rows=session.run(_relationship_count_query()),
                    )
            return FoundationInitializationSummary(
                foundation_id=manifest["foundation_id"],
                foundation_version=manifest["version"],
                database=self.settings.database,
                status=plan["action"],
                installed_components=selection["component_ids"],
                concept_counts=counts.concept_counts,
                relationship_counts=counts.relationship_counts,
            )
        except StarterGraphError:
            raise
        except Exception as exc:
            raise StarterGraphError(
                _safe_neo4j_failure("Finance foundation initialization", exc),
                code=_neo4j_error_code(exc),
            ) from exc

    def plan_foundation(
        self,
        *,
        expected_database: str,
        include_starter_profile: bool = False,
        include_starter_bindings: bool = False,
    ) -> dict[str, Any]:
        """Return a read-only installation or upgrade plan for the packaged manifest."""

        self._validate_target(expected_database)
        manifest = finance_foundation_manifest()
        selection = _manifest_selection(
            manifest,
            include_starter_profile=include_starter_profile,
            include_starter_bindings=include_starter_bindings,
        )
        try:
            with self._driver() as driver:
                _verify_connectivity(driver)
                with driver.session(database=self.settings.database) as session:
                    plan = session.execute_read(
                        _plan_foundation_transaction,
                        manifest,
                        selection,
                    )
            return {**plan, "database": self.settings.database}
        except StarterGraphError:
            raise
        except Exception as exc:
            raise StarterGraphError(
                _safe_neo4j_failure("Finance foundation planning", exc),
                code=_neo4j_error_code(exc),
            ) from exc

    def inspect_foundation(self, *, expected_database: str) -> dict[str, Any]:
        """Inspect installed versions and owned graph elements without exposing credentials."""

        self._validate_target(expected_database)
        try:
            with self._driver() as driver:
                _verify_connectivity(driver)
                with driver.session(database=self.settings.database) as session:
                    installations = _records_to_list(session.run(_installation_query()))
                    core = next(
                        (row for row in installations if row["component_id"] == CORE_COMPONENT),
                        None,
                    )
                    return {
                        "status": "installed" if core is not None else "not_installed",
                        "database": self.settings.database,
                        "foundation_id": core["foundation_id"] if core is not None else None,
                        "foundation_version": core["version"] if core is not None else None,
                        "installed_components": installations,
                        "owned_concept_count": _single_count(
                            session.run(_owned_concept_count_query())
                        ),
                        "concept_counts": _records_to_dict(session.run(_concept_count_query())),
                        "relationship_counts": _records_to_dict(
                            session.run(_relationship_count_query())
                        ),
                    }
        except StarterGraphError:
            raise
        except Exception as exc:
            raise StarterGraphError(
                _safe_neo4j_failure("Finance foundation inspection", exc),
                code=_neo4j_error_code(exc),
            ) from exc

    def load_seed_data(self) -> StarterGraphLoadSummary:
        """Load the compatibility starter profile through the safe initializer."""

        result = self.initialize_foundation(
            expected_database=self.settings.database,
            include_starter_profile=True,
            include_starter_bindings=True,
        )
        return StarterGraphLoadSummary(
            schema_version=STARTER_GRAPH_SCHEMA_VERSION,
            database=result.database,
            concept_counts=result.concept_counts,
            relationship_counts=result.relationship_counts,
        )

    def inspect_context(self) -> dict[str, Any]:
        """Inspect the compatibility starter profile and its DWH references."""

        try:
            with self._driver() as driver:
                _verify_connectivity(driver)
                with driver.session(database=self.settings.database) as session:
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
            raise StarterGraphError(
                _safe_neo4j_failure("Neo4j starter graph inspection", exc),
                code=_neo4j_error_code(exc),
            ) from exc

    def _validate_target(self, expected_database: str) -> None:
        if not isinstance(expected_database, str) or not expected_database.strip():
            raise StarterGraphError(
                "The expected Neo4j database must be supplied explicitly",
                code="missing_database_target",
            )
        if expected_database.strip() != self.settings.database:
            raise StarterGraphError(
                "The expected Neo4j database does not match the configured target",
                code="database_target_mismatch",
            )

    def _driver(self) -> Any:
        driver_factory = self._driver_factory
        if driver_factory is None:
            try:
                from neo4j import GraphDatabase
            except ImportError as exc:
                raise StarterGraphError(
                    "Neo4j driver is not installed. Install 'kdaf[neo4j]' and retry.",
                    code="neo4j_driver_missing",
                ) from exc
            driver_factory = GraphDatabase.driver
        try:
            return driver_factory(
                self.settings.uri,
                auth=(self.settings.user, self.settings.password),
            )
        except Exception as exc:
            raise StarterGraphError(
                _safe_neo4j_failure("Neo4j driver creation", exc),
                code=_neo4j_error_code(exc),
            ) from exc


def finance_foundation_manifest() -> dict[str, Any]:
    """Return and validate a copy of the packaged finance foundation manifest."""

    root = resources.files("kdaf").joinpath("resources/starter_graph")
    payload = json.loads(root.joinpath("foundation_manifest.json").read_text(encoding="utf-8"))
    _validate_manifest(payload)
    return payload


def starter_graph_cypher_artifacts() -> dict[str, str]:
    """Return compatibility Cypher artifacts for the starter semantic graph."""

    root = resources.files("kdaf").joinpath("resources/starter_graph")
    return {
        "seed": root.joinpath("seed.cypher").read_text(encoding="utf-8"),
        "sample_queries": root.joinpath("sample_queries.cypher").read_text(encoding="utf-8"),
    }


def starter_graph_model() -> dict[str, list[dict[str, Any]]]:
    """Return the compatibility starter model derived from the manifest."""

    manifest = finance_foundation_manifest()
    bindings = {row["concept_id"]: row for row in manifest["starter_dwh_bindings"]}
    dependencies: dict[str, list[str]] = {}
    for relationship in manifest["relationships"]:
        if relationship["type"] == "DEPENDS_ON":
            dependencies.setdefault(relationship["source_id"], []).append(
                relationship["target_id"]
            )
    groups: dict[str, list[dict[str, Any]]] = {
        "domains": [],
        "accounts": [],
        "departments": [],
        "scenarios": [],
        "metrics": [],
    }
    label_groups = {
        "FinanceDomain": "domains",
        "AccountConcept": "accounts",
        "DepartmentConcept": "departments",
        "ScenarioConcept": "scenarios",
        "MetricConcept": "metrics",
    }
    for concept in manifest["concepts"]:
        group = label_groups[concept["labels"][0]]
        item = {
            "id": concept["id"],
            "name": concept["name"],
            "description": concept["description"],
            "validation_state": "seeded",
        }
        binding = bindings.get(concept["id"])
        if binding is not None:
            item.update(
                dwh_table=binding["table"],
                dwh_key=binding["key"],
                dwh_value=binding["value"],
            )
        if group == "metrics":
            item["depends_on"] = dependencies.get(concept["id"], [])
        groups[group].append(item)
    account_order = {
        concept_id: index
        for index, concept_id in enumerate(
            [
                "account:revenue",
                "account:cogs",
                "account:payroll",
                "account:cloud_hosting",
                "account:marketing_spend",
                "account:headcount",
            ]
        )
    }
    groups["accounts"].sort(key=lambda row: account_order[row["id"]])
    return groups


def _manifest_selection(
    manifest: dict[str, Any],
    *,
    include_starter_profile: bool,
    include_starter_bindings: bool,
) -> dict[str, Any]:
    if include_starter_bindings and not include_starter_profile:
        raise StarterGraphError(
            "Starter DWH bindings require the starter profile",
            code="invalid_component_selection",
        )
    component_ids = [CORE_COMPONENT]
    if include_starter_profile:
        component_ids.append(STARTER_PROFILE_COMPONENT)
    if include_starter_bindings:
        component_ids.append(STARTER_BINDINGS_COMPONENT)
    concepts = [
        concept for concept in manifest["concepts"] if concept["component_id"] in component_ids
    ]
    concept_ids = {concept["id"] for concept in concepts}
    concept_components = {concept["id"]: concept["component_id"] for concept in concepts}
    relationships = [
        {
            **relationship,
            "component_id": (
                STARTER_PROFILE_COMPONENT
                if STARTER_PROFILE_COMPONENT
                in {
                    concept_components[relationship["source_id"]],
                    concept_components[relationship["target_id"]],
                }
                else CORE_COMPONENT
            ),
        }
        for relationship in manifest["relationships"]
        if relationship["source_id"] in concept_ids and relationship["target_id"] in concept_ids
    ]
    bindings = manifest["starter_dwh_bindings"] if include_starter_bindings else []
    return {
        "component_ids": component_ids,
        "concepts": concepts,
        "relationships": relationships,
        "bindings": bindings,
    }


def _plan_foundation_transaction(
    transaction: Any,
    manifest: dict[str, Any],
    selection: dict[str, Any],
) -> dict[str, Any]:
    return _build_foundation_plan(
        manifest,
        selection,
        _read_foundation_state(transaction, selection),
    )


def _initialize_foundation_transaction(
    transaction: Any,
    manifest: dict[str, Any],
    selection: dict[str, Any],
) -> dict[str, Any]:
    plan = _build_foundation_plan(
        manifest,
        selection,
        _read_foundation_state(transaction, selection),
    )
    if plan["conflicts"]:
        conflict_ids = ", ".join(item["id"] for item in plan["conflicts"][:5])
        raise StarterGraphError(
            f"Foundation initialization requires review because of conflicts: {conflict_ids}",
            code="foundation_conflict",
        )
    if plan["action"] == "noop":
        return plan

    owner = manifest["owner"]
    version = manifest["version"]
    adoptable_concepts = set(plan["adoptable_concepts"])
    for concept in selection["concepts"]:
        label_fragment = ":".join(
            _safe_cypher_identifier(label)
            for label in ["SemanticConcept", *concept["labels"]]
        )
        transaction.run(
            f"""
            MERGE (concept:{label_fragment} {{id: $id}})
            ON CREATE SET
                concept.name = $name,
                concept.description = $description,
                concept.validation_state = 'seeded',
                concept.kdaf_owner = $owner,
                concept.kdaf_component_id = $component_id,
                concept.kdaf_foundation_version = $version,
                concept.kdaf_provenance = $provenance
            ON MATCH SET
                concept.name = CASE
                    WHEN $legacy_adoption THEN $name ELSE concept.name
                END,
                concept.description = CASE
                    WHEN $legacy_adoption THEN $description ELSE concept.description
                END,
                concept.kdaf_owner = coalesce(concept.kdaf_owner, $owner),
                concept.kdaf_component_id = coalesce(concept.kdaf_component_id, $component_id),
                concept.kdaf_foundation_version = coalesce(
                    concept.kdaf_foundation_version, $version
                ),
                concept.kdaf_provenance = coalesce(concept.kdaf_provenance, $provenance)
            """,
            id=concept["id"],
            name=concept["name"],
            description=concept["description"],
            owner=owner,
            component_id=concept["component_id"],
            version=version,
            provenance=manifest["provenance"]["source"],
            legacy_adoption=concept["id"] in adoptable_concepts,
        ).consume()

    for binding in selection["bindings"]:
        transaction.run(
            """
            MERGE (reference:DwhDimension {id: $id})
            ON CREATE SET
                reference.table = $table,
                reference.key = $key,
                reference.value = $value,
                reference.kdaf_owner = $owner,
                reference.kdaf_component_id = $component_id,
                reference.kdaf_foundation_version = $version
            ON MATCH SET
                reference.kdaf_owner = coalesce(reference.kdaf_owner, $owner),
                reference.kdaf_component_id = coalesce(
                    reference.kdaf_component_id, $component_id
                ),
                reference.kdaf_foundation_version = coalesce(
                    reference.kdaf_foundation_version, $version
                )
            """,
            id=_binding_reference_id(binding),
            table=binding["table"],
            key=binding["key"],
            value=binding["value"],
            owner=owner,
            component_id=STARTER_BINDINGS_COMPONENT,
            version=version,
        ).consume()

    relationships = list(selection["relationships"])
    relationships.extend(_binding_relationship(binding) for binding in selection["bindings"])
    for relationship in relationships:
        _merge_relationship(transaction, relationship, owner=owner, version=version)

    component_digests = _component_digests(manifest, selection)
    for component_id in selection["component_ids"]:
        transaction.run(
            """
            MERGE (installation:KdafFoundationInstallation {id: $component_id})
            ON CREATE SET
                installation.foundation_id = $foundation_id,
                installation.component_id = $component_id,
                installation.version = $version,
                installation.manifest_digest = $manifest_digest,
                installation.owner = $owner,
                installation.installed_at = datetime().toString()
            """,
            component_id=component_id,
            foundation_id=manifest["foundation_id"],
            version=version,
            manifest_digest=component_digests[component_id],
            owner=owner,
        ).consume()
    return plan


def _read_foundation_state(transaction: Any, selection: dict[str, Any]) -> dict[str, Any]:
    concept_ids = [concept["id"] for concept in selection["concepts"]]
    reference_ids = [_binding_reference_id(binding) for binding in selection["bindings"]]
    node_ids = [*concept_ids, *reference_ids]
    concepts = {
        row["id"]: {"properties": dict(row["properties"]), "labels": list(row["labels"])}
        for row in transaction.run(
            """
            MATCH (node:SemanticConcept)
            WHERE node.id IN $ids
            RETURN node.id AS id, properties(node) AS properties, labels(node) AS labels
            """,
            ids=concept_ids,
        )
    }
    references = {
        row["id"]: dict(row["properties"])
        for row in transaction.run(
            """
            MATCH (node:DwhDimension)
            WHERE node.id IN $ids
            RETURN node.id AS id, properties(node) AS properties
            """,
            ids=reference_ids,
        )
    }
    relationships = {
        (row["source_id"], row["relationship_type"], row["target_id"]): dict(
            row["properties"]
        )
        for row in transaction.run(
            """
            MATCH (source)-[relationship]->(target)
            WHERE source.id IN $ids AND target.id IN $ids
            RETURN
                source.id AS source_id,
                type(relationship) AS relationship_type,
                target.id AS target_id,
                properties(relationship) AS properties
            """,
            ids=node_ids,
        )
    }
    installations = {
        row["component_id"]: dict(row["properties"])
        for row in transaction.run(
            """
            MATCH (installation:KdafFoundationInstallation)
            WHERE installation.id IN $component_ids
            RETURN installation.id AS component_id, properties(installation) AS properties
            """,
            component_ids=selection["component_ids"],
        )
    }
    return {
        "concepts": concepts,
        "references": references,
        "relationships": relationships,
        "installations": installations,
    }


def _build_foundation_plan(
    manifest: dict[str, Any],
    selection: dict[str, Any],
    state: dict[str, Any],
) -> dict[str, Any]:
    conflicts: list[dict[str, str]] = []
    missing_concepts: list[str] = []
    adoptable_concepts: list[str] = []
    missing_relationships: list[str] = []
    component_digests = _component_digests(manifest, selection)

    for component_id in selection["component_ids"]:
        installed = state["installations"].get(component_id)
        if installed is None:
            continue
        if installed.get("owner") != manifest["owner"]:
            conflicts.append({"id": component_id, "reason": "installation_owner_mismatch"})
        elif installed.get("version") != manifest["version"]:
            conflicts.append({"id": component_id, "reason": "version_requires_upgrade"})
        elif installed.get("manifest_digest") != component_digests[component_id]:
            conflicts.append({"id": component_id, "reason": "manifest_digest_mismatch"})

    for concept in selection["concepts"]:
        existing = state["concepts"].get(concept["id"])
        if existing is None:
            missing_concepts.append(concept["id"])
            continue
        properties = existing["properties"]
        owner = properties.get("kdaf_owner")
        component = properties.get("kdaf_component_id")
        if owner not in (None, manifest["owner"]):
            conflicts.append({"id": concept["id"], "reason": "concept_owner_mismatch"})
            continue
        if owner == manifest["owner"] and component != concept["component_id"]:
            conflicts.append({"id": concept["id"], "reason": "concept_component_mismatch"})
            continue
        if owner is None and component is not None:
            conflicts.append({"id": concept["id"], "reason": "concept_owner_missing"})
            continue
        if owner == manifest["owner"] and properties.get(
            "kdaf_foundation_version"
        ) != manifest["version"]:
            conflicts.append({"id": concept["id"], "reason": "concept_version_mismatch"})
            continue
        legacy_candidate = owner is None and properties.get("validation_state") in (
            None,
            "seeded",
        )
        if owner is None and not legacy_candidate:
            conflicts.append({"id": concept["id"], "reason": "unmanaged_reviewed_concept"})
            continue
        accepted_names = {concept["name"]}
        accepted_descriptions = {concept["description"]}
        if legacy_candidate:
            accepted_names.update(concept.get("legacy_names", []))
            accepted_descriptions.update((None, ""))
            accepted_descriptions.update(concept.get("legacy_descriptions", []))
        if properties.get("name") not in accepted_names:
            conflicts.append({"id": concept["id"], "reason": "concept_name_conflict"})
            continue
        description = properties.get("description")
        if description not in accepted_descriptions:
            conflicts.append({"id": concept["id"], "reason": "concept_description_conflict"})
            continue
        expected_labels = {"SemanticConcept", *concept["labels"]}
        if not expected_labels.issubset(set(existing["labels"])):
            conflicts.append({"id": concept["id"], "reason": "concept_type_conflict"})
            continue
        if owner is None:
            adoptable_concepts.append(concept["id"])

    for binding in selection["bindings"]:
        reference_id = _binding_reference_id(binding)
        existing = state["references"].get(reference_id)
        if existing is None:
            continue
        if existing.get("kdaf_owner") not in (None, manifest["owner"]):
            conflicts.append({"id": reference_id, "reason": "binding_owner_mismatch"})
            continue
        for key in ("table", "key", "value"):
            if existing.get(key) != binding[key]:
                conflicts.append({"id": reference_id, "reason": f"binding_{key}_conflict"})
                break

    desired_relationships = list(selection["relationships"])
    desired_relationships.extend(
        _binding_relationship(binding) for binding in selection["bindings"]
    )
    for relationship in desired_relationships:
        key = (
            relationship["source_id"],
            relationship["type"],
            relationship["target_id"],
        )
        existing = state["relationships"].get(key)
        if existing is None:
            missing_relationships.append(relationship["id"])
        elif existing.get("kdaf_owner") not in (None, manifest["owner"]):
            conflicts.append({"id": relationship["id"], "reason": "relationship_owner_mismatch"})

    installed_ids = set(state["installations"])
    requested_ids = set(selection["component_ids"])
    if conflicts:
        action = "review_required"
    elif (
        not missing_concepts
        and not adoptable_concepts
        and not missing_relationships
        and requested_ids.issubset(installed_ids)
    ):
        action = "noop"
    elif adoptable_concepts:
        action = "migrate_legacy"
    else:
        action = "initialize"
    return {
        "foundation_id": manifest["foundation_id"],
        "installed_version": _installed_core_version(state["installations"]),
        "target_version": manifest["version"],
        "requested_components": selection["component_ids"],
        "action": action,
        "missing_concepts": missing_concepts,
        "adoptable_concepts": adoptable_concepts,
        "missing_relationships": missing_relationships,
        "conflicts": conflicts,
        "preserves_unmanaged_graph": True,
    }


def _merge_relationship(
    transaction: Any,
    relationship: dict[str, str],
    *,
    owner: str,
    version: str,
) -> None:
    relationship_type = _safe_cypher_identifier(relationship["type"])
    target_label = (
        "DwhDimension" if relationship_type == "REFERENCES_DWH_DIMENSION" else "SemanticConcept"
    )
    component_id = (
        STARTER_BINDINGS_COMPONENT
        if relationship_type == "REFERENCES_DWH_DIMENSION"
        else relationship.get("component_id", CORE_COMPONENT)
    )
    transaction.run(
        f"""
        MATCH (source:SemanticConcept {{id: $source_id}})
        MATCH (target:{target_label} {{id: $target_id}})
        MERGE (source)-[relationship:{relationship_type}]->(target)
        ON CREATE SET
            relationship.kdaf_id = $relationship_id,
            relationship.kdaf_owner = $owner,
            relationship.kdaf_component_id = $component_id,
            relationship.kdaf_foundation_version = $version
        ON MATCH SET
            relationship.kdaf_id = coalesce(relationship.kdaf_id, $relationship_id),
            relationship.kdaf_owner = coalesce(relationship.kdaf_owner, $owner),
            relationship.kdaf_component_id = coalesce(
                relationship.kdaf_component_id, $component_id
            ),
            relationship.kdaf_foundation_version = coalesce(
                relationship.kdaf_foundation_version, $version
            )
        """,
        source_id=relationship["source_id"],
        target_id=relationship["target_id"],
        relationship_id=relationship["id"],
        owner=owner,
        component_id=component_id,
        version=version,
    ).consume()


def _binding_relationship(binding: dict[str, str]) -> dict[str, str]:
    reference_id = _binding_reference_id(binding)
    return {
        "id": f"binding:{binding['concept_id']}:{reference_id}",
        "type": "REFERENCES_DWH_DIMENSION",
        "source_id": binding["concept_id"],
        "target_id": reference_id,
        "component_id": STARTER_BINDINGS_COMPONENT,
    }


def _binding_reference_id(binding: dict[str, str]) -> str:
    return f"dwh:{binding['table']}:{binding['value']}"


def _component_digests(
    manifest: dict[str, Any], selection: dict[str, Any]
) -> dict[str, str]:
    digests: dict[str, str] = {}
    for component_id in selection["component_ids"]:
        if component_id == STARTER_BINDINGS_COMPONENT:
            content: Any = selection["bindings"]
        else:
            concepts = [
                concept
                for concept in selection["concepts"]
                if concept["component_id"] == component_id
            ]
            relationships = [
                relationship
                for relationship in selection["relationships"]
                if relationship["component_id"] == component_id
            ]
            content = {"concepts": concepts, "relationships": relationships}
        encoded = json.dumps(content, sort_keys=True, separators=(",", ":")).encode()
        digests[component_id] = hashlib.sha256(encoded).hexdigest()
    return digests


def _validate_manifest(payload: Any) -> None:
    if not isinstance(payload, dict):
        raise StarterGraphError("Finance foundation manifest must be an object")
    if payload.get("schema_version") != FOUNDATION_MANIFEST_SCHEMA_VERSION:
        raise StarterGraphError("Unsupported finance foundation manifest schema")
    for field in ("foundation_id", "version", "owner", "concepts", "relationships"):
        if field not in payload:
            raise StarterGraphError(f"Finance foundation manifest is missing {field}")
    component_ids = {component["id"] for component in payload.get("components", [])}
    if component_ids != {CORE_COMPONENT, STARTER_PROFILE_COMPONENT, STARTER_BINDINGS_COMPONENT}:
        raise StarterGraphError("Finance foundation manifest components are invalid")
    concept_ids: set[str] = set()
    for concept in payload["concepts"]:
        concept_id = concept.get("id")
        if not isinstance(concept_id, str) or not concept_id or concept_id in concept_ids:
            raise StarterGraphError("Finance foundation concept IDs must be unique")
        concept_ids.add(concept_id)
        if concept.get("component_id") not in {CORE_COMPONENT, STARTER_PROFILE_COMPONENT}:
            raise StarterGraphError(f"Invalid component for concept {concept_id}")
        if not concept.get("labels") or any(
            not _SAFE_IDENTIFIER.fullmatch(label) for label in concept["labels"]
        ):
            raise StarterGraphError(f"Invalid labels for concept {concept_id}")
        if not concept.get("name") or not concept.get("description"):
            raise StarterGraphError(f"Concept {concept_id} requires name and description")
    relationship_ids: set[str] = set()
    for relationship in payload["relationships"]:
        relationship_id = relationship.get("id")
        if not relationship_id or relationship_id in relationship_ids:
            raise StarterGraphError("Finance foundation relationship IDs must be unique")
        relationship_ids.add(relationship_id)
        if relationship.get("source_id") not in concept_ids or relationship.get(
            "target_id"
        ) not in concept_ids:
            raise StarterGraphError(f"Relationship {relationship_id} has an unknown endpoint")
        _safe_cypher_identifier(relationship.get("type", ""))
    for binding in payload.get("starter_dwh_bindings", []):
        if binding.get("concept_id") not in concept_ids:
            raise StarterGraphError("Starter binding references an unknown concept")
        for field in ("table", "key", "value"):
            if not isinstance(binding.get(field), str) or not binding[field]:
                raise StarterGraphError(f"Starter binding requires {field}")


def _safe_cypher_identifier(value: str) -> str:
    if not isinstance(value, str) or not _SAFE_IDENTIFIER.fullmatch(value):
        raise StarterGraphError("Manifest contains an invalid Cypher identifier")
    return value


def _ensure_constraints(session: Any) -> None:
    statements = (
        "CREATE CONSTRAINT semantic_concept_id IF NOT EXISTS FOR "
        "(concept:SemanticConcept) REQUIRE concept.id IS UNIQUE",
        "CREATE CONSTRAINT kdaf_dwh_dimension_id IF NOT EXISTS FOR "
        "(dimension:DwhDimension) REQUIRE dimension.id IS UNIQUE",
        "CREATE CONSTRAINT kdaf_foundation_installation_id IF NOT EXISTS FOR "
        "(installation:KdafFoundationInstallation) REQUIRE installation.id IS UNIQUE",
    )
    for statement in statements:
        session.run(statement).consume()


def _verify_connectivity(driver: Any) -> None:
    verifier = getattr(driver, "verify_connectivity", None)
    if verifier is not None:
        verifier()


def _installed_core_version(installations: dict[str, dict[str, Any]]) -> str | None:
    core = installations.get(CORE_COMPONENT)
    return None if core is None else core.get("version")


def _installation_query() -> str:
    return """
    MATCH (installation:KdafFoundationInstallation)
    RETURN
        installation.id AS component_id,
        installation.foundation_id AS foundation_id,
        installation.version AS version,
        installation.owner AS owner,
        installation.manifest_digest AS manifest_digest,
        installation.installed_at AS installed_at
    ORDER BY component_id
    """


def _owned_concept_count_query() -> str:
    return "MATCH (concept:SemanticConcept {kdaf_owner: 'kdaf'}) RETURN count(concept) AS count"


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
        raise StarterGraphError(
            "Starter graph has not been loaded",
            code="starter_graph_not_loaded",
        )


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


def _single_count(records: Any) -> int:
    row = records.single()
    return 0 if row is None else int(row["count"])


def _records_to_dict(records: Any) -> dict[str, int]:
    return {record[0]: record[1] for record in records}


def _records_to_list(records: Any) -> list[dict[str, Any]]:
    return [dict(record) for record in records]


def _safe_neo4j_failure(action: str, error: Exception) -> str:
    error_name = type(error).__name__
    if error_name in {"AuthError", "AuthenticationError", "Unauthorized"}:
        return f"{action} failed: Neo4j authentication failed"
    if error_name in {"ServiceUnavailable", "SessionExpired", "ConnectionError"}:
        return f"{action} failed: Neo4j is unavailable"
    if error_name in {"ClientError", "DatabaseError"}:
        return f"{action} failed: Neo4j rejected the operation"
    return f"{action} failed ({error_name})"


def _neo4j_error_code(error: Exception) -> str:
    error_name = type(error).__name__
    if error_name in {"AuthError", "AuthenticationError", "Unauthorized"}:
        return "neo4j_authentication_failed"
    if error_name in {"ServiceUnavailable", "SessionExpired", "ConnectionError"}:
        return "neo4j_unavailable"
    return "neo4j_operation_failed"
