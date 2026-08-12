"""Starter FP&A question catalog and metadata fixture loader."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from importlib import resources
from typing import Any

from kdaf.metadata import MetadataRepository

STARTER_QUESTION_CATALOG_VERSION = 1


@dataclass(frozen=True)
class StarterQuestion:
    id: str
    category: str
    question_text: str
    business_context: str
    expected_data_dependencies: list[str]
    expected_graph_concepts: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class StarterQuestionCatalog:
    schema_version: int
    catalog_id: str
    name: str
    description: str
    questions: list[StarterQuestion]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "catalog_id": self.catalog_id,
            "name": self.name,
            "description": self.description,
            "questions": [question.to_dict() for question in self.questions],
        }


@dataclass(frozen=True)
class StarterQuestionLoadSummary:
    schema_version: int
    catalog_id: str
    project_id: str
    question_count: int
    mvg_count: int
    created_question_count: int
    created_mvg_count: int
    competency_question_ids: list[str]
    mvg_artifact_ids: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class StarterQuestionCatalogError(ValueError):
    """Raised when the starter question catalog cannot be loaded."""


def starter_question_catalog() -> StarterQuestionCatalog:
    """Return the packaged FP&A starter question catalog."""

    root = resources.files("kdaf").joinpath("resources/starter_questions")
    payload = json.loads(root.joinpath("catalog.json").read_text(encoding="utf-8"))
    return _catalog_from_payload(payload)


def load_starter_question_catalog(
    repository: MetadataRepository,
    project_id: str,
) -> StarterQuestionLoadSummary:
    """Load starter catalog questions into project metadata and MVG artifacts."""

    project = repository.get_project(project_id)
    catalog = starter_question_catalog()
    existing_questions = repository.list_competency_questions(project_id=project.id)
    existing_mvg_artifacts = repository.list_mvg_artifacts(project_id=project.id)
    questions_by_text = {question.question_text: question for question in existing_questions}
    artifacts_by_name = {artifact.name: artifact for artifact in existing_mvg_artifacts}

    created_question_count = 0
    created_mvg_count = 0
    question_ids: list[str] = []
    mvg_ids: list[str] = []

    for catalog_question in catalog.questions:
        competency_question = questions_by_text.get(catalog_question.question_text)
        if competency_question is None:
            competency_question = repository.create_competency_question(
                project.id,
                catalog_question.question_text,
                business_context=catalog_question.business_context,
            )
            questions_by_text[competency_question.question_text] = competency_question
            created_question_count += 1

        mvg_name = f"{catalog_question.category.replace('_', ' ').title()} MVG"
        mvg_artifact = artifacts_by_name.get(mvg_name)
        if mvg_artifact is None:
            mvg_artifact = repository.create_mvg_artifact(
                project.id,
                mvg_name,
                description=f"Starter graph scope for {catalog_question.category} questions.",
                question_ids=[competency_question.id],
                concept_ids=catalog_question.expected_graph_concepts,
            )
            artifacts_by_name[mvg_artifact.name] = mvg_artifact
            created_mvg_count += 1
        else:
            mvg_artifact = repository.add_question_to_mvg(mvg_artifact.id, competency_question.id)
            for concept_id in catalog_question.expected_graph_concepts:
                mvg_artifact = repository.add_concept_to_mvg(mvg_artifact.id, concept_id)

        question_ids.append(competency_question.id)
        mvg_ids.append(mvg_artifact.id)

    return StarterQuestionLoadSummary(
        schema_version=catalog.schema_version,
        catalog_id=catalog.catalog_id,
        project_id=project.id,
        question_count=len(question_ids),
        mvg_count=len(mvg_ids),
        created_question_count=created_question_count,
        created_mvg_count=created_mvg_count,
        competency_question_ids=question_ids,
        mvg_artifact_ids=mvg_ids,
    )


def _catalog_from_payload(payload: dict[str, Any]) -> StarterQuestionCatalog:
    schema_version = _required_int(payload, "schema_version")
    if schema_version != STARTER_QUESTION_CATALOG_VERSION:
        raise StarterQuestionCatalogError(f"Unsupported catalog schema version: {schema_version}")

    questions_payload = payload.get("questions")
    if not isinstance(questions_payload, list) or not questions_payload:
        raise StarterQuestionCatalogError("Starter question catalog must include questions")

    return StarterQuestionCatalog(
        schema_version=schema_version,
        catalog_id=_required_text(payload, "catalog_id"),
        name=_required_text(payload, "name"),
        description=_required_text(payload, "description"),
        questions=[_question_from_payload(question) for question in questions_payload],
    )


def _question_from_payload(payload: Any) -> StarterQuestion:
    if not isinstance(payload, dict):
        raise StarterQuestionCatalogError("Starter question entries must be objects")

    return StarterQuestion(
        id=_required_text(payload, "id"),
        category=_required_text(payload, "category"),
        question_text=_required_text(payload, "question_text"),
        business_context=_required_text(payload, "business_context"),
        expected_data_dependencies=_required_text_list(payload, "expected_data_dependencies"),
        expected_graph_concepts=_required_text_list(payload, "expected_graph_concepts"),
    )


def _required_text(payload: dict[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise StarterQuestionCatalogError(f"Catalog field is required: {field}")
    return value.strip()


def _required_int(payload: dict[str, Any], field: str) -> int:
    value = payload.get(field)
    if not isinstance(value, int):
        raise StarterQuestionCatalogError(f"Catalog integer field is required: {field}")
    return value


def _required_text_list(payload: dict[str, Any], field: str) -> list[str]:
    value = payload.get(field)
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(item, str) and item.strip() for item in value)
    ):
        raise StarterQuestionCatalogError(f"Catalog field must be a non-empty string list: {field}")
    return [item.strip() for item in value]
