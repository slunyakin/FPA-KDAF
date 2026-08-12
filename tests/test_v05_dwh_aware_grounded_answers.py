from __future__ import annotations

import json
import sqlite3
import sys
from io import StringIO
from types import SimpleNamespace

import pytest

from kdaf.answers import GroundedAnswerService
from kdaf.cli import main as cli_main
from kdaf.core import KdafCore, KdafError
from kdaf.retrieval import (
    PostgresDwhQueryService,
    ReadOnlyDwhQueryService,
    RetrievalError,
    _assert_read_only,
)
from kdaf.tool_server import handle_message, serve


def _workspace(tmp_path):
    metadata = tmp_path / "metadata.sqlite3"
    dwh = tmp_path / "financial_dwh.sqlite3"
    graph = tmp_path / "graph_context.sqlite3"
    core = KdafCore(
        metadata_store_path=metadata,
        dwh_store_path=dwh,
        graph_store_path=graph,
    )
    project = core.create_project("v0.5 FP&A")
    core.load_starter_dwh(dwh)
    core.load_starter_questions(project["id"])
    question = next(
        question
        for question in core.list_competency_questions(project["id"])
        if question["question_text"] == "Where is actual revenue above or below budget by month?"
    )
    run = core.create_run(project["id"], "retrieval")
    return core, metadata, dwh, graph, project, question, run


def test_read_only_dwh_query_returns_rows_and_captures_metadata(tmp_path) -> None:
    core, _, dwh, _, _, _, _ = _workspace(tmp_path)

    result = core.query_dwh("budget_vs_actuals", {"account_id": "revenue"}, dwh)

    assert result["store"] == "financial_dwh"
    assert result["mode"] == "read_only"
    assert result["row_count"] == 3
    assert result["rows"][0]["actual_amount"] == 100000
    assert len(result["statement_fingerprint"]) == 64
    event = core.metadata.list_audit_events("dwh.query.executed")[-1]
    assert event.payload["query_id"] == "budget_vs_actuals"
    assert event.payload["row_count"] == 3
    assert "rows" not in event.payload


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM fpna_facts",
        "WITH removed AS (DELETE FROM fpna_facts RETURNING *) SELECT * FROM removed",
        "SELECT 1; DROP TABLE fpna_facts",
        "PRAGMA table_info(fpna_facts)",
    ],
)
def test_dwh_read_boundary_rejects_write_or_multi_statement_sql(sql) -> None:
    with pytest.raises(RetrievalError) as exc_info:
        _assert_read_only(sql)
    assert exc_info.value.code == "unsafe_query"


def test_dwh_public_service_rejects_malformed_parameters_and_unknown_query(tmp_path) -> None:
    _, _, dwh, _, _, _, _ = _workspace(tmp_path)
    service = ReadOnlyDwhQueryService(dwh)

    with pytest.raises(RetrievalError) as malformed:
        service.execute("budget_vs_actuals", ["revenue"])  # type: ignore[arg-type]
    with pytest.raises(RetrievalError) as unexpected:
        service.execute("budget_vs_actuals", {"sql": "DELETE FROM fpna_facts"})
    with pytest.raises(RetrievalError) as missing:
        service.execute("does-not-exist")

    assert malformed.value.code == "invalid_input"
    assert unexpected.value.code == "invalid_parameter"
    assert missing.value.code == "not_found"


def test_postgres_dwh_adapter_enforces_read_only_transaction(monkeypatch) -> None:
    calls = []

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def execute(self, statement, parameters=None):
            calls.append((statement, parameters))

        def fetchall(self):
            return [{"period_id": "2026-01", "actual_amount": 100000}]

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def cursor(self):
            return Cursor()

    def connect(**settings):
        calls.append(("connect", settings))
        return Connection()

    fake_psycopg = SimpleNamespace(connect=connect, rows=SimpleNamespace(dict_row=object()))
    monkeypatch.setitem(sys.modules, "psycopg", fake_psycopg)
    service = PostgresDwhQueryService(
        host="dwh",
        port=5432,
        database="finance",
        user="reader",
        password="secret",
    )

    result = service.execute("budget_vs_actuals", {"account_id": "revenue"})

    assert calls[0][1]["options"] == "-c default_transaction_read_only=on"
    assert calls[1] == ("SET TRANSACTION READ ONLY", None)
    assert "%(account_id)s" in calls[2][0]
    assert calls[2][1] == {"account_id": "revenue"}
    assert result.mode == "read_only"


