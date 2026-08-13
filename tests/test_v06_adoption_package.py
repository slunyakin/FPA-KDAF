from __future__ import annotations

import re
import tomllib
from pathlib import Path

import kdaf

ADOPTION_DOCS = (
    Path("docs/quickstart-v0.6.md"),
    Path("docs/architecture-v0.6.md"),
    Path("docs/adoption-v0.6.md"),
    Path("docs/releases/v0.6.0.md"),
)


def test_v06_package_version_is_aligned() -> None:
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert project["project"]["version"] == "0.6.0"
    assert kdaf.__version__ == "0.6.0"


def test_adoption_documents_have_no_broken_local_links() -> None:
    for document in ADOPTION_DOCS:
        content = document.read_text(encoding="utf-8")
        for target in re.findall(r"\[[^]]+\]\(([^)]+)\)", content):
            if target.startswith(("http://", "https://", "#")):
                continue
            path = target.split("#", 1)[0]
            assert (document.parent / path).resolve().exists(), (document, target)


def test_quickstart_is_fresh_clone_complete_and_points_to_evidence() -> None:
    quickstart = Path("docs/quickstart-v0.6.md").read_text(encoding="utf-8")

    for command in (
        "git clone https://github.com/slunyakin/FPA-KDAF.git",
        "python3 -m venv .venv",
        'python -m pip install -e ".[dev]"',
        "pytest -m smoke",
        "python scripts/run_public_demo.py",
        "--offline-graph",
    ):
        assert command in quickstart
    for evidence_link in (
        "public-demo-v0.6.md",
        "fpna-benchmark-v0.6.md",
        "release-readiness-v0.6.md",
        "architecture-v0.6.md",
    ):
        assert evidence_link in quickstart


def test_release_notes_state_capabilities_architecture_and_limitations() -> None:
    notes = Path("docs/releases/v0.6.0.md").read_text(encoding="utf-8")

    for required in (
        "## Capabilities",
        "## Architecture guarantees",
        "Financial numbers are not stored in Neo4j",
        "## Limitations",
        "not as a production deployment template",
        "## Validation baseline",
        "## Upgrade notes",
    ):
        assert required in notes


def test_readme_links_complete_v06_adoption_surface() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")

    for path in (
        "docs/quickstart-v0.6.md",
        "docs/adoption-v0.6.md",
        "docs/public-demo-v0.6.md",
        "docs/fpna-benchmark-v0.6.md",
        "docs/release-readiness-v0.6.md",
        "docs/releases/v0.6.0.md",
    ):
        assert path in readme
