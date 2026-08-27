from __future__ import annotations

import builtins
import hashlib
import re
import tomllib
from pathlib import Path

import pytest

import kdaf
from kdaf.retrieval import (
    Neo4jGraphContextProvider,
    PostgresDwhQueryService,
    RetrievalError,
)
from kdaf.starter_graph import (
    Neo4jConnectionSettings,
    StarterGraphError,
    StarterGraphRepository,
)

PROTECTED_README_SHA256 = "ac3a2e5bc7e4997647b871342b763b4870cfe421b0531e523ca9e45440842843"


def _project_config() -> dict:
    return tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))


def test_project_metadata_defines_offline_core_and_live_integration_extras() -> None:
    config = _project_config()
    project = config["project"]

    assert project["name"] == "kdaf"
    assert project["dynamic"] == ["version"]
    assert project["readme"] == "PYPI.md"
    assert project["requires-python"] == ">=3.11,<3.15"
    assert project["dependencies"] == []
    assert config["tool"]["hatch"]["version"]["path"] == "src/kdaf/_version.py"

    extras = project["optional-dependencies"]
    assert extras["neo4j"] == ["neo4j>=5.25,<6"]
    assert extras["postgres"] == ["psycopg[binary]>=3.2,<4"]
    assert set(extras["all"]) == set(extras["neo4j"] + extras["postgres"])
    assert set(extras["all"]).issubset(extras["dev"])


def test_distribution_boundaries_are_explicit_and_exclude_protected_material() -> None:
    config = _project_config()
    sdist = config["tool"]["hatch"]["build"]["targets"]["sdist"]
    wheel = config["tool"]["hatch"]["build"]["targets"]["wheel"]

    assert wheel["packages"] == ["src/kdaf"]
    assert set(sdist["include"]) == {
        "/LICENSE",
        "/PYPI.md",
        "/pyproject.toml",
        "/src/kdaf",
    }
    assert "/README.md" not in sdist["include"]
    assert any("AGENTS.md" in pattern for pattern in sdist["exclude"])
    assert any("carp-manuscript-guidance.md" in pattern for pattern in sdist["exclude"])


def test_dedicated_pypi_description_is_install_oriented_and_uses_stable_links() -> None:
    description = Path("PYPI.md").read_text(encoding="utf-8")
    normalized = " ".join(description.split())

    for expected in (
        "pip install kdaf",
        'kdaf public-demo "My FP&A Trial" --offline-graph',
        "from kdaf import KdafCore",
        "kdaf-tool-server",
        "kdaf[neo4j]",
        "kdaf[postgres]",
        "not a production deployment template",
    ):
        assert expected in normalized

    targets = re.findall(r"\[[^]]+\]\(([^)]+)\)", description)
    assert targets
    assert all(target.startswith(("https://", "#")) for target in targets)


def test_protected_readme_fingerprint_is_unchanged() -> None:
    digest = hashlib.sha256(Path("README.md").read_bytes()).hexdigest()

    assert digest == PROTECTED_README_SHA256


def test_public_version_has_one_source_of_truth() -> None:
    assert kdaf.__version__ == "0.6.0"
    assert kdaf.package_metadata().version == kdaf.__version__


def test_missing_postgres_extra_returns_actionable_sanitized_error(monkeypatch) -> None:
    original_import = builtins.__import__

    def import_without_psycopg(name, *args, **kwargs):
        if name == "psycopg":
            raise ImportError("missing for test")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", import_without_psycopg)
    service = PostgresDwhQueryService(
        host="secret-host",
        port=5432,
        database="finance",
        user="reader",
        password="secret-password",
    )

    with pytest.raises(RetrievalError) as exc_info:
        service.execute("budget_vs_actuals")

    assert exc_info.value.code == "dwh_unavailable"
    assert "kdaf[postgres]" in str(exc_info.value)
    assert "secret-host" not in str(exc_info.value)
    assert "secret-password" not in str(exc_info.value)


def test_missing_neo4j_extra_returns_actionable_sanitized_errors(monkeypatch) -> None:
    original_import = builtins.__import__

    def import_without_neo4j(name, *args, **kwargs):
        if name == "neo4j":
            raise ImportError("missing for test")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", import_without_neo4j)
    settings = Neo4jConnectionSettings(
        uri="bolt://secret-host:7687",
        user="neo4j",
        password="secret-password",
        database="neo4j",
    )

    with pytest.raises(RetrievalError) as retrieval:
        Neo4jGraphContextProvider(settings).retrieve([])
    with pytest.raises(StarterGraphError) as starter:
        StarterGraphRepository(settings).load_seed_data()

    for error in (retrieval.value, starter.value):
        assert "kdaf[neo4j]" in str(error)
        assert "secret-host" not in str(error)
        assert "secret-password" not in str(error)


def test_release_workflows_use_trusted_publishing_and_protected_environments() -> None:
    checks = Path(".github/workflows/package-checks.yml").read_text(encoding="utf-8")
    publish = Path(".github/workflows/publish.yml").read_text(encoding="utf-8")

    assert "pull_request:" in checks
    assert "3.11" in checks and "3.14" in checks
    assert "python -m build" in checks
    assert "twine check" in checks
    assert "scripts/verify_distribution.py" in checks
    assert "scripts/smoke_installed_package.py" in checks

    assert "workflow_dispatch:" in publish
    assert "release:" in publish
    assert "id-token: write" in publish
    assert "environment: testpypi" in publish
    assert "environment: pypi" in publish
    assert "pypa/gh-action-pypi-publish" in publish
    assert "download-artifact" in publish
    assert "--expected-tag" in publish
    assert "PYPI_API_TOKEN" not in publish