def test_carp_retrieval_returns_semantics_relationships_provenance_and_validation(tmp_path) -> None:
    core, _, _, _, _, question, _ = _workspace(tmp_path)
    source_file = tmp_path / "actuals.csv"
    source_file.write_text("account,amount\nRevenue,100000\n", encoding="utf-8")
    source = core.register_source("Actuals", str(source_file))
    extraction = core.extract_source(source["id"])
    validation = core.enqueue_validation("extraction", extraction["id"])
    core.approve_validation(validation["id"], "controller", "Reconciled")

    context = core.retrieve_carp_context(question["id"], offline_graph=True)

    assert {node["id"] for node in context["nodes"]} >= {
        "metric:budget_vs_actuals",
        "account:revenue",
        "scenario:actual",
        "scenario:budget",
    }
    assert any(item["type"] == "DEPENDS_ON" for item in context["relationships"])
    assert any(item["table"] == "fpna_accounts" for item in context["dimensions"])
    assert all(node["validation_state"] == "seeded" for node in context["nodes"])
    assert any(link["source_id"] == source["id"] for link in context["source_links"])
    assert context["validation_states"][0]["status"] == "approved"
    assert context["provenance"]["question_id"] == question["id"]


def test_evidence_packet_references_every_required_audit_dimension(tmp_path) -> None:
    core, _, dwh, _, project, question, run = _workspace(tmp_path)

    packet = core.build_evidence_packet(
        question["id"], run["id"], dwh_store_path=dwh, offline_graph=True
    )

    assert packet["project_id"] == project["id"]
    assert packet["run_id"] == run["id"]
    assert packet["competency_question_id"] == question["id"]
    assert packet["dwh_queries"][0]["row_count"] == 3
    assert packet["graph_nodes"]
    assert packet["graph_relationships"]
    assert "source_records" in packet
    assert "validation_decisions" in packet
    assert packet["provenance"]["dwh_query_ids"]
    assert all(entry["id"] for entry in packet["entries"])


def test_financial_numbers_are_in_packet_dwh_entries_but_not_graph_context(tmp_path) -> None:
    core, _, dwh, graph, _, question, run = _workspace(tmp_path)
    packet = core.build_evidence_packet(
        question["id"], run["id"], dwh_store_path=dwh, offline_graph=True
    )

    assert "100000" in json.dumps(packet["dwh_queries"])
    assert "100000" not in json.dumps(packet["graph_nodes"])
    with sqlite3.connect(graph) as connection:
        tables = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    assert all("fact" not in row[0] for row in tables)


def test_grounded_answer_has_valid_citations_and_full_prompt_output_audit(tmp_path) -> None:
    core, _, dwh, _, project, question, run = _workspace(tmp_path)
    packet = core.build_evidence_packet(
        question["id"], run["id"], dwh_store_path=dwh, offline_graph=True
    )

    answer = core.generate_grounded_answer(packet)

    entry_ids = {entry["id"] for entry in packet["entries"]}
    assert answer["status"] == "grounded"
    assert set(answer["citations"]) <= entry_ids
    assert answer["project_id"] == project["id"]
    audit = core.metadata.list_audit_events("answer.generated")[-1].payload
    assert audit["provider"] == "deterministic"
    assert audit["model"] == "kdaf-grounded-demo"
    assert audit["parameters"] == {}
    assert audit["prompt"]
    assert audit["output"] == answer["answer"]
    assert audit["run_id"] == run["id"]


def test_answer_service_refuses_unsupported_claim_and_uncited_provider_output(tmp_path) -> None:
    core, _, dwh, _, _, question, run = _workspace(tmp_path)
    packet = core.build_evidence_packet(
        question["id"], run["id"], dwh_store_path=dwh, offline_graph=True
    )
    refusal = core.generate_grounded_answer(packet, requested_claim="What was the cash balance?")

    class UncitedProvider:
        name = "uncited-test"

        def generate(self, prompt, model, parameters):
            return "Revenue was definitely one million dollars."

    uncited = GroundedAnswerService(core.metadata).generate(packet, UncitedProvider(), model="test")

    assert refusal["status"] == "insufficiently_supported"
    assert refusal["citations"] == []
    assert uncited["status"] == "insufficiently_supported"
    assert "one million" not in uncited["answer"]

    malformed_packet = {**packet, "entries": [{}]}
    malformed = handle_message(
        {"tool": "answer.generate", "arguments": {"evidence_packet": malformed_packet}},
        core,
    )
    assert malformed == {
        "ok": False,
        "error": {
            "code": "missing_field",
            "message": "Evidence packet entry ID is required",
        },
    }


