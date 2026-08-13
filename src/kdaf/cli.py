"""Human/operator CLI for KDAF."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, TextIO

from kdaf.core import KdafCore, KdafError


class SafeArgumentParser(argparse.ArgumentParser):
    """Route parser failures through the CLI's stable JSON error envelope."""

    def error(self, message: str) -> None:
        raise KdafError(f"Invalid command: {message}", code="invalid_arguments")


def build_parser() -> argparse.ArgumentParser:
    parser = SafeArgumentParser(prog="kdaf", description="KDAF operator CLI")
    parser.add_argument("--config", type=Path, help="Path to a KDAF TOML config file")
    parser.add_argument("--metadata-store", type=Path, help="Path to the local metadata SQLite DB")
    parser.add_argument("--dwh-store", type=Path, help="Path to the local extraction DWH adapter")
    parser.add_argument("--graph-store", type=Path, help="Path to the local graph adapter")

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("health", help="Return local runtime health")
    subparsers.add_parser("config", help="Return a non-secret config summary")

    project = subparsers.add_parser("project", help="Manage project metadata")
    project_subparsers = project.add_subparsers(dest="project_command", required=True)

    project_create = project_subparsers.add_parser("create", help="Create a project")
    project_create.add_argument("name")
    project_create.add_argument("--description", default="")

    project_subparsers.add_parser("list", help="List projects")

    project_get = project_subparsers.add_parser("get", help="Read one project")
    project_get.add_argument("id")

    run = subparsers.add_parser("run", help="Manage run metadata")
    run_subparsers = run.add_subparsers(dest="run_command", required=True)

    run_create = run_subparsers.add_parser("create", help="Create a run")
    run_create.add_argument("project_id")
    run_create.add_argument("--status", default="created")

    run_list = run_subparsers.add_parser("list", help="List runs")
    run_list.add_argument("--project-id")

    run_get = run_subparsers.add_parser("get", help="Read one run")
    run_get.add_argument("id")

    question = subparsers.add_parser("competency-question", help="Manage competency questions")
    question_subparsers = question.add_subparsers(dest="question_command", required=True)

    question_create = question_subparsers.add_parser(
        "create",
        help="Create a competency question for a project",
    )
    question_create.add_argument("project_id")
    question_create.add_argument("question_text")
    question_create.add_argument("--business-context", default="")

    question_list = question_subparsers.add_parser("list", help="List competency questions")
    question_list.add_argument("--project-id")

    question_get = question_subparsers.add_parser("get", help="Read one competency question")
    question_get.add_argument("id")

    mvg = subparsers.add_parser("mvg", help="Manage minimum viable graph artifacts")
    mvg_subparsers = mvg.add_subparsers(dest="mvg_command", required=True)

    mvg_create = mvg_subparsers.add_parser("create", help="Create an MVG artifact")
    mvg_create.add_argument("project_id")
    mvg_create.add_argument("name")
    mvg_create.add_argument("--description", default="")
    mvg_create.add_argument("--question-id", action="append", default=[])
    mvg_create.add_argument("--concept-id", action="append", default=[])

    mvg_list = mvg_subparsers.add_parser("list", help="List MVG artifacts")
    mvg_list.add_argument("--project-id")

    mvg_get = mvg_subparsers.add_parser("get", help="Read one MVG artifact")
    mvg_get.add_argument("id")

    mvg_add_question = mvg_subparsers.add_parser(
        "add-question",
        help="Attach a source competency question to an MVG artifact",
    )
    mvg_add_question.add_argument("mvg_id")
    mvg_add_question.add_argument("question_id")

    mvg_add_concept = mvg_subparsers.add_parser(
        "add-concept",
        help="Attach an initial graph concept ID to an MVG artifact",
    )
    mvg_add_concept.add_argument("mvg_id")
    mvg_add_concept.add_argument("concept_id")

    starter_dwh = subparsers.add_parser("starter-dwh", help="Manage the FP&A starter DWH")
    starter_dwh_subparsers = starter_dwh.add_subparsers(
        dest="starter_dwh_command",
        required=True,
    )

    starter_dwh_subparsers.add_parser("schema", help="Print starter DWH Postgres SQL artifacts")

    starter_dwh_load = starter_dwh_subparsers.add_parser(
        "load",
        help="Load starter FP&A dimensions and facts into the local DWH store",
    )
    starter_dwh_load.add_argument("--dwh-store", type=Path)

    starter_dwh_facts = starter_dwh_subparsers.add_parser(
        "facts",
        help="Run sample starter DWH queries",
    )
    starter_dwh_facts.add_argument("--dwh-store", type=Path)

    starter_graph = subparsers.add_parser("starter-graph", help="Manage the FP&A starter graph")
    starter_graph_subparsers = starter_graph.add_subparsers(
        dest="starter_graph_command",
        required=True,
    )

    starter_graph_subparsers.add_parser("schema", help="Print starter graph Cypher artifacts")
    starter_graph_subparsers.add_parser("load", help="Load starter FP&A concepts into Neo4j")
    starter_graph_subparsers.add_parser("inspect", help="Inspect starter graph concept links")

    starter_questions = subparsers.add_parser(
        "starter-questions",
        help="Manage the FP&A starter question catalog",
    )
    starter_questions_subparsers = starter_questions.add_subparsers(
        dest="starter_questions_command",
        required=True,
    )
    starter_questions_subparsers.add_parser("catalog", help="Print starter FP&A questions")

    starter_questions_load = starter_questions_subparsers.add_parser(
        "load",
        help="Load starter questions and MVG artifacts into project metadata",
    )
    starter_questions_load.add_argument("project_id")

    starter_kit = subparsers.add_parser("starter-kit", help="Manage the full FP&A starter kit")
    starter_kit_subparsers = starter_kit.add_subparsers(
        dest="starter_kit_command",
        required=True,
    )

    starter_kit_load = starter_kit_subparsers.add_parser(
        "load",
        help="Load starter DWH, graph, questions, and MVG artifacts",
    )
    starter_kit_load.add_argument("project_id")
    starter_kit_load.add_argument("--dwh-store", type=Path)
    starter_kit_load.add_argument(
        "--skip-graph",
        action="store_true",
        help="Skip Neo4j graph loading for offline or test environments",
    )

    source = subparsers.add_parser("source", help="Register and extract structured sources")
    source_subparsers = source.add_subparsers(dest="source_command", required=True)

    source_register = source_subparsers.add_parser("register", help="Register a CSV source")
    source_register.add_argument("name")
    source_register.add_argument("locator")
    source_register.add_argument("--type", default="csv", dest="source_type")
    source_register.add_argument("--metadata-json", default="{}")
    source_subparsers.add_parser("list", help="List registered sources")
    source_get = source_subparsers.add_parser("get", help="Read a registered source")
    source_get.add_argument("id")
    source_extract = source_subparsers.add_parser("extract", help="Extract a registered source")
    source_extract.add_argument("id")
    source_extractions = source_subparsers.add_parser(
        "extractions", help="List extraction attempts"
    )
    source_extractions.add_argument("--source-id")

    provenance = subparsers.add_parser("provenance", help="Trace extraction provenance")
    provenance_subparsers = provenance.add_subparsers(dest="provenance_command", required=True)
    provenance_get = provenance_subparsers.add_parser("get", help="Trace an extraction batch")
    provenance_get.add_argument("batch_id")

    validation = subparsers.add_parser("validation", help="Manage expert validation")
    validation_subparsers = validation.add_subparsers(dest="validation_command", required=True)
    validation_enqueue = validation_subparsers.add_parser("enqueue")
    validation_enqueue.add_argument("subject_type")
    validation_enqueue.add_argument("subject_id")
    validation_enqueue.add_argument("--payload-json", default="{}")
    validation_list = validation_subparsers.add_parser("list")
    validation_list.add_argument("--status")
    validation_get = validation_subparsers.add_parser("get")
    validation_get.add_argument("id")
    for action in ("approve", "reject", "comment"):
        action_parser = validation_subparsers.add_parser(action)
        action_parser.add_argument("id")
        action_parser.add_argument("--reviewer", required=True)
        action_parser.add_argument("--comment", required=action == "comment", default="")

    dwh = subparsers.add_parser("dwh", help="Run controlled read-only DWH queries")
    dwh_subparsers = dwh.add_subparsers(dest="dwh_command", required=True)
    dwh_query = dwh_subparsers.add_parser("query", help="Execute an allow-listed DWH query")
    dwh_query.add_argument("query_id")
    dwh_query.add_argument("--parameters-json", default="{}")

    carp = subparsers.add_parser("carp", help="Retrieve context-aware graph relevance")
    carp_subparsers = carp.add_subparsers(dest="carp_command", required=True)
    carp_retrieve = carp_subparsers.add_parser("retrieve")
    carp_retrieve.add_argument("question_id")
    carp_retrieve.add_argument("--offline-graph", action="store_true")

    evidence = subparsers.add_parser("evidence", help="Build auditable evidence packets")
    evidence_subparsers = evidence.add_subparsers(dest="evidence_command", required=True)
    evidence_build = evidence_subparsers.add_parser("build")
    evidence_build.add_argument("question_id")
    evidence_build.add_argument("run_id")
    evidence_build.add_argument("--offline-graph", action="store_true")

    answer = subparsers.add_parser("answer", help="Generate answers from evidence packets")
    answer_subparsers = answer.add_subparsers(dest="answer_command", required=True)
    answer_generate = answer_subparsers.add_parser("generate")
    answer_generate.add_argument("evidence_file", type=Path)
    answer_generate.add_argument(
        "--provider",
        choices=("deterministic", "ollama", "openai-compatible"),
        default="deterministic",
    )
    answer_generate.add_argument("--model", default="kdaf-grounded-demo")
    answer_generate.add_argument("--parameters-json", default="{}")
    answer_generate.add_argument("--claim")
    answer_generate.add_argument("--base-url")
    answer_generate.add_argument("--api-key")

    demo = subparsers.add_parser("grounded-demo", help="Run the v0.5 grounded answer slice")
    demo.add_argument("question_id")
    demo.add_argument("run_id")
    demo.add_argument("--offline-graph", action="store_true")

    evaluation = subparsers.add_parser("eval", help="Run and inspect FP&A evaluations")
    evaluation_subparsers = evaluation.add_subparsers(dest="eval_command", required=True)
    evaluation_run = evaluation_subparsers.add_parser("run", help="Evaluate starter questions")
    evaluation_run.add_argument("project_id")
    evaluation_run.add_argument("--question-id", action="append")
    evaluation_run.add_argument("--offline-graph", action="store_true")
    evaluation_list = evaluation_subparsers.add_parser("list", help="List evaluation results")
    evaluation_list.add_argument("--run-id")
    evaluation_get = evaluation_subparsers.add_parser("get", help="Read an evaluation result")
    evaluation_get.add_argument("id")

    return parser


