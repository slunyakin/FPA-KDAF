#!/usr/bin/env python3
"""Run the KDAF v0.6 public demo and print stable JSON output."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kdaf.core import KdafCore, KdafError  # noqa: E402


class SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise KdafError(f"Invalid command: {message}", "invalid_arguments")


def build_parser() -> argparse.ArgumentParser:
    parser = SafeArgumentParser(description="Run the KDAF v0.6 public demo")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--metadata-store", type=Path)
    parser.add_argument("--dwh-store", type=Path)
    parser.add_argument("--graph-store", type=Path)
    parser.add_argument("--project-name", default="KDAF v0.6 Public Demo")
    parser.add_argument("--question-category", default="budget_vs_actuals")
    parser.add_argument("--offline-graph", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        core = KdafCore(
            config_path=args.config,
            metadata_store_path=args.metadata_store,
            dwh_store_path=args.dwh_store,
            graph_store_path=args.graph_store,
        )
        result = core.run_public_demo(
            args.project_name,
            question_category=args.question_category,
            dwh_store_path=args.dwh_store,
            offline_graph=args.offline_graph,
        )
    except KdafError as exc:
        print(
            json.dumps({"ok": False, "error": {"code": exc.code, "message": exc.message}}),
            flush=True,
        )
        return 2
    print(json.dumps({"ok": True, "result": result}, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