def test_grounded_demo_proves_complete_vertical_slice(tmp_path) -> None:
    core, _, dwh, _, _, question, run = _workspace(tmp_path)

    result = core.grounded_answer_demo(
        question["id"], run["id"], dwh_store_path=dwh, offline_graph=True
    )

    assert result["evidence_packet"]["graph_nodes"]
    assert result["evidence_packet"]["dwh_queries"][0]["rows"]
    assert result["answer"]["status"] == "grounded"
    assert result["unsupported_claim"]["status"] == "insufficiently_supported"
    assert result["architecture"]["graph_stores_financial_facts"] is False
    assert len(core.metadata.list_audit_events("answer.generated")) == 2


def test_cli_public_retrieval_evidence_answer_and_demo_entrypoints(tmp_path) -> None:
    core, metadata, dwh, _, _, question, run = _workspace(tmp_path)
    common = ["--metadata-store", str(metadata), "--dwh-store", str(dwh)]

    dwh_output = StringIO()
    assert cli_main([*common, "dwh", "query", "budget_vs_actuals"], stdout=dwh_output) == 0
    assert json.loads(dwh_output.getvalue())["row_count"] == 3

    graph_output = StringIO()
    assert (
        cli_main(
            [*common, "carp", "retrieve", question["id"], "--offline-graph"],
            stdout=graph_output,
        )
        == 0
    )
    assert json.loads(graph_output.getvalue())["nodes"]

    evidence_output = StringIO()
    assert (
        cli_main(
            [
                *common,
                "evidence",
                "build",
                question["id"],
                run["id"],
                "--offline-graph",
            ],
            stdout=evidence_output,
        )
        == 0
    )
    packet = json.loads(evidence_output.getvalue())
    evidence_file = tmp_path / "evidence.json"
    evidence_file.write_text(json.dumps(packet), encoding="utf-8")

    answer_output = StringIO()
    assert cli_main([*common, "answer", "generate", str(evidence_file)], stdout=answer_output) == 0
    assert json.loads(answer_output.getvalue())["status"] == "grounded"

    demo_output = StringIO()
    assert (
        cli_main(
            [*common, "grounded-demo", question["id"], run["id"], "--offline-graph"],
            stdout=demo_output,
        )
        == 0
    )
    assert json.loads(demo_output.getvalue())["answer"]["status"] == "grounded"
    assert core.metadata.get_run(run["id"]).id == run["id"]


def test_tool_server_public_v05_entrypoints_share_core_workflow(tmp_path) -> None:
    core, _, dwh, _, _, question, run = _workspace(tmp_path)

    query = handle_message(
        {
            "tool": "dwh.query",
            "arguments": {"query_id": "budget_vs_actuals"},
        },
        core,
    )
    graph = handle_message(
        {
            "tool": "carp.retrieve",
            "arguments": {"question_id": question["id"], "offline_graph": True},
        },
        core,
    )
    evidence = handle_message(
        {
            "tool": "evidence.build",
            "arguments": {
                "question_id": question["id"],
                "run_id": run["id"],
                "offline_graph": True,
            },
        },
        core,
    )
    answer = handle_message(
        {
            "tool": "answer.generate",
            "arguments": {"evidence_packet": evidence["result"]},
        },
        core,
    )
    demo = handle_message(
        {
            "tool": "grounded_answer.demo",
            "arguments": {
                "question_id": question["id"],
                "run_id": run["id"],
                "offline_graph": True,
            },
        },
        core,
    )

    assert query["ok"] and query["result"]["mode"] == "read_only"
    assert graph["ok"] and graph["result"]["provenance"]
    assert evidence["ok"] and evidence["result"]["entries"]
    assert answer["ok"] and answer["result"]["status"] == "grounded"
    assert demo["ok"] and demo["result"]["unsupported_claim"]["status"] == (
        "insufficiently_supported"
    )


