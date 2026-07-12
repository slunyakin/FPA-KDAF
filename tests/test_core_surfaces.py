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