def main(argv: list[str] | None = None, stdout: TextIO | None = None) -> int:
    output = sys.stdout if stdout is None else stdout
    parser = build_parser()

    try:
        args = parser.parse_args(argv)
        result = _dispatch(args)
    except KdafError as exc:
        _write_json({"ok": False, "error": {"code": exc.code, "message": exc.message}}, output)
        return 2

    _write_json(result, output)
    return 0


def _dispatch(args: argparse.Namespace) -> Any:
    core = KdafCore(
        config_path=args.config,
        metadata_store_path=args.metadata_store,
        dwh_store_path=args.dwh_store,
        graph_store_path=args.graph_store,
    )

    if args.command == "health":
        return core.health()
    if args.command == "config":
        return core.config_summary()
    if args.command == "project":
        return _dispatch_project(core, args)
    if args.command == "run":
        return _dispatch_run(core, args)
    if args.command == "competency-question":
        return _dispatch_competency_question(core, args)
    if args.command == "mvg":
        return _dispatch_mvg(core, args)
    if args.command == "starter-dwh":
        return _dispatch_starter_dwh(core, args)
    if args.command == "starter-graph":
        return _dispatch_starter_graph(core, args)
    if args.command == "starter-questions":
        return _dispatch_starter_questions(core, args)
    if args.command == "starter-kit":
        return _dispatch_starter_kit(core, args)
    if args.command == "source":
        return _dispatch_source(core, args)
    if args.command == "provenance":
        return core.get_provenance(args.batch_id)
    if args.command == "validation":
        return _dispatch_validation(core, args)
    if args.command == "dwh":
        return core.query_dwh(
            args.query_id,
            _parse_json_object(args.parameters_json, "parameters-json"),
            dwh_store_path=args.dwh_store,
        )
    if args.command == "carp":
        return core.retrieve_carp_context(args.question_id, offline_graph=args.offline_graph)
    if args.command == "evidence":
        return core.build_evidence_packet(
            args.question_id,
            args.run_id,
            dwh_store_path=args.dwh_store,
            offline_graph=args.offline_graph,
        )
    if args.command == "answer":
        return core.generate_grounded_answer(
            _read_json_object(args.evidence_file, "evidence packet"),
            provider_name=args.provider,
            model=args.model,
            parameters=_parse_json_object(args.parameters_json, "parameters-json"),
            requested_claim=args.claim,
            base_url=args.base_url,
            api_key=args.api_key,
        )
    if args.command == "grounded-demo":
        return core.grounded_answer_demo(
            args.question_id,
            args.run_id,
            dwh_store_path=args.dwh_store,
            offline_graph=args.offline_graph,
        )
    if args.command == "eval":
        if args.eval_command == "run":
            return core.run_evaluation(
                args.project_id,
                question_ids=args.question_id,
                dwh_store_path=args.dwh_store,
                offline_graph=args.offline_graph,
            )
        if args.eval_command == "list":
            return core.list_evaluation_results(args.run_id)
        if args.eval_command == "get":
            return core.get_evaluation_result(args.id)
        raise KdafError(f"Unknown eval command: {args.eval_command}")
    raise KdafError(f"Unknown command: {args.command}")


