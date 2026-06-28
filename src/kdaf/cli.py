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


def _write_json(payload: Any, output: TextIO) -> None:
    output.write(json.dumps(payload, sort_keys=True))
    output.write("\n")


if __name__ == "__main__":
    raise SystemExit(main())
