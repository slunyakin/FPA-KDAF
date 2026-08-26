#!/usr/bin/env python3
"""Exercise the installed KDAF artifact outside the source-tree import path."""

from __future__ import annotations

import importlib.metadata
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import kdaf


def _command(name: str) -> str:
    scripts_dir = Path(sys.prefix) / ("Scripts" if sys.platform == "win32" else "bin")
    candidate = scripts_dir / name
    if not candidate.is_file():
        candidate = candidate.with_suffix(".exe")
    if not candidate.is_file():
        raise RuntimeError(f"Installed console command is unavailable: {name}")
    return str(candidate)


def _run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    process = subprocess.run(
        command,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if process.returncode != 0:
        raise RuntimeError(
            f"Command failed ({process.returncode}): {' '.join(command)}\n"
            f"stdout: {process.stdout}\nstderr: {process.stderr}"
        )
    return process


def _run_expected_error(command: list[str], cwd: Path, code: str, extra: str) -> None:
    process = subprocess.run(
        command,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if process.returncode != 2:
        raise RuntimeError(
            f"Command did not return the stable error status: {' '.join(command)}\n"
            f"stdout: {process.stdout}\nstderr: {process.stderr}"
        )
    payload = json.loads(process.stdout)
    error = payload.get("error", {})
    if error.get("code") != code or extra not in error.get("message", ""):
        raise RuntimeError(f"Unexpected optional-extra error: {payload}")
    serialized = json.dumps(payload)
    if "kdaf_metadata_password" in serialized or "kdaf_dwh_password" in serialized:
        raise RuntimeError("Optional-extra error leaked default credentials")


def main() -> int:
    installed_version = importlib.metadata.version("kdaf")
    if installed_version != kdaf.__version__:
        raise RuntimeError(
            f"Installed metadata version {installed_version!r} does not match "
            f"kdaf.__version__ {kdaf.__version__!r}"
        )

    if len(kdaf.starter_question_catalog().questions) != 5:
        raise RuntimeError("Packaged starter question catalog is unavailable")
    if "CREATE TABLE" not in kdaf.starter_dwh_sql_artifacts()["schema"]:
        raise RuntimeError("Packaged starter DWH schema is unavailable")
    if "SemanticConcept" not in kdaf.starter_graph_cypher_artifacts()["seed"]:
        raise RuntimeError("Packaged starter graph seed is unavailable")

    kdaf_command = _command("kdaf")
    tool_server_command = _command("kdaf-tool-server")
    with tempfile.TemporaryDirectory(prefix="kdaf-installed-smoke-") as temp_dir:
        workdir = Path(temp_dir)
        _run([kdaf_command, "--help"], workdir)
        _run([tool_server_command, "--help"], workdir)
        health = json.loads(_run([kdaf_command, "health"], workdir).stdout)
        result = json.loads(
            _run(
                [
                    kdaf_command,
                    "public-demo",
                    "Installed Artifact Smoke",
                    "--offline-graph",
                ],
                workdir,
            ).stdout
        )

        if health != {"service": "kdaf", "status": "ok", "version": installed_version}:
            raise RuntimeError(f"Unexpected health result: {health}")
        if result["answer"]["status"] != "grounded" or not result["answer"]["citations"]:
            raise RuntimeError("Installed public demo did not produce a cited grounded answer")
        if result["unsupported_claim"]["status"] != "insufficiently_supported":
            raise RuntimeError("Installed public demo did not refuse the unsupported claim")
        if result["evaluation_result"]["status"] != "passed":
            raise RuntimeError("Installed public demo evaluation did not pass")
        expected_files = {"metadata.sqlite3", "starter_dwh.sqlite3"}
        actual_files = {path.name for path in (workdir / ".kdaf").glob("*.sqlite3")}
        if not expected_files.issubset(actual_files):
            raise RuntimeError(f"Installed public demo local stores are incomplete: {actual_files}")
        _run_expected_error(
            [kdaf_command, "dwh", "query", "budget_vs_actuals"],
            workdir,
            "dwh_unavailable",
            "kdaf[postgres]",
        )
        _run_expected_error(
            [kdaf_command, "starter-graph", "load"],
            workdir,
            "starter_graph_error",
            "kdaf[neo4j]",
        )

    print(json.dumps({"name": "kdaf", "status": "passed", "version": installed_version}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
