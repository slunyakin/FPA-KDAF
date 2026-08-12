from __future__ import annotations

import pytest

from kdaf.metadata import MetadataRepository
from kdaf.starter_questions import load_starter_question_catalog, starter_question_catalog


def test_starter_question_catalog_contains_required_fpna_families() -> None:
    catalog = starter_question_catalog()

    assert catalog.schema_version == 1
    assert catalog.catalog_id == "starter_question_catalog:fpna_v1"
    assert {
        "budget_vs_actuals",
        "forecast_movement",
        "department_spend",
        "revenue_driver",
        "variance",
    } <= {question.category for question in catalog.questions}

    for question in catalog.questions:
        assert question.question_text
        assert question.business_context
        assert question.expected_data_dependencies
        assert question.expected_graph_concepts


def test_starter_question_loader_creates_competency_questions_and_mvg_artifacts(tmp_path) -> None:
    repository = MetadataRepository(tmp_path / "metadata.sqlite3")
    repository.initialize_schema()
    project = repository.create_project("Quarterly FP&A")

    summary = load_starter_question_catalog(repository, project.id)
    questions = repository.list_competency_questions(project_id=project.id)
    artifacts = repository.list_mvg_artifacts(project_id=project.id)

    assert summary.schema_version == 1
    assert summary.project_id == project.id
    assert summary.question_count == 5
    assert summary.mvg_count == 5
    assert summary.created_question_count == 5
    assert summary.created_mvg_count == 5
    assert len(questions) == 5
    assert len(artifacts) == 5
    assert {question.id for question in questions} == set(summary.competency_question_ids)
    assert {artifact.id for artifact in artifacts} == set(summary.mvg_artifact_ids)
    assert any("metric:budget_vs_actuals" in artifact.concept_ids for artifact in artifacts)


def test_starter_question_loader_is_idempotent_for_project(tmp_path) -> None:
    repository = MetadataRepository(tmp_path / "metadata.sqlite3")
    repository.initialize_schema()
    project = repository.create_project("Quarterly FP&A")

    first_summary = load_starter_question_catalog(repository, project.id)
    second_summary = load_starter_question_catalog(repository, project.id)

    assert first_summary.competency_question_ids == second_summary.competency_question_ids
    assert first_summary.mvg_artifact_ids == second_summary.mvg_artifact_ids
    assert second_summary.created_question_count == 0
    assert second_summary.created_mvg_count == 0
    assert len(repository.list_competency_questions(project_id=project.id)) == 5
    assert len(repository.list_mvg_artifacts(project_id=project.id)) == 5


def test_starter_question_loader_requires_existing_project(tmp_path) -> None:
    repository = MetadataRepository(tmp_path / "metadata.sqlite3")
    repository.initialize_schema()

    with pytest.raises(ValueError, match="Project not found"):
        load_starter_question_catalog(repository, "missing-project")