def _dispatch_project(core: KdafCore, args: argparse.Namespace) -> Any:
    if args.project_command == "create":
        return core.create_project(name=args.name, description=args.description)
    if args.project_command == "list":
        return core.list_projects()
    if args.project_command == "get":
        return core.get_project(args.id)
    raise KdafError(f"Unknown project command: {args.project_command}")


def _dispatch_run(core: KdafCore, args: argparse.Namespace) -> Any:
    if args.run_command == "create":
        return core.create_run(project_id=args.project_id, status=args.status)
    if args.run_command == "list":
        return core.list_runs(project_id=args.project_id)
    if args.run_command == "get":
        return core.get_run(args.id)
    raise KdafError(f"Unknown run command: {args.run_command}")


def _dispatch_competency_question(core: KdafCore, args: argparse.Namespace) -> Any:
    if args.question_command == "create":
        return core.create_competency_question(
            project_id=args.project_id,
            question_text=args.question_text,
            business_context=args.business_context,
        )
    if args.question_command == "list":
        return core.list_competency_questions(project_id=args.project_id)
    if args.question_command == "get":
        return core.get_competency_question(args.id)
    raise KdafError(f"Unknown competency question command: {args.question_command}")


def _dispatch_mvg(core: KdafCore, args: argparse.Namespace) -> Any:
    if args.mvg_command == "create":
        return core.create_mvg_artifact(
            project_id=args.project_id,
            name=args.name,
            description=args.description,
            question_ids=args.question_id,
            concept_ids=args.concept_id,
        )
    if args.mvg_command == "list":
        return core.list_mvg_artifacts(project_id=args.project_id)
    if args.mvg_command == "get":
        return core.get_mvg_artifact(args.id)
    if args.mvg_command == "add-question":
        return core.add_question_to_mvg(args.mvg_id, args.question_id)
    if args.mvg_command == "add-concept":
        return core.add_concept_to_mvg(args.mvg_id, args.concept_id)
    raise KdafError(f"Unknown MVG command: {args.mvg_command}")


