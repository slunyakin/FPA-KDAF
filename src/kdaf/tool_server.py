"""MCP-style JSON-line tool server for KDAF v0.2."""

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
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kdaf-tool-server",
        description="KDAF MCP-style JSON-line tool server",
    )
    parser.add_argument("--config", type=Path, help="Path to a KDAF TOML config file")
    parser.add_argument("--metadata-store", type=Path, help="Path to the local metadata SQLite DB")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    core = KdafCore(config_path=args.config, metadata_store_path=args.metadata_store)
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


def _error_response(code: str, message: str) -> dict[str, Any]:
    return {"ok": False, "error": {"code": code, "message": message}}


if __name__ == "__main__":
    raise SystemExit(main())
