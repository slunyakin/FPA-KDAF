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