def _dispatch_starter_dwh(core: KdafCore, args: argparse.Namespace) -> Any:
    if args.starter_dwh_command == "schema":
        return core.starter_dwh_schema()
    if args.starter_dwh_command == "load":
        return core.load_starter_dwh(dwh_store_path=args.dwh_store)
    if args.starter_dwh_command == "facts":
        return core.starter_dwh_sample_facts(dwh_store_path=args.dwh_store)
    raise KdafError(f"Unknown starter DWH command: {args.starter_dwh_command}")


def _dispatch_starter_graph(core: KdafCore, args: argparse.Namespace) -> Any:
    if args.starter_graph_command == "schema":
        return core.starter_graph_schema()
    if args.starter_graph_command == "load":
        return core.load_starter_graph()
    if args.starter_graph_command == "inspect":
        return core.starter_graph_context()
    raise KdafError(f"Unknown starter graph command: {args.starter_graph_command}")


def _dispatch_starter_questions(core: KdafCore, args: argparse.Namespace) -> Any:
    if args.starter_questions_command == "catalog":
        return core.starter_question_catalog()
    if args.starter_questions_command == "load":
        return core.load_starter_questions(project_id=args.project_id)
    raise KdafError(f"Unknown starter questions command: {args.starter_questions_command}")


def _dispatch_starter_kit(core: KdafCore, args: argparse.Namespace) -> Any:
    if args.starter_kit_command == "load":
        return core.load_starter_kit(
            project_id=args.project_id,
            dwh_store_path=args.dwh_store,
            include_graph=not args.skip_graph,
        )
    raise KdafError(f"Unknown starter kit command: {args.starter_kit_command}")


