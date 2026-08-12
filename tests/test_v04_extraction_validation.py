from __future__ import annotations

import json
import sqlite3
from io import StringIO

import pytest

from kdaf.cli import main as cli_main
from kdaf.core import KdafCore, KdafError
from kdaf.extraction import ExtractionDwhRepository
from kdaf.tool_server import handle_message, serve


def _stores(tmp_path) -> tuple[object, object, object]:
    return (
        tmp_path / "metadata.sqlite3",
        tmp_path / "financial_dwh.sqlite3",
        tmp_path / "graph.sqlite3",
    )


def _core(tmp_path) -> KdafCore:
    metadata, dwh, graph = _stores(tmp_path)
    return KdafCore(
        metadata_store_path=metadata,
        dwh_store_path=dwh,
        graph_store_path=graph,
    )


def _write_csv(tmp_path):
    path = tmp_path / "actuals.csv"
    path.write_text(
        "account,period,amount\nRevenue,2026-01,100000\nPayroll,2026-01,46000\n",
        encoding="utf-8",
    )
    return path


def test_core_extraction_provenance_and_validation_lifecycle(tmp_path) -> None:
    core = _core(tmp_path)
    source = core.register_source(
        "January actuals",
        str(_write_csv(tmp_path)),
        metadata={"owner": "FP&A"},
    )

    extraction = core.extract_source(source["id"])
    provenance = core.get_provenance(extraction["id"])

    assert extraction["status"] == "completed"
    assert extraction["row_count"] == 2
    assert extraction["provenance_link_count"] == 4
    assert provenance["source"]["id"] == source["id"]
    assert provenance["dwh"]["source_id"] == source["id"]
    assert [row["row_number"] for row in provenance["dwh"]["rows"]] == [1, 2]
    assert provenance["graph"][0]["relationship"] == "DERIVED_FROM"

    item = core.enqueue_validation("extraction", extraction["id"], {"check": "source totals"})
    needs_changes = core.comment_validation(item["id"], "reviewer@example.com", "Recheck total")
    approved = core.approve_validation(item["id"], "reviewer@example.com", "Totals reconcile")

    assert item["status"] == "pending"
    assert needs_changes["status"] == "needs_changes"
    assert approved["status"] == "approved"
    assert approved["decided_at"] is not None
    assert [event["action"] for event in approved["decisions"]] == [
        "enqueue",
        "comment",
        "approved",
    ]
    assert all(event["created_at"] for event in approved["decisions"])


def test_financial_values_stay_in_dwh_and_out_of_graph(tmp_path) -> None:
    core = _core(tmp_path)
    source = core.register_source("Actuals", str(_write_csv(tmp_path)))
    extraction = core.extract_source(source["id"])
    _, dwh_path, graph_path = _stores(tmp_path)

    rows = ExtractionDwhRepository(dwh_path).read_rows(extraction["id"])
    assert rows[0]["amount"] == "100000"

    with sqlite3.connect(graph_path) as connection:
        graph_sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE name = 'kdaf_graph_provenance'"
        ).fetchone()[0]
        graph_contents = " ".join(
            str(value)
            for row in connection.execute("SELECT * FROM kdaf_graph_provenance")
            for value in row
        )
    assert "amount" not in graph_sql.lower()
    assert "value" not in graph_sql.lower()
    assert "100000" not in graph_contents


def test_rejected_validation_is_timestamped_and_cannot_be_reopened(tmp_path) -> None:
    core = _core(tmp_path)
    source = core.register_source("Actuals", str(_write_csv(tmp_path)))
    item = core.enqueue_validation("source", source["id"])

    rejected = core.reject_validation(item["id"], "expert", "Untrusted source")

    assert rejected["status"] == "rejected"
    assert rejected["decided_at"] is not None
    with pytest.raises(KdafError) as exc_info:
        core.comment_validation(item["id"], "expert", "Try again")
    assert exc_info.value.code == "invalid_transition"


def test_failed_extraction_is_recorded_without_path_or_row_leakage(tmp_path) -> None:
    core = _core(tmp_path)
    secret_path = tmp_path / "password-do-not-leak.csv"
    source = core.register_source("Missing", str(secret_path))

    with pytest.raises(KdafError) as exc_info:
        core.extract_source(source["id"])

    assert exc_info.value.code == "source_file_not_found"
    assert "password-do-not-leak" not in exc_info.value.message
    attempts = core.list_extractions(source["id"])
    assert attempts[0]["status"] == "failed"
    assert attempts[0]["error_code"] == "source_file_not_found"
    assert "password-do-not-leak" not in attempts[0]["error_message"]


