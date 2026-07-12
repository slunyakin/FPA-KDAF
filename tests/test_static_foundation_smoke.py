from __future__ import annotations

from pathlib import Path

import pytest

import kdaf


@pytest.mark.smoke
def test_static_foundation_smoke_loads_without_docker() -> None:
    config = kdaf.load_config(Path("config/kdaf.example.toml"))

    assert kdaf.package_metadata().name == "kdaf"
    assert config.runtime.environment
    assert config.metadata_db.database == "kdaf_metadata"
    assert config.dwh_db.database == "kdaf_financial_dwh"
    assert config.neo4j.uri.startswith("bolt://")


@pytest.mark.smoke
def test_static_docker_compose_structure() -> None:
    compose = Path("docker-compose.yml").read_text(encoding="utf-8")

    for service in ("neo4j:", "metadata-db:", "financial-dwh:"):
        assert service in compose

    assert compose.count("healthcheck:") == 3
    assert "metadata_db_data:" in compose
    assert "financial_dwh_data:" in compose
    assert "neo4j_data:" in compose
    assert "kdaf_metadata" in compose
    assert "kdaf_financial_dwh" in compose


@pytest.mark.smoke
def test_readme_documents_v02_public_commands() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")

    assert "v0.2" in readme
    assert "kdaf --metadata-store .kdaf/v02-demo.sqlite3 health" in readme
    assert "kdaf --metadata-store .kdaf/v02-demo.sqlite3 project create" in readme
    assert "kdaf-tool-server --metadata-store .kdaf/v02-demo.sqlite3" in readme
    assert '"tool":"health"' in readme
