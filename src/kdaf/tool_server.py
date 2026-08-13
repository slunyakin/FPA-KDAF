"""MCP-style JSON-line tool server for KDAF."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, TextIO

from kdaf.core import KdafCore, KdafError

TOOL_NAMES = (
    "health",
    "config",
    "project.create",
    "project.list",
    "project.get",
    "run.create",
    "run.list",
    "run.get",
    "competency_question.create",
    "competency_question.list",
    "competency_question.get",
    "mvg.create",
    "mvg.list",
    "mvg.get",
    "mvg.add_question",
    "mvg.add_concept",
    "starter_dwh.schema",
    "starter_dwh.load",
    "starter_dwh.facts",
    "starter_graph.schema",
    "starter_graph.load",
    "starter_graph.inspect",
    "starter_questions.catalog",
    "starter_questions.load",
    "starter_kit.load",
    "source.register",
    "source.list",
    "source.get",
    "source.extract",
    "source.extractions",
    "provenance.get",
    "validation.enqueue",
    "validation.list",
    "validation.get",
    "validation.approve",
    "validation.reject",
    "validation.comment",
    "dwh.query",
    "carp.retrieve",
    "evidence.build",
    "answer.generate",
    "grounded_answer.demo",
    "eval.run",
    "eval.list",
    "eval.get",
    "eval.catalog",
    "eval.benchmark",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kdaf-tool-server",
        description="KDAF MCP-style JSON-line tool server",
    )
    parser.add_argument("--config", type=Path, help="Path to a KDAF TOML config file")
    parser.add_argument("--metadata-store", type=Path, help="Path to the local metadata SQLite DB")
    parser.add_argument("--dwh-store", type=Path, help="Path to the local extraction DWH adapter")
    parser.add_argument("--graph-store", type=Path, help="Path to the local graph adapter")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    core = KdafCore(
        config_path=args.config,
        metadata_store_path=args.metadata_store,
        dwh_store_path=args.dwh_store,
        graph_store_path=args.graph_store,
    )
    serve(core=core, stdin=sys.stdin, stdout=sys.stdout)
    return 0


def serve(core: KdafCore, stdin: TextIO, stdout: TextIO) -> None:
    for line in stdin:
        if not line.strip():
            continue
        response = handle_json_line(line, core)
        stdout.write(json.dumps(response, sort_keys=True))
        stdout.write("\n")
        stdout.flush()


def handle_json_line(line: str, core: KdafCore) -> dict[str, Any]:
    try:
        message = json.loads(line)
    except json.JSONDecodeError as exc:
        return _error_response("invalid_json", f"Malformed JSON: {exc.msg}")

    if not isinstance(message, dict):
        return _error_response("invalid_request", "Tool request must be a JSON object")
    return handle_message(message, core)


def handle_message(message: dict[str, Any], core: KdafCore) -> dict[str, Any]:
    try:
        if message.get("method") == "tools/list" or message.get("tool") == "tools.list":
            return {"ok": True, "result": list_tools()}

        tool_name, arguments = _extract_call(message)
        result = call_tool(tool_name, arguments, core)
        return {"ok": True, "result": result}
    except KdafError as exc:
        return _error_response(exc.code, exc.message)
    except Exception:
        # Keep the long-running server alive and never return config, paths, or stack traces.
        return _error_response("internal_error", "The tool request could not be completed")


def list_tools() -> list[dict[str, str]]:
    return [{"name": name} for name in TOOL_NAMES]


def call_tool(tool_name: str, arguments: dict[str, Any] | None, core: KdafCore) -> Any:
    args = {} if arguments is None else arguments
    if not isinstance(args, dict):
        raise KdafError("Tool arguments must be a JSON object", code="invalid_arguments")
    if not isinstance(tool_name, str) or not tool_name.strip():
        raise KdafError("Missing required tool name", code="missing_tool")

    if tool_name == "health":
        return core.health()
    if tool_name == "config":
        return core.config_summary()
    if tool_name == "project.create":
        return core.create_project(
            name=_required_arg(args, "name"),
            description=args.get("description", ""),
        )
    if tool_name == "project.list":
        return core.list_projects()
    if tool_name == "project.get":
        return core.get_project(_required_arg(args, "id"))
    if tool_name == "run.create":
        return core.create_run(
            project_id=_required_arg(args, "project_id"),
            status=args.get("status", "created"),
        )
    if tool_name == "run.list":
        return core.list_runs(project_id=args.get("project_id"))
    if tool_name == "run.get":
        return core.get_run(_required_arg(args, "id"))
    if tool_name == "competency_question.create":
        return core.create_competency_question(
            project_id=_required_arg(args, "project_id"),
            question_text=_required_arg(args, "question_text"),
            business_context=args.get("business_context", ""),
        )
    if tool_name == "competency_question.list":
        return core.list_competency_questions(project_id=args.get("project_id"))
    if tool_name == "competency_question.get":
        return core.get_competency_question(_required_arg(args, "id"))
    if tool_name == "mvg.create":
        return core.create_mvg_artifact(
            project_id=_required_arg(args, "project_id"),
            name=_required_arg(args, "name"),
            description=args.get("description", ""),
            question_ids=_optional_string_list_arg(args, "question_ids"),
            concept_ids=_optional_string_list_arg(args, "concept_ids"),
        )
    if tool_name == "mvg.list":
        return core.list_mvg_artifacts(project_id=args.get("project_id"))
    if tool_name == "mvg.get":
        return core.get_mvg_artifact(_required_arg(args, "id"))
    if tool_name == "mvg.add_question":
        return core.add_question_to_mvg(
            mvg_id=_required_arg(args, "mvg_id"),
            question_id=_required_arg(args, "question_id"),
        )
    if tool_name == "mvg.add_concept":
        return core.add_concept_to_mvg(
            mvg_id=_required_arg(args, "mvg_id"),
            concept_id=_required_arg(args, "concept_id"),
        )
    if tool_name == "starter_dwh.schema":
        return core.starter_dwh_schema()
    if tool_name == "starter_dwh.load":
        return core.load_starter_dwh(dwh_store_path=args.get("dwh_store_path"))
    if tool_name == "starter_dwh.facts":
        return core.starter_dwh_sample_facts(dwh_store_path=args.get("dwh_store_path"))
    if tool_name == "starter_graph.schema":
        return core.starter_graph_schema()
    if tool_name == "starter_graph.load":
        return core.load_starter_graph()
    if tool_name == "starter_graph.inspect":
        return core.starter_graph_context()
    if tool_name == "starter_questions.catalog":
        return core.starter_question_catalog()
    if tool_name == "starter_questions.load":
        return core.load_starter_questions(project_id=_required_arg(args, "project_id"))
    if tool_name == "starter_kit.load":
        return core.load_starter_kit(
            project_id=_required_arg(args, "project_id"),
            dwh_store_path=args.get("dwh_store_path"),
            include_graph=_optional_bool_arg(args, "include_graph", default=True),
        )
    if tool_name == "source.register":
        return core.register_source(
            name=_required_arg(args, "name"),
            locator=_required_arg(args, "locator"),
            source_type=args.get("source_type", "csv"),
            metadata=args.get("metadata", {}),
        )
    if tool_name == "source.list":
        return core.list_sources()
    if tool_name == "source.get":
        return core.get_source(_required_arg(args, "id"))
    if tool_name == "source.extract":
        return core.extract_source(_required_arg(args, "id"))
    if tool_name == "source.extractions":
        return core.list_extractions(args.get("source_id"))
    if tool_name == "provenance.get":
        return core.get_provenance(_required_arg(args, "batch_id"))
    if tool_name == "validation.enqueue":
        return core.enqueue_validation(
            _required_arg(args, "subject_type"),
            _required_arg(args, "subject_id"),
            args.get("payload", {}),
        )
    if tool_name == "validation.list":
        return core.list_validations(args.get("status"))
    if tool_name == "validation.get":
        return core.get_validation(_required_arg(args, "id"))
    if tool_name == "validation.approve":
        return core.approve_validation(
            _required_arg(args, "id"),
            _required_arg(args, "reviewer"),
            args.get("comment", ""),
        )
    if tool_name == "validation.reject":
        return core.reject_validation(
            _required_arg(args, "id"),
            _required_arg(args, "reviewer"),
            args.get("comment", ""),
        )
    if tool_name == "validation.comment":
        return core.comment_validation(
            _required_arg(args, "id"),
            _required_arg(args, "reviewer"),
            _required_arg(args, "comment"),
        )
    if tool_name == "dwh.query":
        return core.query_dwh(
            _required_arg(args, "query_id"),
            _optional_object_arg(args, "parameters"),
            dwh_store_path=_optional_string_arg(args, "dwh_store_path"),
        )
    if tool_name == "carp.retrieve":
        return core.retrieve_carp_context(
            _required_arg(args, "question_id"),
            offline_graph=_optional_bool_arg(args, "offline_graph", default=False),
        )
    if tool_name == "evidence.build":
        return core.build_evidence_packet(
            _required_arg(args, "question_id"),
            _required_arg(args, "run_id"),
            dwh_store_path=_optional_string_arg(args, "dwh_store_path"),
            offline_graph=_optional_bool_arg(args, "offline_graph", default=False),
        )
    if tool_name == "answer.generate":
        return core.generate_grounded_answer(
            _required_object_arg(args, "evidence_packet"),
            provider_name=_optional_string_arg(args, "provider") or "deterministic",
            model=_optional_string_arg(args, "model") or "kdaf-grounded-demo",
            parameters=_optional_object_arg(args, "parameters"),
            requested_claim=_optional_string_arg(args, "claim"),
            base_url=_optional_string_arg(args, "base_url"),
            api_key=_optional_string_arg(args, "api_key"),
        )
    if tool_name == "grounded_answer.demo":
        return core.grounded_answer_demo(
            _required_arg(args, "question_id"),
            _required_arg(args, "run_id"),
            dwh_store_path=_optional_string_arg(args, "dwh_store_path"),
            offline_graph=_optional_bool_arg(args, "offline_graph", default=False),
        )
    if tool_name == "eval.run":
        return core.run_evaluation(
            _required_arg(args, "project_id"),
            question_ids=(
                _optional_string_list_arg(args, "question_ids")
                if "question_ids" in args
                else None
            ),
            dwh_store_path=_optional_string_arg(args, "dwh_store_path"),
            offline_graph=_optional_bool_arg(args, "offline_graph", default=False),
        )
    if tool_name == "eval.list":
        return core.list_evaluation_results(_optional_string_arg(args, "run_id"))
    if tool_name == "eval.get":
        return core.get_evaluation_result(_required_arg(args, "id"))
    if tool_name == "eval.catalog":
        return core.fpna_benchmark_catalog()
    if tool_name == "eval.benchmark":
        return core.run_fpna_benchmark(
            _required_arg(args, "project_id"),
            case_ids=(
                _optional_string_list_arg(args, "case_ids") if "case_ids" in args else None
            ),
            dwh_store_path=_optional_string_arg(args, "dwh_store_path"),
            offline_graph=_optional_bool_arg(args, "offline_graph", default=False),
        )
    raise KdafError(f"Unknown tool: {tool_name}", code="unknown_tool")


def _extract_call(message: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    if message.get("method") == "tools/call":
        params = message.get("params")
        if not isinstance(params, dict):
            raise KdafError("Missing tools/call params object", code="invalid_request")
        if "name" not in params:
            raise KdafError("Missing required tool name", code="missing_tool")
        return params["name"], params.get("arguments", {})

    if "tool" not in message:
        raise KdafError("Missing required tool name", code="missing_tool")
    return message["tool"], message.get("arguments", {})


def _required_arg(arguments: dict[str, Any], name: str) -> str:
    value = arguments.get(name)
    if not isinstance(value, str) or not value.strip():
        raise KdafError(f"Missing required argument: {name}", code="missing_argument")
    return value


def _optional_string_list_arg(arguments: dict[str, Any], name: str) -> list[str]:
    value = arguments.get(name, [])
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise KdafError(f"Argument must be a list of strings: {name}", code="invalid_argument")
    return value


def _optional_bool_arg(arguments: dict[str, Any], name: str, default: bool) -> bool:
    value = arguments.get(name, default)
    if not isinstance(value, bool):
        raise KdafError(f"Argument must be a boolean: {name}", code="invalid_argument")
    return value


def _required_object_arg(arguments: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in arguments:
        raise KdafError(f"Missing required argument: {name}", code="missing_argument")
    value = arguments[name]
    if not isinstance(value, dict):
        raise KdafError(f"Argument must be an object: {name}", code="invalid_argument")
    return value


def _optional_object_arg(arguments: dict[str, Any], name: str) -> dict[str, Any]:
    value = arguments.get(name, {})
    if not isinstance(value, dict):
        raise KdafError(f"Argument must be an object: {name}", code="invalid_argument")
    return value


def _optional_string_arg(arguments: dict[str, Any], name: str) -> str | None:
    value = arguments.get(name)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise KdafError(f"Argument must be a non-empty string: {name}", code="invalid_argument")
    return value.strip()


def _error_response(code: str, message: str) -> dict[str, Any]:
    return {"ok": False, "error": {"code": code, "message": message}}


if __name__ == "__main__":
    raise SystemExit(main())