@pytest.mark.parametrize(
    ("contents", "message"),
    [
        ("", "CSV header is required"),
        ("account,amount\nRevenue\n", "does not match the header"),
        ("account,account\nRevenue,Sales\n", "headers must be unique"),
    ],
)
def test_malformed_csv_errors_are_clear(tmp_path, contents, message) -> None:
    path = tmp_path / "bad.csv"
    path.write_text(contents, encoding="utf-8")
    core = _core(tmp_path)
    source = core.register_source("Bad CSV", str(path))

    with pytest.raises(KdafError, match=message) as exc_info:
        core.extract_source(source["id"])
    assert exc_info.value.code == "invalid_csv"


def test_cli_and_tool_server_share_the_v04_workflow(tmp_path) -> None:
    metadata, dwh, graph = _stores(tmp_path)
    csv_path = _write_csv(tmp_path)
    common = [
        "--metadata-store",
        str(metadata),
        "--dwh-store",
        str(dwh),
        "--graph-store",
        str(graph),
    ]
    output = StringIO()
    assert cli_main([*common, "source", "register", "Actuals", str(csv_path)], stdout=output) == 0
    source = json.loads(output.getvalue())

    for command in (["source", "list"], ["source", "get", source["id"]]):
        command_output = StringIO()
        assert cli_main([*common, *command], stdout=command_output) == 0
        assert source["id"] in command_output.getvalue()

    core = _core(tmp_path)
    extracted_response = handle_message(
        {"tool": "source.extract", "arguments": {"id": source["id"]}}, core
    )
    assert extracted_response["ok"] is True
    batch_id = extracted_response["result"]["id"]

    extraction_output = StringIO()
    assert (
        cli_main(
            [*common, "source", "extractions", "--source-id", source["id"]],
            stdout=extraction_output,
        )
        == 0
    )
    assert json.loads(extraction_output.getvalue())[0]["id"] == batch_id

    validation_output = StringIO()
    assert (
        cli_main(
            [*common, "validation", "enqueue", "extraction", batch_id],
            stdout=validation_output,
        )
        == 0
    )
    validation = json.loads(validation_output.getvalue())

    for command in (
        ["validation", "list", "--status", "pending"],
        ["validation", "get", validation["id"]],
    ):
        command_output = StringIO()
        assert cli_main([*common, *command], stdout=command_output) == 0
        assert validation["id"] in command_output.getvalue()

    approved_response = handle_message(
        {
            "tool": "validation.approve",
            "arguments": {"id": validation["id"], "reviewer": "controller"},
        },
        core,
    )
    assert approved_response["ok"] is True
    assert approved_response["result"]["status"] == "approved"

    provenance_output = StringIO()
    assert cli_main([*common, "provenance", "get", batch_id], stdout=provenance_output) == 0
    assert json.loads(provenance_output.getvalue())["extraction"]["row_count"] == 2


def test_all_v04_tool_commands_have_valid_public_paths(tmp_path) -> None:
    core = _core(tmp_path)
    csv_path = _write_csv(tmp_path)

    def call(tool, arguments=None):
        response = handle_message({"tool": tool, "arguments": arguments or {}}, core)
        assert response["ok"] is True, response
        return response["result"]

    source = call(
        "source.register",
        {"name": "Actuals", "locator": str(csv_path), "metadata": {"owner": "FP&A"}},
    )
    assert call("source.list")[0]["id"] == source["id"]
    assert call("source.get", {"id": source["id"]})["name"] == "Actuals"
    extraction = call("source.extract", {"id": source["id"]})
    assert call("source.extractions", {"source_id": source["id"]})[0]["status"] == "completed"
    assert call("provenance.get", {"batch_id": extraction["id"]})["dwh"]["rows"]

    first = call(
        "validation.enqueue",
        {"subject_type": "extraction", "subject_id": extraction["id"]},
    )
    assert call("validation.list", {"status": "pending"})[0]["id"] == first["id"]
    assert call("validation.get", {"id": first["id"]})["status"] == "pending"
    changed = call(
        "validation.comment",
        {"id": first["id"], "reviewer": "expert", "comment": "Please revise"},
    )
    assert changed["status"] == "needs_changes"
    assert (
        call("validation.approve", {"id": first["id"], "reviewer": "expert"})["status"]
        == "approved"
    )

    second = call(
        "validation.enqueue",
        {"subject_type": "source", "subject_id": source["id"]},
    )
    assert (
        call(
            "validation.reject",
            {"id": second["id"], "reviewer": "expert", "comment": "Unsupported"},
        )["status"]
        == "rejected"
    )


def test_cli_missing_and_malformed_input_have_stable_errors(tmp_path) -> None:
    metadata, _, _ = _stores(tmp_path)
    missing_output = StringIO()
    missing_exit = cli_main(
        ["--metadata-store", str(metadata), "source", "register"],
        stdout=missing_output,
    )
    malformed_output = StringIO()
    malformed_exit = cli_main(
        [
            "--metadata-store",
            str(metadata),
            "source",
            "register",
            "Actuals",
            "actuals.csv",
            "--metadata-json",
            "[not-an-object]",
        ],
        stdout=malformed_output,
    )

    assert missing_exit == 2
    assert json.loads(missing_output.getvalue())["error"]["code"] == "invalid_arguments"
    assert malformed_exit == 2
    assert json.loads(malformed_output.getvalue()) == {
        "ok": False,
        "error": {"code": "invalid_input", "message": "metadata-json must be valid JSON"},
    }


