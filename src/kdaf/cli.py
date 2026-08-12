"""Human/operator CLI for KDAF v0.2."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, TextIO

from kdaf.core import KdafCore, KdafError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kdaf", description="KDAF operator CLI")
    parser.add_argument("--config", type=Path, help="Path to a KDAF TOML config file")
    parser.add_argument("--metadata-store", type=Path, help="Path to the local metadata SQLite DB")

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

    return parser


def main(argv: list[str] | None = None, stdout: TextIO | None = None) -> int:
    output = sys.stdout if stdout is None else stdout
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        result = _dispatch(args)
    except KdafError as exc:
        _write_json({"ok": False, "error": {"code": exc.code, "message": exc.message}}, output)
        return 2

    _write_json(result, output)
    return 0


def _dispatch(args: argparse.Namespace) -> Any:
    core = KdafCore(config_path=args.config, metadata_store_path=args.metadata_store)

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


def _write_json(payload: Any, output: TextIO) -> None:
    output.write(json.dumps(payload, sort_keys=True))
    output.write("\n")


if __name__ == "__main__":
    raise SystemExit(main())
