from pathlib import Path


def test_release_readiness_report_publishes_required_evidence() -> None:
    report = Path("docs/release-readiness-v0.6.md").read_text(encoding="utf-8")

    for required in (
        "## Readiness checklist",
        "Static foundation smoke",
        "Optional live Docker smoke",
        "## Benchmark baseline",
        "Variance",
        "Unsupported claim",
        "## Architecture coverage",
        "Neo4j semantic graph",
        "Postgres metadata DB role",
        "Separate Postgres DWH role",
        "No financial facts in Neo4j",
        "## Supported workflows",
        "## Unsupported areas and known limitations",
        "## Next-release roadmap",
        "No v0.7 milestone or committed scope exists",
    ):
        assert required in report


def test_readme_links_release_readiness_evidence() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")

    assert "docs/release-readiness-v0.6.md" in readme
