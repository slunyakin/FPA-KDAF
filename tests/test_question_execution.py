from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from io import StringIO
from typing import Any

import pytest

from kdaf.cli import main as cli_main
from kdaf.core import KdafCore
from kdaf.metadata import MetadataRepository
from kdaf.question_execution import QuestionBindingService, QuestionExecutionError
from kdaf.retrieval import DwhQueryResult, ReadOnlyDwhQueryService
from kdaf.tool_server import call_tool, handle_message, list_tools

PARAMETER_SCHEMA = {
    "type": "object",
    "properties": {"account_id": {"type": "string", "maxLength": 40}},
    "required": ["account_id"],
    "additionalProperties": False,
}
RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "period_id": {"type": "string"},
        "actual_revenue": {"type": "number"},
    },
    "required": ["period_id", "actual_revenue"],
    "additionalProperties": False,
}


class PublishedScope:
    def __init__(self, question_id: str, *, concepts: list[str] | None = None) -> None:
        self.question_id = question_id
        self.concepts = concepts or ["account:revenue", "driver:renewal_rate"]
        self.calls: list[dict[str, Any]] = []

    def question_scope(self, project_id: str, **kwargs: Any) -> dict[str, Any]:
        self.calls.append({"project_id": project_id, **kwargs})
        if kwargs.get("question_id") != self.question_id:
            return {"project_id": project_id, "scopes": []}
        return {
            "database": kwargs["expected_database"],
            "project_id": project_id,
            "question_id": self.question_id,
            "graph_publication_id": kwargs["graph_publication_id"],
            "scopes": [
                {
                    "id": "question-scope:renewal",
                    "question_id": self.question_id,
                    "graph_publication_id": kwargs["graph_publication_id"],
                    "concepts": [
                        {"id": concept_id, "name": concept_id.split(":")[-1]}
                        for concept_id in self.concepts
                    ],
                    "relationships": [
                        {
                            "id": "relationship:renewal_drives_revenue",
                            "type": "DRIVEN_BY",
                            "source_id": "account:revenue",
                            "target_id": "driver:renewal_rate",
                        }
                    ],
                    "data_reference_requirements": [],
                }
            ],
        }


@dataclass
class RecordingDataService:
    rows: list[dict[str, Any]]
    calls: int = 0

    def execute_registered(self, **kwargs: Any) -> DwhQueryResult:
        self.calls += 1
        return DwhQueryResult(
            id="dwh-operation:test",
            query_id=kwargs["operation_id"],
            operation_version=kwargs["operation_version"],
            statement_fingerprint="fingerprint:test",
            parameters=kwargs["parameters"],
            rows=self.rows,
            row_count=len(self.rows),
            duration_ms=1.0,
            executed_at=datetime.now(UTC).isoformat(),
        )


def _service(tmp_path, *, concepts: list[str] | None = None):
    metadata = MetadataRepository(tmp_path / "metadata.sqlite3")
    metadata.initialize_schema()
    project = metadata.create_project("Custom finance questions")
    question = metadata.create_competency_question(
        project.id,
        "How does renewal rate affect revenue?",
    )
    run = metadata.create_run(project.id)
    scope = PublishedScope(question.id, concepts=concepts)
    return (
        QuestionBindingService(metadata, scope),
        metadata,
        project,
        question,
        run,
        scope,
    )


def _register_quantitative(service, project, question, **overrides):
    operation = service.register_data_operation(
        project.id,
        "actual-revenue-by-account",
        statement=(
            "SELECT period_id, actual_revenue FROM revenue_actuals "
            "WHERE account_id = :account_id ORDER BY period_id"
        ),
        parameter_schema=PARAMETER_SCHEMA,
        result_schema=RESULT_SCHEMA,
        evidence_eligible=overrides.pop("evidence_eligible", True),
        max_rows=overrides.pop("max_rows", 24),
    )
    binding = service.register_binding(
        project.id,
        overrides.pop("binding_id", "renewal-revenue"),
        question.id,
        evidence_mode="quantitative",
        required_concept_ids=["account:revenue", "driver:renewal_rate"],
        graph_publication_id="graph-publication:renewal-v1",
        data_operation_id=operation["operation_id"],
        data_operation_version=operation["version"],
        **overrides,
    )
    return operation, binding


