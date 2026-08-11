from __future__ import annotations

import json
from io import StringIO

from kdaf.cli import main as cli_main
from kdaf.core import KdafCore
from kdaf.tool_server import call_tool, handle_message, serve


def test_core_health_and_config_summary_do_not_expose_secrets(tmp_path) -> None:
    core = KdafCore(metadata_store_path=tmp_path / "metadata.sqlite3")

    assert core.health()["status"] == "ok"

    summary = core.config_summary()
    serialized = json.dumps(summary)
    assert "password" not in serialized.lower()
    assert "kdaf_metadata_password" not in serialized
    assert summary["metadata_db"]["database"] == "kdaf_metadata"


def test_cli_created_project_is_visible_through_tool_server(tmp_path) -> None:
    store = tmp_path / "metadata.sqlite3"
    stdout = StringIO()

    exit_code = cli_main(
        ["--metadata-store", str(store), "project", "create", "CLI Project"],
        stdout=stdout,
    )

    assert exit_code == 0
    created = json.loads(stdout.getvalue())
    core = KdafCore(metadata_store_path=store)

    assert call_tool("project.get", {"id": created["id"]}, core)["name"] == "CLI Project"


def test_tool_server_created_project_is_visible_through_cli(tmp_path) -> None:
    store = tmp_path / "metadata.sqlite3"
    core = KdafCore(metadata_store_path=store)
    created = call_tool("project.create", {"name": "Agent Project"}, core)

    stdout = StringIO()
    exit_code = cli_main(
        ["--metadata-store", str(store), "project", "get", created["id"]],
        stdout=stdout,
    )

    assert exit_code == 0
    assert json.loads(stdout.getvalue())["name"] == "Agent Project"


def test_cli_manages_competency_questions_and_mvg_artifacts(tmp_path) -> None:
    store = tmp_path / "metadata.sqlite3"
    project_stdout = StringIO()
    cli_main(
        ["--metadata-store", str(store), "project", "create", "CLI Project"],
        stdout=project_stdout,
    )
    project = json.loads(project_stdout.getvalue())

    question_stdout = StringIO()
    question_exit_code = cli_main(
        [
            "--metadata-store",
            str(store),
            "competency-question",
            "create",
            project["id"],
            "Where is actual spend over budget this quarter?",
            "--business-context",
            "Monthly business review",
        ],
        stdout=question_stdout,
    )
    question = json.loads(question_stdout.getvalue())

    mvg_stdout = StringIO()
    mvg_exit_code = cli_main(
        [
            "--metadata-store",
            str(store),
            "mvg",
            "create",
            project["id"],
            "Budget variance MVG",
            "--description",
            "Initial graph scope for variance analysis",
            "--question-id",
            question["id"],
            "--concept-id",
            "metric:budget_variance",
            "--concept-id",
            "department:sales",
        ],
        stdout=mvg_stdout,
    )
    mvg = json.loads(mvg_stdout.getvalue())

    assert question_exit_code == 0
    assert question["project_id"] == project["id"]
    assert question["business_context"] == "Monthly business review"
    assert mvg_exit_code == 0
    assert mvg["question_ids"] == [question["id"]]
    assert mvg["concept_ids"] == ["department:sales", "metric:budget_variance"]


