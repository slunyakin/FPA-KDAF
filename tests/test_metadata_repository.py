from __future__ import annotations

import pytest

from kdaf.metadata import MetadataError, MetadataRepository


def test_projects_can_be_created_listed_and_read(tmp_path) -> None:
    repository = MetadataRepository(tmp_path / "metadata.sqlite3")
    repository.initialize_schema()

    project = repository.create_project("Quarterly FP&A", description="Board workflow")

    assert repository.list_projects() == [project]
    assert repository.get_project(project.id) == project


def test_runs_can_be_created_listed_and_read(tmp_path) -> None:
    repository = MetadataRepository(tmp_path / "metadata.sqlite3")
    repository.initialize_schema()
    project = repository.create_project("Quarterly FP&A")

    run = repository.create_run(project.id, status="queued")

    assert repository.list_runs() == [run]
    assert repository.list_runs(project_id=project.id) == [run]
    assert repository.get_run(run.id) == run


def test_run_creation_requires_existing_project(tmp_path) -> None:
    repository = MetadataRepository(tmp_path / "metadata.sqlite3")
    repository.initialize_schema()

    with pytest.raises(MetadataError, match="Project not found"):
        repository.create_run("missing-project")


def test_competency_questions_can_be_created_listed_and_read(tmp_path) -> None:
    repository = MetadataRepository(tmp_path / "metadata.sqlite3")
    repository.initialize_schema()
    project = repository.create_project("Quarterly FP&A")

    question = repository.create_competency_question(
        project.id,
        "Where is actual spend over budget this quarter?",
        business_context="Monthly business review",
    )

    assert question.project_id == project.id
    assert question.question_text == "Where is actual spend over budget this quarter?"
    assert question.business_context == "Monthly business review"
    assert repository.list_competency_questions() == [question]
    assert repository.list_competency_questions(project_id=project.id) == [question]
    assert repository.get_competency_question(question.id) == question


def test_competency_question_creation_requires_existing_project(tmp_path) -> None:
    repository = MetadataRepository(tmp_path / "metadata.sqlite3")
    repository.initialize_schema()

    with pytest.raises(MetadataError, match="Project not found"):
        repository.create_competency_question(
            "missing-project",
            "Which departments are above budget?",
        )


def test_mvg_artifacts_track_source_questions_and_initial_concepts(tmp_path) -> None:
    repository = MetadataRepository(tmp_path / "metadata.sqlite3")
    repository.initialize_schema()
    project = repository.create_project("Quarterly FP&A")
    question = repository.create_competency_question(
        project.id,
        "Which departments are driving the forecast variance?",
    )

    artifact = repository.create_mvg_artifact(
        project.id,
        "Budget variance MVG",
        description="Initial graph scope for budget-to-actual variance questions",
        question_ids=[question.id],
        concept_ids=["metric:budget_variance", "department:sales"],
    )

    assert artifact.project_id == project.id
    assert artifact.question_ids == [question.id]
    assert artifact.concept_ids == ["department:sales", "metric:budget_variance"]
    assert repository.list_mvg_artifacts(project_id=project.id) == [artifact]
    assert repository.get_mvg_artifact(artifact.id) == artifact


def test_mvg_question_links_must_stay_inside_project(tmp_path) -> None:
    repository = MetadataRepository(tmp_path / "metadata.sqlite3")
    repository.initialize_schema()
    project = repository.create_project("Quarterly FP&A")
    other_project = repository.create_project("Other FP&A")
    question = repository.create_competency_question(
        other_project.id,
        "Which products are below margin plan?",
    )
    artifact = repository.create_mvg_artifact(project.id, "Budget variance MVG")

    with pytest.raises(MetadataError, match="same project"):
        repository.add_question_to_mvg(artifact.id, question.id)


def test_mvg_creation_with_invalid_question_does_not_leave_partial_artifact(tmp_path) -> None:
    repository = MetadataRepository(tmp_path / "metadata.sqlite3")
    repository.initialize_schema()
    project = repository.create_project("Quarterly FP&A")

    with pytest.raises(MetadataError, match="Competency question not found"):
        repository.create_mvg_artifact(
            project.id,
            "Budget variance MVG",
            question_ids=["missing-question"],
        )

    assert repository.list_mvg_artifacts(project_id=project.id) == []


def test_schema_contains_v02_extension_points(tmp_path) -> None:
    repository = MetadataRepository(tmp_path / "metadata.sqlite3")
    repository.initialize_schema()

    assert {
        "kdaf_schema_migrations",
        "kdaf_projects",
        "kdaf_runs",
        "kdaf_audit_log",
        "kdaf_source_registry",
        "kdaf_validation_queue",
        "kdaf_eval_results",
        "kdaf_competency_questions",
        "kdaf_mvg_artifacts",
        "kdaf_mvg_questions",
        "kdaf_mvg_concepts",
    } <= repository.table_names()
