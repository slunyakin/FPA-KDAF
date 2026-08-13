from __future__ import annotations

import json
from io import StringIO

import pytest

from kdaf.benchmark import fpna_benchmark_catalog
from kdaf.cli import main as cli_main
from kdaf.core import KdafCore, KdafError
from kdaf.tool_server import handle_message


def _workspace(tmp_path):
    metadata = tmp_path / "metadata.sqlite3"
    dwh = tmp_path / "financial_dwh.sqlite3"
    graph = tmp_path / "graph.sqlite3"
    core = KdafCore(
        metadata_store_path=metadata,
        dwh_store_path=dwh,
        graph_store_path=graph,
    )
    project = core.create_project("v0.6 benchmark")
    core.load_starter_dwh(dwh)
    core.load_starter_questions(project["id"])
    return core, metadata, dwh, graph, project


def test_public_benchmark_fixture_covers_required_fpna_cases() -> None:
    catalog = fpna_benchmark_catalog()
    case_ids = {case.id for case in catalog.cases}

    assert catalog.benchmark_id == "kdaf:fpna_benchmark:v1"
    assert case_ids == {
        "fpna:variance",
        "fpna:budget_vs_actuals",
        "fpna:forecast",
        "fpna:department_spend",
        "fpna:revenue_driver",
        "fpna:provenance_heavy",
        "fpna:unsupported_claim_refusal",
    }
    assert all(case.expected_evidence["provenance"] for case in catalog.cases)


def test_eval_harness_runs_public_benchmark_and_persists_baseline(tmp_path) -> None:
    core, _, dwh, _, project = _workspace(tmp_path)

    result = core.run_fpna_benchmark(
        project["id"], dwh_store_path=dwh, offline_graph=True
    )

    assert result["status"] == "passed"
    assert result["summary"] == {"total": 7, "passed": 7, "failed": 0}
    assert all(case["metrics"]["passed"] for case in result["results"])
    refusal = next(
        case for case in result["results"] if case["case_id"].endswith("refusal")
    )
    assert refusal["details"]["answer_status"] == "insufficiently_supported"
    assert core.list_evaluation_results(result["run"]["id"]) == result["results"]


def test_benchmark_case_error_is_machine_readable_and_does_not_abort(tmp_path, monkeypatch) -> None:
    core, _, dwh, _, project = _workspace(tmp_path)
    original = core.build_evidence_packet
    calls = 0

    def fail_first(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise KdafError("Synthetic case failure", "benchmark_case_failed")
        return original(*args, **kwargs)

    monkeypatch.setattr(core, "build_evidence_packet", fail_first)
    result = core.run_fpna_benchmark(
        project["id"], dwh_store_path=dwh, offline_graph=True
    )

    assert result["summary"] == {"total": 7, "passed": 6, "failed": 1}
    assert result["results"][0]["error"] == {
        "code": "benchmark_case_failed",
        "message": "Synthetic case failure",
    }


@pytest.mark.parametrize(
    ("case_ids", "code"),
    [([123], "invalid_input"), (["missing"], "not_found"), ([], "missing_field")],
)
def test_benchmark_rejects_malformed_missing_and_invalid_case_ids(
    case_ids, code, tmp_path
) -> None:
    core, _, dwh, _, project = _workspace(tmp_path)

    with pytest.raises(KdafError) as exc_info:
        core.run_fpna_benchmark(
            project["id"], case_ids=case_ids, dwh_store_path=dwh, offline_graph=True
        )

    assert exc_info.value.code == code


def test_benchmark_rejects_invalid_project_id(tmp_path) -> None:
    core, _, dwh, _, _ = _workspace(tmp_path)

    with pytest.raises(KdafError) as exc_info:
        core.run_fpna_benchmark("missing", dwh_store_path=dwh, offline_graph=True)

    assert exc_info.value.code == "not_found"


def test_benchmark_cli_runs_through_public_entrypoint(tmp_path) -> None:
    _, metadata, dwh, graph, project = _workspace(tmp_path)
    output = StringIO()
    code = cli_main(
        [
            "--metadata-store",
            str(metadata),
            "--dwh-store",
            str(dwh),
            "--graph-store",
            str(graph),
            "eval",
            "benchmark",
            project["id"],
            "--case-id",
            "fpna:unsupported_claim_refusal",
            "--offline-graph",
        ],
        output,
    )

    assert code == 0
    assert json.loads(output.getvalue())["summary"] == {
        "total": 1,
        "passed": 1,
        "failed": 0,
    }


def test_benchmark_tool_server_valid_and_negative_paths(tmp_path) -> None:
    core, _, dwh, _, project = _workspace(tmp_path)
    valid = handle_message(
        {
            "tool": "eval.benchmark",
            "arguments": {
                "project_id": project["id"],
                "case_ids": ["fpna:variance"],
                "dwh_store_path": str(dwh),
                "offline_graph": True,
            },
        },
        core,
    )
    malformed = handle_message(
        {
            "tool": "eval.benchmark",
            "arguments": {"project_id": project["id"], "case_ids": "fpna:variance"},
        },
        core,
    )
    missing = handle_message({"tool": "eval.benchmark", "arguments": {}}, core)
    invalid = handle_message(
        {
            "tool": "eval.benchmark",
            "arguments": {"project_id": project["id"], "case_ids": ["missing"]},
        },
        core,
    )

    assert valid["ok"] is True
    assert malformed["error"]["code"] == "invalid_argument"
    assert missing["error"]["code"] == "missing_argument"
    assert invalid["error"]["code"] == "not_found"
    assert "secret" not in json.dumps([valid, malformed, missing, invalid]).lower()
