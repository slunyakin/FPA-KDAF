"""Versioned execution bindings for published competency-question scope."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import uuid4

from kdaf.metadata import (
    DataOperationRecord,
    MetadataError,
    MetadataRepository,
    QuestionBindingRecord,
)
from kdaf.retrieval import DwhQueryResult, RetrievalError, _assert_read_only

EXECUTION_EVIDENCE_SCHEMA_VERSION = 2
_PARAMETER = re.compile(r"(?<!:):([a-zA-Z_][a-zA-Z0-9_]*)")
_SUPPORTED_TYPES = frozenset({"string", "integer", "number", "boolean"})
_SCHEMA_KEYS = frozenset({"type", "properties", "required", "additionalProperties", "description"})
_PROPERTY_SCHEMA_KEYS = frozenset(
    {"type", "description", "enum", "maxLength", "minimum", "maximum"}
)


class QuestionExecutionError(ValueError):
    """Stable registration, activation, and execution error."""

    def __init__(self, message: str, code: str = "question_execution_error") -> None:
        super().__init__(message)
        self.code = code


class PublishedQuestionScopeProvider(Protocol):
    def question_scope(
        self,
        project_id: str,
        *,
        expected_database: str,
        question_id: str | None = None,
        graph_publication_id: str | None = None,
    ) -> dict[str, Any]: ...


class RegisteredDataQueryService(Protocol):
    def execute_registered(
        self,
        *,
        operation_id: str,
        operation_version: int,
        statement: str,
        parameters: dict[str, Any],
        max_rows: int,
    ) -> DwhQueryResult: ...


@dataclass(frozen=True)
class QuestionBindingService:
    metadata: MetadataRepository
    scope_provider: PublishedQuestionScopeProvider

    def register_data_operation(
        self,
        project_id: str,
        operation_id: str,
        *,
        statement: str,
        parameter_schema: dict[str, Any],
        result_schema: dict[str, Any],
        evidence_eligible: bool = True,
        max_rows: int = 100,
    ) -> dict[str, Any]:
        try:
            _assert_read_only(statement)
            normalized_parameters = _normalize_object_schema(
                parameter_schema,
                field="parameter_schema",
            )
            normalized_result = _normalize_object_schema(
                result_schema,
                field="result_schema",
            )
            placeholders = set(_PARAMETER.findall(statement))
            declared = set(normalized_parameters["properties"])
            if placeholders != declared:
                raise QuestionExecutionError(
                    "Statement parameters must exactly match parameter_schema properties",
                    "invalid_operation_schema",
                )
            operation = self.metadata.create_data_operation(
                project_id,
                operation_id,
                statement=statement,
                parameter_schema=normalized_parameters,
                result_schema=normalized_result,
                evidence_eligible=evidence_eligible,
                max_rows=max_rows,
            )
            return operation.to_dict()
        except QuestionExecutionError:
            raise
        except RetrievalError as exc:
            raise QuestionExecutionError(str(exc), exc.code) from exc
        except MetadataError as exc:
            raise QuestionExecutionError(str(exc), exc.code) from exc

    def list_data_operations(self, project_id: str) -> list[dict[str, Any]]:
        try:
            return [item.to_dict() for item in self.metadata.list_data_operations(project_id)]
        except MetadataError as exc:
            raise QuestionExecutionError(str(exc), exc.code) from exc

    def get_data_operation(
        self,
        project_id: str,
        operation_id: str,
        *,
        version: int | None = None,
    ) -> dict[str, Any]:
        try:
            return self.metadata.get_data_operation(
                project_id,
                operation_id,
                version=version,
            ).to_dict()
        except MetadataError as exc:
            raise QuestionExecutionError(str(exc), exc.code) from exc

    def register_binding(
        self,
        project_id: str,
        binding_id: str,
        question_id: str,
        *,
        evidence_mode: str,
        required_concept_ids: list[str],
        graph_publication_id: str,
        data_operation_id: str | None = None,
        data_operation_version: int | None = None,
    ) -> dict[str, Any]:
        try:
            operation = None
            if data_operation_id is not None:
                operation = self.metadata.get_data_operation(
                    project_id,
                    data_operation_id,
                    version=data_operation_version,
                )
            binding = self.metadata.create_question_binding(
                project_id,
                binding_id,
                question_id,
                evidence_mode=evidence_mode,
                required_concept_ids=required_concept_ids,
                graph_publication_id=graph_publication_id,
                data_operation=operation,
            )
            return binding.to_dict()
        except MetadataError as exc:
            raise QuestionExecutionError(str(exc), exc.code) from exc

    def activate_binding(
        self,
        record_id: str,
        *,
        expected_database: str,
    ) -> dict[str, Any]:
        try:
            binding = self.metadata.get_question_binding_record(record_id)
            self._validate_binding_dependencies(
                binding,
                expected_database=expected_database,
            )
            return self.metadata.activate_question_binding(binding.id).to_dict()
        except QuestionExecutionError:
            raise
        except MetadataError as exc:
            raise QuestionExecutionError(str(exc), exc.code) from exc

    def get_binding(
        self,
        project_id: str,
        binding_id: str,
        *,
        version: int | None = None,
    ) -> dict[str, Any]:
        try:
            return self.metadata.get_question_binding(
                project_id,
                binding_id,
                version=version,
            ).to_dict()
        except MetadataError as exc:
            raise QuestionExecutionError(str(exc), exc.code) from exc

    def list_bindings(self, project_id: str) -> list[dict[str, Any]]:
        try:
            return [item.to_dict() for item in self.metadata.list_question_bindings(project_id)]
        except MetadataError as exc:
            raise QuestionExecutionError(str(exc), exc.code) from exc

    def execute_binding(
        self,
        project_id: str,
        binding_id: str,
        run_id: str,
        *,
        expected_database: str,
        data_service: RegisteredDataQueryService | None,
        version: int | None = None,
        parameters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            binding = self.metadata.get_question_binding(
                project_id,
                binding_id,
                version=version,
                active_only=True,
            )
            run = self.metadata.get_run(run_id)
            question = self.metadata.get_competency_question(binding.question_id)
            if run.project_id != binding.project_id or question.project_id != binding.project_id:
                raise QuestionExecutionError(
                    "Run, binding, and question must share a project",
                    "invalid_scope",
                )
            scope = self._validate_binding_dependencies(
                binding,
                expected_database=expected_database,
            )
            supplied = {} if parameters is None else parameters
            validated_parameters = _validate_object(
                supplied,
                binding.parameter_schema,
                missing_code="missing_parameter",
                invalid_code="invalid_parameter",
            )
            dwh_result: DwhQueryResult | None = None
            operation: DataOperationRecord | None = None
            if binding.evidence_mode == "quantitative":
                if data_service is None:
                    raise QuestionExecutionError(
                        "Quantitative binding requires a configured DWH adapter",
                        "missing_data_binding",
                    )
                operation = self._data_operation(binding)
                try:
                    dwh_result = data_service.execute_registered(
                        operation_id=operation.operation_id,
                        operation_version=operation.version,
                        statement=operation.statement,
                        parameters=validated_parameters,
                        max_rows=operation.max_rows,
                    )
                except RetrievalError as exc:
                    raise QuestionExecutionError(str(exc), exc.code) from exc
                if not dwh_result.rows:
                    raise QuestionExecutionError(
                        "Registered data operation returned no evidence",
                        "missing_data",
                    )
                _validate_result_rows(dwh_result.rows, binding.result_schema)
                self.metadata.record_audit_event(
                    "data_operation.executed",
                    "question_binding",
                    binding.id,
                    {
                        "run_id": run.id,
                        "operation_id": operation.operation_id,
                        "operation_version": operation.version,
                        "statement_fingerprint": dwh_result.statement_fingerprint,
                        "parameters": validated_parameters,
                        "row_count": dwh_result.row_count,
                    },
                )
            packet = _build_execution_packet(
                binding=binding,
                question=question.to_dict(),
                run=run.to_dict(),
                scope=scope,
                dwh_result=dwh_result,
                operation=operation,
            )
            self.metadata.record_audit_event(
                "question_binding.executed",
                "question_binding",
                binding.id,
                {
                    "run_id": run.id,
                    "binding_id": binding.binding_id,
                    "binding_version": binding.version,
                    "question_id": binding.question_id,
                    "graph_publication_id": binding.graph_publication_id,
                    "evidence_mode": binding.evidence_mode,
                    "evidence_packet_id": packet["id"],
                },
            )
            return packet
        except QuestionExecutionError:
            raise
        except MetadataError as exc:
            raise QuestionExecutionError(str(exc), exc.code) from exc

    def _validate_binding_dependencies(
        self,
        binding: QuestionBindingRecord,
        *,
        expected_database: str,
    ) -> dict[str, Any]:
        try:
            result = self.scope_provider.question_scope(
                binding.project_id,
                expected_database=expected_database,
                question_id=binding.question_id,
                graph_publication_id=binding.graph_publication_id,
            )
        except Exception as exc:
            if hasattr(exc, "code"):
                raise QuestionExecutionError(str(exc), exc.code) from exc
            raise
        scopes = result.get("scopes") if isinstance(result, dict) else None
        if not isinstance(result, dict) or any(
            result.get(field) != expected
            for field, expected in (
                ("project_id", binding.project_id),
                ("question_id", binding.question_id),
                ("graph_publication_id", binding.graph_publication_id),
            )
        ):
            raise QuestionExecutionError(
                "Published question scope does not match the binding",
                "missing_context",
            )
        if not isinstance(scopes, list) or not scopes:
            raise QuestionExecutionError(
                "Published question scope is missing",
                "missing_context",
            )
        if len(scopes) != 1:
            raise QuestionExecutionError(
                "Published question scope is ambiguous",
                "ambiguous_context",
            )
        scope = scopes[0]
        if not isinstance(scope, dict):
            raise QuestionExecutionError("Published question scope is invalid", "missing_context")
        if (
            scope.get("question_id") != binding.question_id
            or scope.get("graph_publication_id") != binding.graph_publication_id
        ):
            raise QuestionExecutionError(
                "Published question scope does not match the binding",
                "missing_context",
            )
        available = {
            item.get("id")
            for item in scope.get("concepts", [])
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        }
        missing = set(binding.required_concept_ids) - available
        if missing:
            raise QuestionExecutionError(
                f"Published question scope is missing concept: {sorted(missing)[0]}",
                "missing_context",
            )
        if binding.evidence_mode == "quantitative":
            self._data_operation(binding)
        return scope

    def _data_operation(self, binding: QuestionBindingRecord) -> DataOperationRecord:
        if binding.data_operation_id is None or binding.data_operation_version is None:
            raise QuestionExecutionError(
                "Quantitative binding has no registered data operation",
                "missing_data_binding",
            )
        try:
            operation = self.metadata.get_data_operation(
                binding.project_id,
                binding.data_operation_id,
                version=binding.data_operation_version,
            )
        except MetadataError as exc:
            raise QuestionExecutionError(str(exc), "missing_data_binding") from exc
        if operation.status != "active" or not operation.evidence_eligible:
            raise QuestionExecutionError(
                "Registered data operation is not authorized for evidence",
                "unauthorized_data_operation",
            )
        if (
            operation.parameter_schema != binding.parameter_schema
            or operation.result_schema != binding.result_schema
        ):
            raise QuestionExecutionError(
                "Registered data operation no longer matches the binding contract",
                "stale_data_binding",
            )
        return operation


def _normalize_object_schema(value: Any, *, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise QuestionExecutionError(f"{field} must be an object", "invalid_operation_schema")
    unknown = set(value) - _SCHEMA_KEYS
    if unknown:
        raise QuestionExecutionError(
            f"{field} contains unsupported field: {sorted(unknown)[0]}",
            "invalid_operation_schema",
        )
    if value.get("type") != "object":
        raise QuestionExecutionError(
            f"{field}.type must be object",
            "invalid_operation_schema",
        )
    properties = value.get("properties", {})
    required = value.get("required", [])
    if not isinstance(properties, dict) or not isinstance(required, list):
        raise QuestionExecutionError(
            f"{field} properties and required must be structured",
            "invalid_operation_schema",
        )
    if value.get("additionalProperties") is not False:
        raise QuestionExecutionError(
            f"{field} must set additionalProperties to false",
            "invalid_operation_schema",
        )
    if any(not isinstance(item, str) or not item for item in required):
        raise QuestionExecutionError(
            f"{field}.required must contain field names",
            "invalid_operation_schema",
        )
    if len(required) != len(set(required)) or set(required) - set(properties):
        raise QuestionExecutionError(
            f"{field}.required is inconsistent with properties",
            "invalid_operation_schema",
        )
    normalized_properties: dict[str, dict[str, Any]] = {}
    for name, schema in properties.items():
        if not isinstance(name, str) or not name or not isinstance(schema, dict):
            raise QuestionExecutionError(
                f"{field} contains an invalid property",
                "invalid_operation_schema",
            )
        unknown_property_keys = set(schema) - _PROPERTY_SCHEMA_KEYS
        if unknown_property_keys or schema.get("type") not in _SUPPORTED_TYPES:
            raise QuestionExecutionError(
                f"{field} property schema is unsupported: {name}",
                "invalid_operation_schema",
            )
        if "enum" in schema and (not isinstance(schema["enum"], list) or not schema["enum"]):
            raise QuestionExecutionError(
                f"{field} enum is invalid: {name}",
                "invalid_operation_schema",
            )
        kind = schema["type"]
        if "enum" in schema and any(not _matches_type(kind, item) for item in schema["enum"]):
            raise QuestionExecutionError(
                f"{field} enum values do not match the property type: {name}",
                "invalid_operation_schema",
            )
        if "maxLength" in schema and (
            kind != "string"
            or not isinstance(schema["maxLength"], int)
            or isinstance(schema["maxLength"], bool)
            or schema["maxLength"] < 1
        ):
            raise QuestionExecutionError(
                f"{field} maxLength is invalid: {name}",
                "invalid_operation_schema",
            )
        for bound in ("minimum", "maximum"):
            if bound in schema and (
                kind not in {"integer", "number"} or not _matches_type("number", schema[bound])
            ):
                raise QuestionExecutionError(
                    f"{field} {bound} is invalid: {name}",
                    "invalid_operation_schema",
                )
        if "minimum" in schema and "maximum" in schema and schema["minimum"] > schema["maximum"]:
            raise QuestionExecutionError(
                f"{field} numeric bounds are inconsistent: {name}",
                "invalid_operation_schema",
            )
        normalized_properties[name] = dict(schema)
    return {
        "type": "object",
        "properties": normalized_properties,
        "required": list(required),
        "additionalProperties": False,
        **({"description": value["description"]} if "description" in value else {}),
    }


def _validate_object(
    value: Any,
    schema: dict[str, Any],
    *,
    missing_code: str,
    invalid_code: str,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise QuestionExecutionError("Parameters must be an object", invalid_code)
    properties = schema.get("properties", {})
    required = schema.get("required", [])
    missing = set(required) - set(value)
    if missing:
        raise QuestionExecutionError(
            f"Required parameter is missing: {sorted(missing)[0]}",
            missing_code,
        )
    unexpected = set(value) - set(properties)
    if unexpected:
        raise QuestionExecutionError(
            f"Unexpected parameter: {sorted(unexpected)[0]}",
            invalid_code,
        )
    for name, item in value.items():
        _validate_scalar(name, item, properties[name], invalid_code)
    return dict(value)


def _validate_result_rows(rows: list[dict[str, Any]], schema: dict[str, Any]) -> None:
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise QuestionExecutionError(
                f"Result row is not an object: {index}",
                "invalid_result_schema",
            )
        try:
            _validate_object(
                row,
                schema,
                missing_code="invalid_result_schema",
                invalid_code="invalid_result_schema",
            )
        except QuestionExecutionError as exc:
            raise QuestionExecutionError(
                f"Result row does not match the registered schema: {index}",
                "invalid_result_schema",
            ) from exc


def _validate_scalar(name: str, value: Any, schema: dict[str, Any], code: str) -> None:
    kind = schema["type"]
    if not _matches_type(kind, value):
        raise QuestionExecutionError(f"Invalid value type: {name}", code)
    if "enum" in schema and value not in schema["enum"]:
        raise QuestionExecutionError(f"Value is outside the allowed enum: {name}", code)
    if isinstance(value, str) and "maxLength" in schema and len(value) > schema["maxLength"]:
        raise QuestionExecutionError(f"String parameter is too long: {name}", code)
    if isinstance(value, int | float) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            raise QuestionExecutionError(f"Value is below minimum: {name}", code)
        if "maximum" in schema and value > schema["maximum"]:
            raise QuestionExecutionError(f"Value is above maximum: {name}", code)


def _matches_type(kind: str, value: Any) -> bool:
    return (
        (kind == "string" and isinstance(value, str))
        or (kind == "integer" and isinstance(value, int) and not isinstance(value, bool))
        or (kind == "number" and isinstance(value, int | float) and not isinstance(value, bool))
        or (kind == "boolean" and isinstance(value, bool))
    )


def _build_execution_packet(
    *,
    binding: QuestionBindingRecord,
    question: dict[str, Any],
    run: dict[str, Any],
    scope: dict[str, Any],
    dwh_result: DwhQueryResult | None,
    operation: DataOperationRecord | None,
) -> dict[str, Any]:
    concepts = scope.get("concepts", [])
    relationships = scope.get("relationships", [])
    entries = [
        {
            "id": f"graph-node:{item['id']}",
            "kind": "semantic_context",
            "node_id": item["id"],
            "data": item,
        }
        for item in concepts
    ]
    entries.extend(
        {
            "id": f"graph-relationship:{item['id']}",
            "kind": "semantic_relationship",
            "relationship_id": item["id"],
            "data": item,
        }
        for item in relationships
    )
    if dwh_result is not None:
        entries.extend(
            {
                "id": f"{dwh_result.id}:row:{index}",
                "kind": "financial_fact",
                "query_id": dwh_result.id,
                "data": row,
            }
            for index, row in enumerate(dwh_result.rows, start=1)
        )
    dwh_queries = [] if dwh_result is None else [dwh_result.to_dict()]
    operation_provenance = None
    if dwh_result is not None and operation is not None:
        operation_provenance = {
            "operation_id": operation.operation_id,
            "operation_version": operation.version,
            "statement_fingerprint": dwh_result.statement_fingerprint,
            "parameters": dwh_result.parameters,
        }
    return {
        "schema_version": EXECUTION_EVIDENCE_SCHEMA_VERSION,
        "id": f"evidence-packet:{uuid4()}",
        "project_id": binding.project_id,
        "run_id": run["id"],
        "competency_question_id": binding.question_id,
        "question": question["question_text"],
        "binding": {
            "record_id": binding.id,
            "binding_id": binding.binding_id,
            "version": binding.version,
            "evidence_mode": binding.evidence_mode,
        },
        "dwh_queries": dwh_queries,
        "graph_nodes": concepts,
        "graph_relationships": relationships,
        "source_records": [],
        "validation_decisions": [],
        "entries": entries,
        "provenance": {
            "binding_id": binding.binding_id,
            "binding_version": binding.version,
            "graph_publication_id": binding.graph_publication_id,
            "question_scope_id": scope.get("id"),
            "data_operation": operation_provenance,
            "dwh_query_ids": [] if dwh_result is None else [dwh_result.id],
            "source_link_ids": [],
            "validation_ids": [],
        },
        "built_at": _timestamp(),
    }


def _timestamp() -> str:
    return datetime.now(UTC).isoformat()