def test_semantic_only_binding_executes_custom_question_without_dwh(tmp_path) -> None:
    service, _, project, question, run, scope = _service(tmp_path)
    binding = service.register_binding(
        project.id,
        "renewal-impact",
        question.id,
        evidence_mode="semantic_only",
        required_concept_ids=["account:revenue", "driver:renewal_rate"],
        graph_publication_id="graph-publication:renewal-v1",
    )
    active = service.activate_binding(binding["id"], expected_database="kdaf")

    packet = service.execute_binding(
        project.id,
        "renewal-impact",
        run.id,
        expected_database="kdaf",
        data_service=None,
    )

    assert active["status"] == "active"
    assert packet["binding"] == {
        "record_id": binding["id"],
        "binding_id": "renewal-impact",
        "version": 1,
        "evidence_mode": "semantic_only",
    }
    assert packet["dwh_queries"] == []
    assert {item["id"] for item in packet["graph_nodes"]} == {
        "account:revenue",
        "driver:renewal_rate",
    }
    assert packet["provenance"]["graph_publication_id"] == ("graph-publication:renewal-v1")
    assert any(item["kind"] == "semantic_relationship" for item in packet["entries"])
    assert scope.calls[-1]["question_id"] == question.id


def test_binding_uses_stable_ids_even_if_display_text_changes(tmp_path) -> None:
    service, metadata, project, question, run, _ = _service(tmp_path)
    binding = service.register_binding(
        project.id,
        "renewal-impact",
        question.id,
        evidence_mode="semantic_only",
        required_concept_ids=["account:revenue"],
        graph_publication_id="graph-publication:renewal-v1",
    )
    service.activate_binding(binding["id"], expected_database="kdaf")
    with sqlite3.connect(metadata.store_path) as connection:
        connection.execute(
            "UPDATE kdaf_competency_questions SET question_text = ? WHERE id = ?",
            ("What is our renewal exposure?", question.id),
        )

    packet = service.execute_binding(
        project.id,
        "renewal-impact",
        run.id,
        expected_database="kdaf",
        data_service=None,
    )

    assert packet["competency_question_id"] == question.id
    assert packet["question"] == "What is our renewal exposure?"


def test_quantitative_binding_executes_exact_versioned_operation(tmp_path) -> None:
    service, _, project, question, run, _ = _service(tmp_path)
    operation, binding = _register_quantitative(service, project, question)
    service.activate_binding(binding["id"], expected_database="kdaf")
    data_service = RecordingDataService([{"period_id": "2026-10", "actual_revenue": 125000.0}])

    packet = service.execute_binding(
        project.id,
        "renewal-revenue",
        run.id,
        expected_database="kdaf",
        data_service=data_service,
        parameters={"account_id": "revenue"},
    )

    assert data_service.calls == 1
    assert packet["provenance"]["data_operation"] == {
        "operation_id": operation["operation_id"],
        "operation_version": operation["version"],
        "statement_fingerprint": "fingerprint:test",
        "parameters": {"account_id": "revenue"},
    }
    facts = [item for item in packet["entries"] if item["kind"] == "financial_fact"]
    assert facts[0]["data"]["actual_revenue"] == 125000.0


def test_registered_operation_executes_read_only_sqlite_query(tmp_path) -> None:
    service, _, project, question, run, _ = _service(tmp_path)
    _, binding = _register_quantitative(service, project, question)
    service.activate_binding(binding["id"], expected_database="kdaf")
    dwh_path = tmp_path / "finance.sqlite3"
    with sqlite3.connect(dwh_path) as connection:
        connection.execute(
            "CREATE TABLE revenue_actuals (period_id TEXT, account_id TEXT, actual_revenue REAL)"
        )
        connection.execute(
            "INSERT INTO revenue_actuals VALUES (?, ?, ?)",
            ("2026-10", "revenue", 125000.0),
        )

    packet = service.execute_binding(
        project.id,
        "renewal-revenue",
        run.id,
        expected_database="kdaf",
        data_service=ReadOnlyDwhQueryService(dwh_path),
        parameters={"account_id": "revenue"},
    )

    assert packet["dwh_queries"][0]["row_count"] == 1
    assert packet["dwh_queries"][0]["operation_version"] == 1