@pytest.mark.parametrize(
    "command",
    [
        ["source", "get", "missing-source"],
        ["source", "extract", "missing-source"],
        ["source", "extractions", "--source-id", "missing-source"],
        ["provenance", "get", "missing-batch"],
        ["validation", "get", "missing-validation"],
        ["validation", "approve", "missing-validation", "--reviewer", "expert"],
        ["validation", "reject", "missing-validation", "--reviewer", "expert"],
        [
            "validation",
            "comment",
            "missing-validation",
            "--reviewer",
            "expert",
            "--comment",
            "revise",
        ],
    ],
)
def test_cli_v04_invalid_ids_have_stable_not_found_shape(tmp_path, command) -> None:
    output = StringIO()
    exit_code = cli_main(
        ["--metadata-store", str(tmp_path / "metadata.sqlite3"), *command],
        stdout=output,
    )

    assert exit_code == 2
    response = json.loads(output.getvalue())
    assert response["error"]["code"] == "not_found"
    assert set(response["error"]) == {"code", "message"}


@pytest.mark.parametrize(
    ("message", "code"),
    [
        ({"tool": "source.register", "arguments": {"locator": "x.csv"}}, "missing_argument"),
        (
            {
                "tool": "source.register",
                "arguments": {"name": "x", "locator": "x.csv", "metadata": []},
            },
            "invalid_input",
        ),
        ({"tool": "source.get", "arguments": {"id": "missing"}}, "not_found"),
        ({"tool": "source.extract", "arguments": {"id": "missing"}}, "not_found"),
        (
            {"tool": "source.extractions", "arguments": {"source_id": "missing"}},
            "not_found",
        ),
        ({"tool": "provenance.get", "arguments": {"batch_id": "missing"}}, "not_found"),
        (
            {
                "tool": "validation.enqueue",
                "arguments": {"subject_type": "source", "subject_id": "missing"},
            },
            "not_found",
        ),
        ({"tool": "validation.get", "arguments": {"id": "missing"}}, "not_found"),
        (
            {"tool": "validation.approve", "arguments": {"id": "missing"}},
            "missing_argument",
        ),
        (
            {
                "tool": "validation.approve",
                "arguments": {"id": "missing", "reviewer": "expert", "comment": []},
            },
            "not_found",
        ),
        (
            {
                "tool": "validation.reject",
                "arguments": {"id": "missing", "reviewer": "expert"},
            },
            "not_found",
        ),
        (
            {
                "tool": "validation.comment",
                "arguments": {"id": "missing", "reviewer": "expert"},
            },
            "missing_argument",
        ),
        (
            {"tool": "validation.list", "arguments": {"status": "unknown"}},
            "invalid_status",
        ),
    ],
)
def test_tool_server_v04_negative_paths_are_machine_readable(tmp_path, message, code) -> None:
    response = handle_message(message, _core(tmp_path))

    assert response["ok"] is False
    assert response["error"]["code"] == code
    assert set(response["error"]) == {"code", "message"}


def test_tool_server_survives_bad_v04_request_and_handles_the_next_line(tmp_path) -> None:
    core = _core(tmp_path)
    stdin = StringIO(
        '{"tool":"source.register","arguments":{"name":"x","locator":"x","metadata":[]}}\n'
        '{"tool":"health","arguments":{}}\n'
    )
    stdout = StringIO()

    serve(core, stdin, stdout)

    responses = [json.loads(line) for line in stdout.getvalue().splitlines()]
    assert responses[0]["error"]["code"] == "invalid_input"
    assert responses[1]["ok"] is True


def test_tool_server_rejects_malformed_optional_review_comment(tmp_path) -> None:
    core = _core(tmp_path)
    source = core.register_source("Actuals", str(_write_csv(tmp_path)))
    item = core.enqueue_validation("source", source["id"])

    response = handle_message(
        {
            "tool": "validation.approve",
            "arguments": {"id": item["id"], "reviewer": "expert", "comment": []},
        },
        core,
    )

    assert response["error"]["code"] == "invalid_input"


def test_unexpected_tool_failure_is_generic_and_does_not_leak(monkeypatch, tmp_path) -> None:
    core = _core(tmp_path)

    def fail(*args, **kwargs):
        raise RuntimeError("password=super-secret /private/config.toml")

    monkeypatch.setattr(core, "register_source", fail)
    response = handle_message(
        {"tool": "source.register", "arguments": {"name": "x", "locator": "x"}},
        core,
    )

    serialized = json.dumps(response)
    assert response["error"]["code"] == "internal_error"
    assert "super-secret" not in serialized
    assert "config.toml" not in serialized