@pytest.mark.parametrize(
    ("message", "code"),
    [
        ({"tool": "dwh.query", "arguments": {}}, "missing_argument"),
        (
            {"tool": "dwh.query", "arguments": {"query_id": "x", "parameters": []}},
            "invalid_argument",
        ),
        ({"tool": "dwh.query", "arguments": {"query_id": "missing"}}, "not_found"),
        ({"tool": "carp.retrieve", "arguments": {}}, "missing_argument"),
        (
            {
                "tool": "carp.retrieve",
                "arguments": {"question_id": "missing", "offline_graph": True},
            },
            "not_found",
        ),
        (
            {
                "tool": "carp.retrieve",
                "arguments": {"question_id": "missing", "offline_graph": "yes"},
            },
            "invalid_argument",
        ),
        ({"tool": "evidence.build", "arguments": {"question_id": "x"}}, "missing_argument"),
        ({"tool": "answer.generate", "arguments": {}}, "missing_argument"),
        (
            {"tool": "answer.generate", "arguments": {"evidence_packet": []}},
            "invalid_argument",
        ),
        (
            {"tool": "answer.generate", "arguments": {"evidence_packet": {}}},
            "missing_field",
        ),
        (
            {
                "tool": "answer.generate",
                "arguments": {
                    "evidence_packet": {
                        "id": "packet",
                        "project_id": "missing-project",
                        "run_id": "missing-run",
                        "competency_question_id": "missing-question",
                        "question": "Missing?",
                        "entries": [],
                    }
                },
            },
            "not_found",
        ),
        (
            {
                "tool": "grounded_answer.demo",
                "arguments": {"question_id": "missing", "run_id": "missing"},
            },
            "not_found",
        ),
    ],
)
def test_tool_server_v05_negative_paths_have_stable_machine_shape(tmp_path, message, code) -> None:
    response = handle_message(message, KdafCore(metadata_store_path=tmp_path / "metadata.sqlite3"))

    assert response["ok"] is False
    assert response["error"]["code"] == code
    assert set(response["error"]) == {"code", "message"}


def test_cli_v05_malformed_missing_and_not_found_inputs_are_stable(tmp_path) -> None:
    metadata = tmp_path / "metadata.sqlite3"
    malformed_packet = tmp_path / "malformed.json"
    malformed_packet.write_text("{not-json", encoding="utf-8")
    incomplete_packet = tmp_path / "incomplete.json"
    incomplete_packet.write_text("{}", encoding="utf-8")
    cases = [
        (["dwh", "query"], "invalid_arguments"),
        (["dwh", "query", "unknown"], "not_found"),
        (
            ["dwh", "query", "budget_vs_actuals", "--parameters-json", "[]"],
            "invalid_input",
        ),
        (["carp", "retrieve", "missing", "--offline-graph"], "not_found"),
        (["answer", "generate", str(tmp_path / "missing-secret.json")], "not_found"),
        (["answer", "generate", str(malformed_packet)], "invalid_input"),
        (["answer", "generate", str(incomplete_packet)], "missing_field"),
        (["evidence", "build", "missing", "missing", "--offline-graph"], "not_found"),
    ]
    for command, expected_code in cases:
        output = StringIO()
        exit_code = cli_main(["--metadata-store", str(metadata), *command], stdout=output)
        assert exit_code == 2
        error = json.loads(output.getvalue())["error"]
        assert error["code"] == expected_code
        assert "missing-secret" not in error["message"]


def test_provider_failure_does_not_leak_api_key_or_endpoint(tmp_path) -> None:
    core, _, dwh, _, _, question, run = _workspace(tmp_path)
    packet = core.build_evidence_packet(
        question["id"], run["id"], dwh_store_path=dwh, offline_graph=True
    )
    secret = "super-secret-token"
    response = handle_message(
        {
            "tool": "answer.generate",
            "arguments": {
                "evidence_packet": packet,
                "provider": "openai-compatible",
                "model": "test",
                "base_url": "http://127.0.0.1:1/private-endpoint",
                "api_key": secret,
            },
        },
        core,
    )

    rendered = json.dumps(response)
    assert response["error"]["code"] == "provider_unavailable"
    assert secret not in rendered
    assert "private-endpoint" not in rendered


def test_tool_server_survives_bad_v05_request(tmp_path) -> None:
    core = KdafCore(metadata_store_path=tmp_path / "metadata.sqlite3")
    stdin = StringIO(
        '{"tool":"answer.generate","arguments":{"evidence_packet":[]}}\n'
        '{"tool":"health","arguments":{}}\n'
    )
    stdout = StringIO()

    serve(core, stdin, stdout)

    responses = [json.loads(line) for line in stdout.getvalue().splitlines()]
    assert responses[0]["error"]["code"] == "invalid_argument"
    assert responses[1]["ok"] is True


def test_evidence_rejects_run_from_another_project(tmp_path) -> None:
    core, _, dwh, _, _, question, run = _workspace(tmp_path)
    other_project = core.create_project("Other")
    other_run = core.create_run(other_project["id"])

    with pytest.raises(KdafError) as exc_info:
        core.build_evidence_packet(
            question["id"], other_run["id"], dwh_store_path=dwh, offline_graph=True
        )
    assert exc_info.value.code == "invalid_id"

    packet = core.build_evidence_packet(
        question["id"], run["id"], dwh_store_path=dwh, offline_graph=True
    )
    packet["run_id"] = other_run["id"]
    with pytest.raises(KdafError) as answer_error:
        core.generate_grounded_answer(packet)
    assert answer_error.value.code == "invalid_id"