def _dispatch_source(core: KdafCore, args: argparse.Namespace) -> Any:
    if args.source_command == "register":
        return core.register_source(
            args.name,
            args.locator,
            args.source_type,
            _parse_json_object(args.metadata_json, "metadata-json"),
        )
    if args.source_command == "list":
        return core.list_sources()
    if args.source_command == "get":
        return core.get_source(args.id)
    if args.source_command == "extract":
        return core.extract_source(args.id)
    if args.source_command == "extractions":
        return core.list_extractions(args.source_id)
    raise KdafError(f"Unknown source command: {args.source_command}")


def _dispatch_validation(core: KdafCore, args: argparse.Namespace) -> Any:
    if args.validation_command == "enqueue":
        return core.enqueue_validation(
            args.subject_type,
            args.subject_id,
            _parse_json_object(args.payload_json, "payload-json"),
        )
    if args.validation_command == "list":
        return core.list_validations(args.status)
    if args.validation_command == "get":
        return core.get_validation(args.id)
    if args.validation_command == "approve":
        return core.approve_validation(args.id, args.reviewer, args.comment)
    if args.validation_command == "reject":
        return core.reject_validation(args.id, args.reviewer, args.comment)
    if args.validation_command == "comment":
        return core.comment_validation(args.id, args.reviewer, args.comment)
    raise KdafError(f"Unknown validation command: {args.validation_command}")


def _parse_json_object(raw: str, option: str) -> dict[str, Any]:
    try:
        result = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise KdafError(f"{option} must be valid JSON", code="invalid_input") from exc
    if not isinstance(result, dict):
        raise KdafError(f"{option} must be a JSON object", code="invalid_input")
    return result


def _read_json_object(path: Path, option: str) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise KdafError(f"{option} file could not be read", code="not_found") from exc
    return _parse_json_object(raw, option)


def _write_json(payload: Any, output: TextIO) -> None:
    output.write(json.dumps(payload, sort_keys=True))
    output.write("\n")


if __name__ == "__main__":
    raise SystemExit(main())
