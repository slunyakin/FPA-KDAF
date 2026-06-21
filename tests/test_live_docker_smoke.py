from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


def test_docker_compose_services_report_healthy_when_available() -> None:
    docker = shutil.which("docker")
    if docker is None:
        pytest.skip("Docker CLI is not available")

    info = subprocess.run([docker, "info"], check=False, capture_output=True, text=True, timeout=30)
    if info.returncode != 0:
        pytest.skip("Docker daemon is not available")

    compose = subprocess.run(
        [docker, "compose", "version"],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if compose.returncode != 0:
        pytest.skip("Docker Compose plugin is not available")

    compose_file = Path("docker-compose.yml")
    up = subprocess.run(
        [docker, "compose", "-f", str(compose_file), "up", "-d", "--wait"],
        check=False,
        capture_output=True,
        text=True,
        timeout=180,
    )
    if up.returncode != 0:
        pytest.fail(f"docker compose up failed:\nSTDOUT:\n{up.stdout}\nSTDERR:\n{up.stderr}")

    try:
        ps = subprocess.run(
            [docker, "compose", "-f", str(compose_file), "ps", "--format", "json"],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        services = _parse_compose_ps_json(ps.stdout)
        expected = {"neo4j", "metadata-db", "financial-dwh"}
        assert expected <= services.keys()
        for service_name in expected:
            assert services[service_name]["Health"] == "healthy"
    finally:
        subprocess.run(
            [docker, "compose", "-f", str(compose_file), "down"],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )


def _parse_compose_ps_json(output: str) -> dict[str, dict[str, str]]:
    stripped = output.strip()
    if stripped.startswith("["):
        rows = json.loads(stripped)
    else:
        rows = [json.loads(line) for line in output.splitlines() if line.strip()]
    return {row["Service"]: row for row in rows}