def test_tool_server_manages_competency_questions_and_mvg_artifacts(tmp_path) -> None:
    core = KdafCore(metadata_store_path=tmp_path / "metadata.sqlite3")
    project = call_tool("project.create", {"name": "Agent Project"}, core)
    question = call_tool(
        "competency_question.create",
        {
            "project_id": project["id"],
            "question_text": "Which departments are driving forecast variance?",
        },
        core,
    )
    followup_question = call_tool(
        "competency_question.create",
        {
            "project_id": project["id"],
            "question_text": "Which scenarios should be compared for the forecast review?",
        },
        core,
    )

    artifact = call_tool(
        "mvg.create",
        {
            "project_id": project["id"],
            "name": "Forecast variance MVG",
            "question_ids": [question["id"]],
            "concept_ids": ["metric:forecast_variance"],
        },
        core,
    )
    updated = call_tool(
        "mvg.add_concept",
        {"mvg_id": artifact["id"], "concept_id": "scenario:forecast"},
        core,
    )
    updated = call_tool(
        "mvg.add_question",
        {"mvg_id": artifact["id"], "question_id": followup_question["id"]},
        core,
    )

    assert call_tool("competency_question.get", {"id": question["id"]}, core) == question
    assert call_tool("mvg.get", {"id": artifact["id"]}, core) == updated
    assert call_tool("mvg.list", {"project_id": project["id"]}, core) == [updated]
    assert set(updated["question_ids"]) == {question["id"], followup_question["id"]}
    assert updated["concept_ids"] == ["metric:forecast_variance", "scenario:forecast"]


def test_tool_server_rejects_invalid_mvg_list_arguments(tmp_path) -> None:
    core = KdafCore(metadata_store_path=tmp_path / "metadata.sqlite3")
    project = call_tool("project.create", {"name": "Agent Project"}, core)

    response = handle_message(
        {
            "tool": "mvg.create",
            "arguments": {
                "project_id": project["id"],
                "name": "Invalid MVG",
                "concept_ids": "metric:budget_variance",
            },
        },
        core,
    )

    assert response == {
        "ok": False,
        "error": {
            "code": "invalid_argument",
            "message": "Argument must be a list of strings: concept_ids",
        },
    }


def test_cli_loads_starter_dwh_and_returns_sample_facts(tmp_path) -> None:
    metadata_store = tmp_path / "metadata.sqlite3"
    dwh_store = tmp_path / "starter_dwh.sqlite3"
    load_stdout = StringIO()

    load_exit_code = cli_main(
        [
            "--metadata-store",
            str(metadata_store),
            "starter-dwh",
            "load",
            "--dwh-store",
            str(dwh_store),
        ],
        stdout=load_stdout,
    )

    assert load_exit_code == 0
    assert json.loads(load_stdout.getvalue())["row_counts"]["fpna_facts"] == 24

    facts_stdout = StringIO()
    facts_exit_code = cli_main(
        [
            "--metadata-store",
            str(metadata_store),
            "starter-dwh",
            "facts",
            "--dwh-store",
            str(dwh_store),
        ],
        stdout=facts_stdout,
    )

    assert facts_exit_code == 0
    facts = json.loads(facts_stdout.getvalue())
    assert facts["budget_vs_actuals"][0]["variance_amount"] == 5000
    assert facts["department_spend"][0]["department_name"] == "Engineering"


def test_tool_server_loads_starter_dwh_and_returns_sample_facts(tmp_path) -> None:
    core = KdafCore(metadata_store_path=tmp_path / "metadata.sqlite3")
    dwh_store = tmp_path / "starter_dwh.sqlite3"

    load_response = handle_message(
        {"tool": "starter_dwh.load", "arguments": {"dwh_store_path": str(dwh_store)}},
        core,
    )
    facts_response = handle_message(
        {"tool": "starter_dwh.facts", "arguments": {"dwh_store_path": str(dwh_store)}},
        core,
    )

    assert load_response["ok"] is True
    assert load_response["result"]["row_counts"]["fpna_facts"] == 24
    assert facts_response["ok"] is True
    assert facts_response["result"]["budget_vs_actuals"][1]["actual_amount"] == 108000


def test_tool_server_starter_dwh_facts_before_load_returns_structured_error(tmp_path) -> None:
    core = KdafCore(metadata_store_path=tmp_path / "metadata.sqlite3")

    response = handle_message(
        {"tool": "starter_dwh.facts", "arguments": {"dwh_store_path": str(tmp_path / "empty.db")}},
        core,
    )

    assert response == {
        "ok": False,
        "error": {
            "code": "starter_dwh_not_loaded",
            "message": "Starter DWH has not been loaded",
        },
    }


