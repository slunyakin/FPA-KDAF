from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from kdaf.starter_kit_demo import run_starter_kit_demo


def test_starter_kit_demo_returns_vertical_slice_evidence_without_graph(tmp_path) -> None:
    result = run_starter_kit_demo(
        project_name="Offline FP&A Demo",
        metadata_store_path=tmp_path / "metadata.sqlite3",
        dwh_store_path=tmp_path / "starter_dwh.sqlite3",
        include_graph=False,
    )

    assert result["project"]["name"] == "Offline FP&A Demo"
    assert result["starter_kit"]["status"] == "loaded"
    assert result["starter_kit"]["dwh"]["row_counts"]["fpna_facts"] == 24
    assert result["starter_kit"]["graph"]["skipped"] is True
    assert result["dwh_sample_facts"]["budget_vs_actuals"][0]["variance_amount"] == 5000
    assert len(result["starter_questions"]) == 5
    assert len(result["mvg_artifacts"]) == 5
    assert any(
        "metric:budget_vs_actuals" in artifact["concept_ids"]
        for artifact in result["mvg_artifacts"]
    )
    assert result["graph_context"]["skipped"] is True


def test_documented_starter_kit_demo_script_command_passes_without_graph(tmp_path) -> None:
    process = subprocess.run(
        [
            sys.executable,
            "scripts/run_starter_kit_demo.py",
            "--metadata-store",
            str(tmp_path / "metadata.sqlite3"),
            "--dwh-store",
            str(tmp_path / "starter_dwh.sqlite3"),
            "--project-name",
            "Script FP&A Demo",
            "--skip-graph",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert process.returncode == 0, process.stderr
    payload = json.loads(process.stdout)
    result = payload["result"]

    assert payload["ok"] is True
    assert result["project"]["name"] == "Script FP&A Demo"
    assert result["starter_kit"]["dwh"]["row_counts"]["fpna_facts"] == 24
    assert result["starter_kit"]["questions"]["question_count"] == 5
    assert len(result["starter_questions"]) == 5
    assert len(result["mvg_artifacts"]) == 5


@pytest.mark.integration
def test_starter_kit_demo_queries_real_graph_when_docker_is_available(tmp_path) -> None:
    pytest.importorskip("neo4j")
    docker = shutil.which("docker")
    if docker is None:
        pytest.skip("Docker CLI is not available")

    info = subprocess.run([docker, "info"], check=False, capture_output=True, text=True, timeout=30)
    if info.returncode != 0:
        pytest.skip("Docker daemon is not available")

    compose_file = Path("docker-compose.yml")
    up = subprocess.run(
        [docker, "compose", "-f", str(compose_file), "up", "-d", "--wait", "neo4j"],
        check=False,
        capture_output=True,
        text=True,
        timeout=180,
    )
    if up.returncode != 0:
        pytest.fail(f"docker compose up neo4j failed:\nSTDOUT:\n{up.stdout}\nSTDERR:\n{up.stderr}")

    try:
        result = run_starter_kit_demo(
            project_name="Graph FP&A Demo",
            config_path=Path("config/kdaf.example.toml"),
            metadata_store_path=tmp_path / "metadata.sqlite3",
            dwh_store_path=tmp_path / "starter_dwh.sqlite3",
            include_graph=True,
        )

        assert result["starter_kit"]["graph"]["concept_counts"]["MetricConcept"] == 5
        assert result["graph_context"]["metric_dependencies"][0]["metric_id"] == (
            "metric:budget_vs_actuals"
        )
        assert len(result["starter_questions"]) == 5
        assert len(result["mvg_artifacts"]) == 5
    finally:
        subprocess.run(
            [docker, "compose", "-f", str(compose_file), "down"],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
