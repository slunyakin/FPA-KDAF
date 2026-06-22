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
    } <= repository.table_names()