def test_independent_projects_execute_different_metric_contracts(tmp_path) -> None:
    revenue_service, _, revenue_project, revenue_question, revenue_run, _ = _service(
        tmp_path / "revenue"
    )
    _, revenue_binding = _register_quantitative(revenue_service, revenue_project, revenue_question)
    revenue_service.activate_binding(revenue_binding["id"], expected_database="kdaf")

    cash_service, _, cash_project, cash_question, cash_run, cash_scope = _service(
        tmp_path / "cash", concepts=["metric:cash_balance"]
    )
    cash_scope.question_id = cash_question.id
    cash_parameters = {
        "type": "object",
        "properties": {"period_id": {"type": "string"}},
        "required": ["period_id"],
        "additionalProperties": False,
    }
    cash_results = {
        "type": "object",
        "properties": {
            "entity_name": {"type": "string"},
            "cash_balance": {"type": "number"},
        },
        "required": ["entity_name", "cash_balance"],
        "additionalProperties": False,
    }
    cash_operation = cash_service.register_data_operation(
        cash_project.id,
        "cash-by-entity",
        statement="SELECT entity_name, cash_balance FROM cash_snapshot "
        "WHERE period_id = :period_id",
        parameter_schema=cash_parameters,
        result_schema=cash_results,
    )
    cash_binding = cash_service.register_binding(
        cash_project.id,
        "cash-position",
        cash_question.id,
        evidence_mode="quantitative",
        required_concept_ids=["metric:cash_balance"],
        graph_publication_id="graph-publication:cash-v1",
        data_operation_id=cash_operation["operation_id"],
        data_operation_version=cash_operation["version"],
    )
    cash_service.activate_binding(cash_binding["id"], expected_database="kdaf")

    revenue_packet = revenue_service.execute_binding(
        revenue_project.id,
        "renewal-revenue",
        revenue_run.id,
        expected_database="kdaf",
        data_service=RecordingDataService([{"period_id": "2026-10", "actual_revenue": 125000.0}]),
        parameters={"account_id": "revenue"},
    )
    cash_packet = cash_service.execute_binding(
        cash_project.id,
        "cash-position",
        cash_run.id,
        expected_database="kdaf",
        data_service=RecordingDataService([{"entity_name": "North", "cash_balance": 80000.0}]),
        parameters={"period_id": "2026-10"},
    )

    assert revenue_packet["provenance"]["data_operation"]["operation_id"] == (
        "actual-revenue-by-account"
    )
    assert cash_packet["provenance"]["data_operation"]["operation_id"] == ("cash-by-entity")


@pytest.mark.parametrize(
    ("parameters", "code"),
    [
        ({}, "missing_parameter"),
        ({"account_id": 5}, "invalid_parameter"),
        ({"account_id": "revenue", "scenario": "actual"}, "invalid_parameter"),
    ],
)
def test_parameters_must_match_registered_schema(tmp_path, parameters, code) -> None:
    service, _, project, question, run, _ = _service(tmp_path)
    _, binding = _register_quantitative(service, project, question)
    service.activate_binding(binding["id"], expected_database="kdaf")

    with pytest.raises(QuestionExecutionError) as error:
        service.execute_binding(
            project.id,
            "renewal-revenue",
            run.id,
            expected_database="kdaf",
            data_service=RecordingDataService([]),
            parameters=parameters,
        )

    assert error.value.code == code


def test_result_rows_must_match_registered_schema(tmp_path) -> None:
    service, _, project, question, run, _ = _service(tmp_path)
    _, binding = _register_quantitative(service, project, question)
    service.activate_binding(binding["id"], expected_database="kdaf")

    with pytest.raises(QuestionExecutionError) as error:
        service.execute_binding(
            project.id,
            "renewal-revenue",
            run.id,
            expected_database="kdaf",
            data_service=RecordingDataService(
                [{"period_id": "2026-10", "actual_revenue": "125000"}]
            ),
            parameters={"account_id": "revenue"},
        )

    assert error.value.code == "invalid_result_schema"


