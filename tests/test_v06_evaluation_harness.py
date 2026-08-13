from __future__ import annotations

import json
from io import StringIO

import pytest

from kdaf.cli import main as cli_main
from kdaf.core import KdafCore, KdafError
from kdaf.tool_server import handle_message, serve


def _workspace(tmp_path):
    metadata = tmp_path / "metadata.sqlite3"
    dwh = tmp_path / "financial_dwh.sqlite3"
    graph = tmp_path / "graph.sqlite3"
    core = KdafCore(
        metadata_store_path=metadata,
        dwh_store_path=dwh,
        graph_store_path=graph,
    )
    project = core.create_project("v0.6 evaluation")
    core.load_starter_dwh(dwh)
    core.load_starter_questions(project["id"])
    return core, metadata, dwh, graph, project


def test_eval_runs_starter_questions_and_persists_metrics(tmp_path) -> None:
    core, _, dwh, _, project = _workspace(tmp_path)

    evaluation = core.run_evaluation(
        project["id"], dwh_store_path=dwh, offline_graph=True
    )

    assert evaluation["status"] == "passed"
    assert evaluation["summary"] == {"total": 5, "passed": 5, "failed": 0}
    assert all(result["metrics"]["answer_citations_valid"] for result in evaluation["results"])
    assert all(
        result["metrics"]["unsupported_claim_refused"] for result in evaluation["results"]
    )
    stored = core.list_evaluation_results(evaluation["run"]["id"])
    assert stored == evaluation["results"]
    assert core.get_evaluation_result(stored[0]["id"]) == stored[0]


def test_eval_records_case_failure_without_aborting_run(tmp_path, monkeypatch) -> None:
    core, _, dwh, _, project = _workspace(tmp_path)
    questions = core.list_competency_questions(project["id"])
    original = core.build_evidence_packet

    def fail_one(question_id, *args, **kwargs):
        if question_id == questions[0]["id"]:
            raise KdafError("Synthetic retrieval failure", "retrieval_failed")
        return original(question_id, *args, **kwargs)

    monkeypatch.setattr(core, "build_evidence_packet", fail_one)
    evaluation = core.run_evaluation(
        project["id"], dwh_store_path=dwh, offline_graph=True
    )

    assert evaluation["status"] == "failed"
    assert evaluation["summary"] == {"total": 5, "passed": 4, "failed": 1}
    failed = next(result for result in evaluation["results"] if result["status"] == "error")
    assert failed["error"] == {
        "code": "retrieval_failed",
        "message": "Synthetic retrieval failure",
    }


@pytest.mark.parametrize("project_id", ["", "missing-project"])
def test_eval_rejects_missing_or_invalid_project(project_id, tmp_path) -> None:
    core, _, dwh, _, _ = _workspace(tmp_path)

    with pytest.raises(KdafError) as exc_info:
        core.run_evaluation(project_id, dwh_store_path=dwh, offline_graph=True)

    assert exc_info.value.code in {"missing_field", "not_found"}


def test_eval_rejects_malformed_question_ids_and_not_found_question(tmp_path) -> None:
    core, _, dwh, _, project = _workspace(tmp_path)

    with pytest.raises(KdafError) as malformed:
        core.run_evaluation(
            project["id"], question_ids=[123], dwh_store_path=dwh  # type: ignore[list-item]
        )
    with pytest.raises(KdafError) as missing:
        core.run_evaluation(
            project["id"], question_ids=["missing"], dwh_store_path=dwh
        )

    assert malformed.value.code == "invalid_input"
    assert missing.value.code == "not_found"


def test_eval_cli_public_entrypoint_valid_and_negative_paths(tmp_path) -> None:
    core, metadata, dwh, graph, project = _workspace(tmp_path)
    question_id = core.list_competency_questions(project["id"])[0]["id"]
    common = [
        "--metadata-store",
        str(metadata),
        "--dwh-store",
        str(dwh),
        "--graph-store",
        str(graph),
    ]
    output = StringIO()

    code = cli_main(
        common
        + ["eval", "run", project["id"], "--question-id", question_id, "--offline-graph"],
        output,
    )
    payload = json.loads(output.getvalue())

    assert code == 0
    assert payload["summary"] == {"total": 1, "passed": 1, "failed": 0}

    output = StringIO()
    code = cli_main(common + ["eval", "get", "missing"], output)
    assert code == 2
    assert json.loads(output.getvalue()) == {
        "ok": False,
        "error": {"code": "not_found", "message": "Evaluation result not found: missing"},
    }


def test_eval_tool_server_public_entrypoint_and_survives_bad_requests(tmp_path) -> None:
    core, _, dwh, _, project = _workspace(tmp_path)
    question_id = core.list_competency_questions(project["id"])[0]["id"]
    valid = handle_message(
        {
            "tool": "eval.run",
            "arguments": {
                "project_id": project["id"],
                "question_ids": [question_id],
                "dwh_store_path": str(dwh),
                "offline_graph": True,
            },
        },
        core,
    )
    malformed = handle_message(
        {"tool": "eval.run", "arguments": {"project_id": project["id"], "question_ids": "x"}},
        core,
    )
    missing = handle_message({"tool": "eval.run", "arguments": {}}, core)
    not_found = handle_message(
        {"tool": "eval.get", "arguments": {"id": "missing"}}, core
    )

    assert valid["ok"] is True
    assert malformed["error"]["code"] == "invalid_argument"
    assert missing["error"]["code"] == "missing_argument"
    assert not_found["error"]["code"] == "not_found"

    output = StringIO()
    serve(
        core,
        StringIO('{bad json}\n{"tool":"eval.list","arguments":{}}\n'),
        output,
    )
    responses = [json.loads(line) for line in output.getvalue().splitlines()]
    assert responses[0]["error"]["code"] == "invalid_json"
    assert responses[1]["ok"] is True
    assert "secret" not in output.getvalue().lower()
