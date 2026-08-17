from pathlib import Path

STAGES = (
    "Problem-Centric Scoping",
    "Ontology Bootstrapping",
    "Schema-Guided Knowledge Extraction",
    "Contextual Knowledge Representation",
    "Hybrid Knowledge Validation",
    "Context-Aware Relevance Propagation",
)


def test_six_stage_approach_explains_problem_method_and_implementation() -> None:
    guide = Path("docs/six-stage-approach.md").read_text(encoding="utf-8")

    assert "why evidence matters" in guide
    assert "treating auditability as a property of the full knowledge-building" in guide
    assert "```mermaid" in guide
    assert "How the public framework implements the approach" in guide
    assert "generalized schema-guided LLM extraction" in guide
    assert "Partial" in guide
    assert "A practical variance-analysis example" in guide
    for stage in STAGES:
        assert stage in guide


def test_public_adoption_docs_link_the_six_stage_approach() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    architecture = Path("docs/architecture-v0.6.md").read_text(encoding="utf-8")
    adoption = Path("docs/adoption-v0.6.md").read_text(encoding="utf-8")
    quickstart = Path("docs/quickstart-v0.6.md").read_text(encoding="utf-8")

    assert "## Why the Framework Is Needed" in readme
    assert "docs/six-stage-approach.md" in readme
    assert "```mermaid" in readme
    for document in (architecture, adoption, quickstart):
        assert "six-stage-approach.md" in document