def test_missing_quantitative_rows_are_not_replaced_with_sample_facts(tmp_path) -> None:
    service, _, project, question, run, _ = _service(tmp_path)
    _, binding = _register_quantitative(service, project, question)
    service.activate_binding(binding["id"], expected_database="kdaf")

    with pytest.raises(QuestionExecutionError) as error:
        service.execute_binding(
            project.id,
            "renewal-revenue",
            run.id,
            expected_database="kdaf",
            data_service=RecordingDataService([]),
            parameters={"account_id": "revenue"},
        )

    assert error.value.code == "missing_data"


def test_activation_rejects_missing_context_and_unauthorized_data(tmp_path) -> None:
    service, _, project, question, _, scope = _service(tmp_path, concepts=["account:revenue"])
    binding = service.register_binding(
        project.id,
        "missing-scope",
        question.id,
        evidence_mode="semantic_only",
        required_concept_ids=["driver:renewal_rate"],
        graph_publication_id="graph-publication:renewal-v1",
    )
    with pytest.raises(QuestionExecutionError) as missing:
        service.activate_binding(binding["id"], expected_database="kdaf")
    assert missing.value.code == "missing_context"

    scope.concepts.append("driver:renewal_rate")
    operation, quantitative = _register_quantitative(
        service,
        project,
        question,
        binding_id="unauthorized",
        evidence_eligible=False,
    )
    assert operation["evidence_eligible"] is False
    with pytest.raises(QuestionExecutionError) as unauthorized:
        service.activate_binding(quantitative["id"], expected_database="kdaf")
    assert unauthorized.value.code == "unauthorized_data_operation"


def test_unsafe_operation_and_unknown_binding_return_explicit_errors(tmp_path) -> None:
    service, _, project, _, run, _ = _service(tmp_path)
    with pytest.raises(QuestionExecutionError) as unsafe:
        service.register_data_operation(
            project.id,
            "delete-revenue",
            statement="DELETE FROM revenue_actuals",
            parameter_schema={
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            },
            result_schema=RESULT_SCHEMA,
        )
    assert unsafe.value.code == "unsafe_query"

    with pytest.raises(QuestionExecutionError) as missing:
        service.execute_binding(
            project.id,
            "unknown-binding",
            run.id,
            expected_database="kdaf",
            data_service=None,
        )
    assert missing.value.code == "binding_not_found"


def test_activation_supersedes_previous_binding_version(tmp_path) -> None:
    service, _, project, question, run, _ = _service(tmp_path)
    first = service.register_binding(
        project.id,
        "renewal-impact",
        question.id,
        evidence_mode="semantic_only",
        required_concept_ids=["account:revenue"],
        graph_publication_id="graph-publication:renewal-v1",
    )
    service.activate_binding(first["id"], expected_database="kdaf")
    second = service.register_binding(
        project.id,
        "renewal-impact",
        question.id,
        evidence_mode="semantic_only",
        required_concept_ids=["account:revenue", "driver:renewal_rate"],
        graph_publication_id="graph-publication:renewal-v1",
    )
    service.activate_binding(second["id"], expected_database="kdaf")

    records = service.list_bindings(project.id)
    packet = service.execute_binding(
        project.id,
        "renewal-impact",
        run.id,
        expected_database="kdaf",
        data_service=None,
    )

    assert [item["status"] for item in records] == ["superseded", "active"]
    assert packet["binding"]["version"] == 2


