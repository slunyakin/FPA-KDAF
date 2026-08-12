#!/usr/bin/env python3
"""Run the KDAF FP&A starter-kit vertical slice and print JSON evidence."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kdaf.core import KdafError  # noqa: E402
from kdaf.starter_kit_demo import run_starter_kit_demo  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the KDAF FP&A starter-kit demo")
    parser.add_argument("--config", type=Path, help="Path to a KDAF TOML config file")
    parser.add_argument("--metadata-store", type=Path, help="Path to the local metadata SQLite DB")
    parser.add_argument("--dwh-store", type=Path, help="Path to the local starter DWH SQLite DB")
    parser.add_argument("--project-name", default="FP&A Starter Kit Demo")
    parser.add_argument(
        "--skip-graph",
        action="store_true",
        help="Skip Neo4j graph loading and inspection",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = run_starter_kit_demo(
            project_name=args.project_name,
            config_path=args.config,
            metadata_store_path=args.metadata_store,
            dwh_store_path=args.dwh_store,
            include_graph=not args.skip_graph,
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