def test_tool_server_handles_json_line_health_request(tmp_path) -> None:
    core = KdafCore(metadata_store_path=tmp_path / "metadata.sqlite3")
    stdin = StringIO('{"tool": "health", "arguments": {}}\n')
    stdout = StringIO()

    serve(core=core, stdin=stdin, stdout=stdout)

    response = json.loads(stdout.getvalue())
    assert response["ok"] is True
    assert response["result"]["status"] == "ok"


def test_tool_server_malformed_json_line_returns_error_and_keeps_serving(tmp_path) -> None:
    core = KdafCore(metadata_store_path=tmp_path / "metadata.sqlite3")
    stdin = StringIO('{"tool": "health"\n{"tool": "health", "arguments": {}}\n')
    stdout = StringIO()

    serve(core=core, stdin=stdin, stdout=stdout)

    responses = [json.loads(line) for line in stdout.getvalue().splitlines()]
    assert responses[0]["ok"] is False
    assert responses[0]["error"]["code"] == "invalid_json"
    assert responses[1]["ok"] is True
    assert responses[1]["result"]["status"] == "ok"


def test_tool_server_accepts_mcp_style_tool_call_shape(tmp_path) -> None:
    core = KdafCore(metadata_store_path=tmp_path / "metadata.sqlite3")

    response = handle_message(
        {
            "method": "tools/call",
            "params": {"name": "project.create", "arguments": {"name": "MCP Project"}},
        },
        core,
    )

    assert response["ok"] is True
    assert response["result"]["name"] == "MCP Project"


def test_tool_server_missing_tool_name_returns_structured_error(tmp_path) -> None:
    core = KdafCore(metadata_store_path=tmp_path / "metadata.sqlite3")

    response = handle_message({"arguments": {}}, core)

    assert response == {
        "ok": False,
        "error": {"code": "missing_tool", "message": "Missing required tool name"},
    }


def test_tool_server_unknown_tool_returns_structured_error(tmp_path) -> None:
    core = KdafCore(metadata_store_path=tmp_path / "metadata.sqlite3")

    response = handle_message({"tool": "missing.tool", "arguments": {}}, core)

    assert response == {
        "ok": False,
        "error": {"code": "unknown_tool", "message": "Unknown tool: missing.tool"},
    }


def test_tool_server_missing_required_argument_returns_structured_error(tmp_path) -> None:
    core = KdafCore(metadata_store_path=tmp_path / "metadata.sqlite3")

    response = handle_message({"tool": "project.get", "arguments": {}}, core)

    assert response == {
        "ok": False,
        "error": {"code": "missing_argument", "message": "Missing required argument: id"},
    }


def test_tool_server_invalid_project_and_run_ids_return_structured_errors(tmp_path) -> None:
    core = KdafCore(metadata_store_path=tmp_path / "metadata.sqlite3")

    project_response = handle_message(
        {"tool": "project.get", "arguments": {"id": "missing-project"}},
        core,
    )
    run_response = handle_message(
        {"tool": "run.get", "arguments": {"id": "missing-run"}},
        core,
    )

    assert project_response == {
        "ok": False,
        "error": {"code": "not_found", "message": "Project not found: missing-project"},
    }
    assert run_response == {
        "ok": False,
        "error": {"code": "not_found", "message": "Run not found: missing-run"},
    }


def test_cli_invalid_project_id_returns_structured_error(tmp_path) -> None:
    stdout = StringIO()

    exit_code = cli_main(
        [
            "--metadata-store",
            str(tmp_path / "metadata.sqlite3"),
            "project",
            "get",
            "missing-project",
        ],
        stdout=stdout,
    )

    assert exit_code == 2
    assert json.loads(stdout.getvalue()) == {
        "ok": False,
        "error": {"code": "not_found", "message": "Project not found: missing-project"},
    }