def test_tool_surface_registers_versioned_operations_and_bindings(tmp_path) -> None:
    core = KdafCore(metadata_store_path=tmp_path / "metadata.sqlite3")
    project = core.create_project("Tool execution")
    question = core.create_competency_question(project["id"], "How does renewal affect revenue?")
    operation = call_tool(
        "data_operation.register",
        {
            "project_id": project["id"],
            "operation_id": "actual-revenue",
            "statement": "SELECT actual_revenue FROM revenue_actuals "
            "WHERE account_id = :account_id",
            "parameter_schema": PARAMETER_SCHEMA,
            "result_schema": {
                "type": "object",
                "properties": {"actual_revenue": {"type": "number"}},
                "required": ["actual_revenue"],
                "additionalProperties": False,
            },
        },
        core,
    )
    binding = call_tool(
        "question_binding.register",
        {
            "project_id": project["id"],
            "binding_id": "renewal-revenue",
            "question_id": question["id"],
            "evidence_mode": "quantitative",
            "required_concept_ids": ["account:revenue"],
            "graph_publication_id": "graph-publication:renewal-v1",
            "data_operation_id": operation["operation_id"],
            "data_operation_version": operation["version"],
        },
        core,
    )

    tool_names = {item["name"] for item in list_tools()}
    assert {
        "data_operation.register",
        "data_operation.get",
        "question_binding.register",
        "question_binding.execute",
    } <= tool_names
    assert (
        call_tool(
            "data_operation.get",
            {
                "project_id": project["id"],
                "operation_id": operation["operation_id"],
                "version": operation["version"],
            },
            core,
        )
        == operation
    )
    assert binding["data_operation_version"] == 1
    assert (
        call_tool(
            "question_binding.get",
            {"project_id": project["id"], "binding_id": "renewal-revenue"},
            core,
        )
        == binding
    )


def test_cli_registers_operation_and_binding_through_public_contract(tmp_path) -> None:
    store = tmp_path / "metadata.sqlite3"
    core = KdafCore(metadata_store_path=store)
    project = core.create_project("CLI execution")
    question = core.create_competency_question(project["id"], "How does renewal affect revenue?")
    statement = tmp_path / "operation.sql"
    parameter_schema = tmp_path / "parameters.json"
    result_schema = tmp_path / "results.json"
    statement.write_text(
        "SELECT period_id, actual_revenue FROM revenue_actuals WHERE account_id = :account_id",
        encoding="utf-8",
    )
    parameter_schema.write_text(json.dumps(PARAMETER_SCHEMA), encoding="utf-8")
    result_schema.write_text(json.dumps(RESULT_SCHEMA), encoding="utf-8")
    operation_output = StringIO()

    operation_exit = cli_main(
        [
            "--metadata-store",
            str(store),
            "data-operation",
            "register",
            project["id"],
            "actual-revenue",
            "--statement-file",
            str(statement),
            "--parameter-schema-file",
            str(parameter_schema),
            "--result-schema-file",
            str(result_schema),
        ],
        stdout=operation_output,
    )
    operation = json.loads(operation_output.getvalue())
    binding_output = StringIO()
    binding_exit = cli_main(
        [
            "--metadata-store",
            str(store),
            "question-binding",
            "register",
            project["id"],
            "renewal-revenue",
            question["id"],
            "--evidence-mode",
            "quantitative",
            "--concept-id",
            "account:revenue",
            "--publication-id",
            "graph-publication:renewal-v1",
            "--operation-id",
            operation["operation_id"],
            "--operation-version",
            str(operation["version"]),
        ],
        stdout=binding_output,
    )
    binding = json.loads(binding_output.getvalue())

    assert operation_exit == 0
    assert binding_exit == 0
    assert binding["status"] == "draft"
    assert binding["data_operation_version"] == operation["version"]


def test_tool_execution_returns_structured_unknown_binding_error(tmp_path) -> None:
    core = KdafCore(metadata_store_path=tmp_path / "metadata.sqlite3")
    project = core.create_project("Missing binding")
    run = core.create_run(project["id"])

    response = handle_message(
        {
            "tool": "question_binding.execute",
            "arguments": {
                "project_id": project["id"],
                "binding_id": "unknown-binding",
                "run_id": run["id"],
                "database": "neo4j",
            },
        },
        core,
    )

    assert response == {
        "ok": False,
        "error": {
            "code": "binding_not_found",
            "message": "Question binding not found: unknown-binding",
        },
    }
