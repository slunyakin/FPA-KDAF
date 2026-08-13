from __future__ import annotations

import json
import subprocess
import sys
from io import StringIO

import pytest

from kdaf.cli import main as cli_main
from kdaf.core import KdafCore, KdafError
from kdaf.tool_server import handle_message, serve


def _paths(tmp_path):
    return (
        tmp_path / "metadata.sqlite3",
        tmp_path / "financial_dwh.sqlite3",
        tmp_path / "graph.sqlite3",
    )


def test_public_demo_completes_project_to_eval_ready_answer(tmp_path) -> None:
    metadata, dwh, graph = _paths(tmp_path)
    core = KdafCore(
        metadata_store_path=metadata,
        dwh_store_path=dwh,
        graph_store_path=graph,
    )

    result = core.run_public_demo(
        "Public FP&A Demo", dwh_store_path=dwh, offline_graph=True
    )

    assert result["project"]["name"] == "Public FP&A Demo"
    assert result["starter_kit"]["status"] == "loaded"
    assert result["starter_kit"]["dwh"]["row_counts"]["fpna_facts"] == 24
    assert result["carp_context"]["nodes"]
    assert result["evidence_packet"]["dwh_queries"][0]["row_count"] == 3
    assert result["answer"]["status"] == "grounded"
    assert result["answer"]["citations"]
    assert result["unsupported_claim"]["status"] == "insufficiently_supported"
    assert result["evaluation_result"]["status"] == "passed"
    assert result["architecture"]["graph_stores_financial_facts"] is False
    stored = core.get_evaluation_result(result["evaluation_result"]["id"])
    assert stored == result["evaluation_result"]


@pytest.mark.parametrize(
    ("project_name", "category", "code"),
    [("", "budget_vs_actuals", "missing_field"), ("Demo", "missing", "not_found")],
)
def test_public_demo_rejects_missing_fields_and_invalid_categories(
    project_name, category, code, tmp_path
) -> None:
    metadata, dwh, graph = _paths(tmp_path)
    core = KdafCore(
        metadata_store_path=metadata,
        dwh_store_path=dwh,
        graph_store_path=graph,
    )

    with pytest.raises(KdafError) as exc_info:
        core.run_public_demo(
            project_name,
            question_category=category,
            dwh_store_path=dwh,
            offline_graph=True,
        )

    assert exc_info.value.code == code


def test_public_demo_cli_public_entrypoint_valid_and_malformed(tmp_path) -> None:
    metadata, dwh, graph = _paths(tmp_path)
    common = [
        "--metadata-store",
        str(metadata),
        "--dwh-store",
        str(dwh),
        "--graph-store",
        str(graph),
    ]
    output = StringIO()
    code = cli_main(common + ["public-demo", "CLI Demo", "--offline-graph"], output)
    payload = json.loads(output.getvalue())

    assert code == 0
    assert payload["answer"]["status"] == "grounded"
    assert payload["evaluation_result"]["status"] == "passed"

    output = StringIO()
    code = cli_main(common + ["public-demo"], output)
    assert code == 2
    assert json.loads(output.getvalue())["error"]["code"] == "invalid_arguments"


def test_public_demo_tool_server_valid_negative_and_server_survival(tmp_path) -> None:
    metadata, dwh, graph = _paths(tmp_path)
    core = KdafCore(
        metadata_store_path=metadata,
        dwh_store_path=dwh,
        graph_store_path=graph,
    )
    valid = handle_message(
        {
            "tool": "public_demo.run",
            "arguments": {
                "project_name": "Tool Demo",
                "dwh_store_path": str(dwh),
                "offline_graph": True,
            },
        },
        core,
    )
    missing = handle_message({"tool": "public_demo.run", "arguments": {}}, core)
    malformed = handle_message(
        {
            "tool": "public_demo.run",
            "arguments": {"project_name": "Demo", "offline_graph": "yes"},
        },
        core,
    )
    invalid = handle_message(
        {
            "tool": "public_demo.run",
            "arguments": {
                "project_name": "Demo",
                "question_category": "missing",
                "offline_graph": True,
            },
        },
        core,
    )

    assert valid["ok"] is True
    assert missing["error"]["code"] == "missing_argument"
    assert malformed["error"]["code"] == "invalid_argument"
    assert invalid["error"]["code"] == "not_found"

    output = StringIO()
    serve(core, StringIO("[]\n{\"tool\":\"health\"}\n"), output)
    responses = [json.loads(line) for line in output.getvalue().splitlines()]
    assert responses[0]["error"]["code"] == "invalid_request"
    assert responses[1]["ok"] is True
    assert "secret" not in output.getvalue().lower()


def test_documented_public_demo_script_runs_offline(tmp_path) -> None:
    metadata, dwh, graph = _paths(tmp_path)
    process = subprocess.run(
        [
            sys.executable,
            "scripts/run_public_demo.py",
            "--metadata-store",
            str(metadata),
            "--dwh-store",
            str(dwh),
            "--graph-store",
            str(graph),
            "--project-name",
            "Script Demo",
            "--offline-graph",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert process.returncode == 0, process.stderr
    payload = json.loads(process.stdout)
    assert payload["ok"] is True
    assert payload["result"]["project"]["name"] == "Script Demo"
    assert payload["result"]["answer"]["citations"]


def test_public_demo_script_has_stable_error_for_invalid_category(tmp_path) -> None:
    metadata, dwh, graph = _paths(tmp_path)
    process = subprocess.run(
        [
            sys.executable,
            "scripts/run_public_demo.py",
            "--metadata-store",
            str(metadata),
            "--dwh-store",
            str(dwh),
            "--graph-store",
            str(graph),
            "--question-category",
            "missing",
            "--offline-graph",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert process.returncode == 2
    assert json.loads(process.stdout) == {
        "ok": False,
        "error": {
            "code": "not_found",
            "message": "Starter question category not found: missing",
        },
    }
