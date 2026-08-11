"""Package and runtime metadata helpers."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import metadata as importlib_metadata
from pathlib import Path
from uuid import uuid4

SCHEMA_VERSION = 2


@dataclass(frozen=True)
class PackageMetadata:
    """Small public metadata object used by tests and downstream tooling."""

    name: str
    version: str


def package_metadata() -> PackageMetadata:
    """Return installed package metadata, falling back to source-tree defaults."""

    try:
        version = importlib_metadata.version("kdaf")
    except importlib_metadata.PackageNotFoundError:
        version = "0.2.0"

    return PackageMetadata(name="kdaf", version=version)


class MetadataError(ValueError):
    """Raised when metadata repository operations cannot be completed."""


@dataclass(frozen=True)
class Project:
    id: str
    name: str
    description: str
    created_at: str

    def to_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class Run:
    id: str
    project_id: str
    status: str
    created_at: str

    def to_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "status": self.status,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class CompetencyQuestion:
    id: str
    project_id: str
    question_text: str
    business_context: str
    created_at: str

    def to_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "question_text": self.question_text,
            "business_context": self.business_context,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class MvgArtifact:
    id: str
    project_id: str
    name: str
    description: str
    question_ids: list[str]
    concept_ids: list[str]
    created_at: str

    def to_dict(self) -> dict[str, str | list[str]]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "name": self.name,
            "description": self.description,
            "question_ids": self.question_ids,
            "concept_ids": self.concept_ids,
            "created_at": self.created_at,
        }


class MetadataRepository:
    """SQLite-backed repository for project, run, and MVG metadata."""

    def __init__(self, store_path: str | Path) -> None:
        self.store_path = Path(store_path)

    def initialize_schema(self) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS kdaf_schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS kdaf_projects (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS kdaf_runs (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES kdaf_projects(id),
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS kdaf_audit_log (
                    id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS kdaf_source_registry (
                    id TEXT PRIMARY KEY,
                    source_type TEXT NOT NULL,
                    locator TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS kdaf_validation_queue (
                    id TEXT PRIMARY KEY,
                    project_id TEXT REFERENCES kdaf_projects(id),
                    status TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS kdaf_eval_results (
                    id TEXT PRIMARY KEY,
                    run_id TEXT REFERENCES kdaf_runs(id),
                    metric_name TEXT NOT NULL,
                    metric_value TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS kdaf_competency_questions (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES kdaf_projects(id),
                    question_text TEXT NOT NULL,
                    business_context TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS kdaf_mvg_artifacts (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES kdaf_projects(id),
                    name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS kdaf_mvg_questions (
                    mvg_id TEXT NOT NULL REFERENCES kdaf_mvg_artifacts(id) ON DELETE CASCADE,
                    question_id TEXT NOT NULL REFERENCES kdaf_competency_questions(id),
                    PRIMARY KEY (mvg_id, question_id)
                );

                CREATE TABLE IF NOT EXISTS kdaf_mvg_concepts (
                    mvg_id TEXT NOT NULL REFERENCES kdaf_mvg_artifacts(id) ON DELETE CASCADE,
                    concept_id TEXT NOT NULL,
                    PRIMARY KEY (mvg_id, concept_id)
                );
                """
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO kdaf_schema_migrations (version, applied_at)
                VALUES (?, ?)
                """,
                (SCHEMA_VERSION, _timestamp()),
            )

    def create_project(self, name: str, description: str = "") -> Project:
        cleaned_name = _require_text("project.name", name)
        cleaned_description = description.strip() if description else ""
        project = Project(
            id=str(uuid4()),
            name=cleaned_name,
            description=cleaned_description,
            created_at=_timestamp(),
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO kdaf_projects (id, name, description, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (project.id, project.name, project.description, project.created_at),
            )
        return project

    def list_projects(self) -> list[Project]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, name, description, created_at
                FROM kdaf_projects
                ORDER BY created_at, id
                """
            ).fetchall()
        return [_project_from_row(row) for row in rows]

    def get_project(self, project_id: str) -> Project:
        cleaned_id = _require_text("project.id", project_id)
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, name, description, created_at
                FROM kdaf_projects
                WHERE id = ?
                """,
                (cleaned_id,),
            ).fetchone()
        if row is None:
            raise MetadataError(f"Project not found: {cleaned_id}")
        return _project_from_row(row)

    def create_run(self, project_id: str, status: str = "created") -> Run:
        project = self.get_project(project_id)
        cleaned_status = _require_text("run.status", status)
        run = Run(
            id=str(uuid4()),
            project_id=project.id,
            status=cleaned_status,
            created_at=_timestamp(),
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO kdaf_runs (id, project_id, status, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (run.id, run.project_id, run.status, run.created_at),
            )
        return run

    def list_runs(self, project_id: str | None = None) -> list[Run]:
        with self._connect() as connection:
            if project_id is None:
                rows = connection.execute(
                    """
                    SELECT id, project_id, status, created_at
                    FROM kdaf_runs
                    ORDER BY created_at, id
                    """
                ).fetchall()
            else:
                cleaned_id = _require_text("project.id", project_id)
                rows = connection.execute(
                    """
                    SELECT id, project_id, status, created_at
                    FROM kdaf_runs
                    WHERE project_id = ?
                    ORDER BY created_at, id
                    """,
                    (cleaned_id,),
                ).fetchall()
        return [_run_from_row(row) for row in rows]

    def get_run(self, run_id: str) -> Run:
        cleaned_id = _require_text("run.id", run_id)
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, project_id, status, created_at
                FROM kdaf_runs
                WHERE id = ?
                """,
                (cleaned_id,),
            ).fetchone()
        if row is None:
            raise MetadataError(f"Run not found: {cleaned_id}")
        return _run_from_row(row)

    def create_competency_question(
        self,
        project_id: str,
        question_text: str,
        business_context: str = "",
    ) -> CompetencyQuestion:
        project = self.get_project(project_id)
        cleaned_question = _require_text("competency_question.question_text", question_text)
        cleaned_context = business_context.strip() if business_context else ""
        question = CompetencyQuestion(
            id=str(uuid4()),
            project_id=project.id,
            question_text=cleaned_question,
            business_context=cleaned_context,
            created_at=_timestamp(),
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO kdaf_competency_questions
                    (id, project_id, question_text, business_context, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    question.id,
                    question.project_id,
                    question.question_text,
                    question.business_context,
                    question.created_at,
                ),
            )
        return question

    def list_competency_questions(
        self,
        project_id: str | None = None,
    ) -> list[CompetencyQuestion]:
        with self._connect() as connection:
            if project_id is None:
                rows = connection.execute(
                    """
                    SELECT id, project_id, question_text, business_context, created_at
                    FROM kdaf_competency_questions
                    ORDER BY created_at, id
                    """
                ).fetchall()
            else:
                project = self.get_project(project_id)
                rows = connection.execute(
                    """
                    SELECT id, project_id, question_text, business_context, created_at
                    FROM kdaf_competency_questions
                    WHERE project_id = ?
                    ORDER BY created_at, id
                    """,
                    (project.id,),
                ).fetchall()
        return [_competency_question_from_row(row) for row in rows]

    def get_competency_question(self, question_id: str) -> CompetencyQuestion:
        cleaned_id = _require_text("competency_question.id", question_id)
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, project_id, question_text, business_context, created_at
                FROM kdaf_competency_questions
                WHERE id = ?
                """,
                (cleaned_id,),
            ).fetchone()
        if row is None:
            raise MetadataError(f"Competency question not found: {cleaned_id}")
        return _competency_question_from_row(row)

    def create_mvg_artifact(
        self,
        project_id: str,
        name: str,
        description: str = "",
        question_ids: list[str] | None = None,
        concept_ids: list[str] | None = None,
    ) -> MvgArtifact:
        project = self.get_project(project_id)
        cleaned_name = _require_text("mvg.name", name)
        cleaned_description = description.strip() if description else ""
        validated_question_ids = self._validate_mvg_question_ids(
            project.id,
            question_ids or [],
        )
        validated_concept_ids = [
            _require_text("mvg.concept_id", concept_id) for concept_id in concept_ids or []
        ]
        artifact = MvgArtifact(
            id=str(uuid4()),
            project_id=project.id,
            name=cleaned_name,
            description=cleaned_description,
            question_ids=[],
            concept_ids=[],
            created_at=_timestamp(),
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO kdaf_mvg_artifacts (id, project_id, name, description, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    artifact.id,
                    artifact.project_id,
                    artifact.name,
                    artifact.description,
                    artifact.created_at,
                ),
            )

        for question_id in validated_question_ids:
            self.add_question_to_mvg(artifact.id, question_id)
        for concept_id in validated_concept_ids:
            self.add_concept_to_mvg(artifact.id, concept_id)
        return self.get_mvg_artifact(artifact.id)

    def list_mvg_artifacts(self, project_id: str | None = None) -> list[MvgArtifact]:
        with self._connect() as connection:
            if project_id is None:
                rows = connection.execute(
                    """
                    SELECT id, project_id, name, description, created_at
                    FROM kdaf_mvg_artifacts
                    ORDER BY created_at, id
                    """
                ).fetchall()
            else:
                project = self.get_project(project_id)
                rows = connection.execute(
                    """
                    SELECT id, project_id, name, description, created_at
                    FROM kdaf_mvg_artifacts
                    WHERE project_id = ?
                    ORDER BY created_at, id
                    """,
                    (project.id,),
                ).fetchall()
        return [self._mvg_artifact_from_row(row) for row in rows]

    def get_mvg_artifact(self, mvg_id: str) -> MvgArtifact:
        cleaned_id = _require_text("mvg.id", mvg_id)
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, project_id, name, description, created_at
                FROM kdaf_mvg_artifacts
                WHERE id = ?
                """,
                (cleaned_id,),
            ).fetchone()
        if row is None:
            raise MetadataError(f"MVG artifact not found: {cleaned_id}")
        return self._mvg_artifact_from_row(row)

    def add_question_to_mvg(self, mvg_id: str, question_id: str) -> MvgArtifact:
        artifact = self.get_mvg_artifact(mvg_id)
        question = self.get_competency_question(question_id)
        if question.project_id != artifact.project_id:
            raise MetadataError(
                "Competency question and MVG artifact must belong to the same project"
            )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO kdaf_mvg_questions (mvg_id, question_id)
                VALUES (?, ?)
                """,
                (artifact.id, question.id),
            )
        return self.get_mvg_artifact(artifact.id)

    def add_concept_to_mvg(self, mvg_id: str, concept_id: str) -> MvgArtifact:
        artifact = self.get_mvg_artifact(mvg_id)
        cleaned_concept_id = _require_text("mvg.concept_id", concept_id)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO kdaf_mvg_concepts (mvg_id, concept_id)
                VALUES (?, ?)
                """,
                (artifact.id, cleaned_concept_id),
            )
        return self.get_mvg_artifact(artifact.id)

    def table_names(self) -> set[str]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type = 'table' AND name LIKE 'kdaf_%'
                """
            ).fetchall()
        return {row["name"] for row in rows}

    def _mvg_artifact_from_row(self, row: sqlite3.Row) -> MvgArtifact:
        with self._connect() as connection:
            question_rows = connection.execute(
                """
                SELECT question_id
                FROM kdaf_mvg_questions
                WHERE mvg_id = ?
                ORDER BY question_id
                """,
                (row["id"],),
            ).fetchall()
            concept_rows = connection.execute(
                """
                SELECT concept_id
                FROM kdaf_mvg_concepts
                WHERE mvg_id = ?
                ORDER BY concept_id
                """,
                (row["id"],),
            ).fetchall()
        return MvgArtifact(
            id=row["id"],
            project_id=row["project_id"],
            name=row["name"],
            description=row["description"],
            question_ids=[question_row["question_id"] for question_row in question_rows],
            concept_ids=[concept_row["concept_id"] for concept_row in concept_rows],
            created_at=row["created_at"],
        )

    def _validate_mvg_question_ids(
        self,
        project_id: str,
        question_ids: list[str],
    ) -> list[str]:
        validated_ids: list[str] = []
        for question_id in question_ids:
            question = self.get_competency_question(question_id)
            if question.project_id != project_id:
                raise MetadataError(
                    "Competency question and MVG artifact must belong to the same project"
                )
            validated_ids.append(question.id)
        return validated_ids

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.store_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection


def _project_from_row(row: sqlite3.Row) -> Project:
    return Project(
        id=row["id"],
        name=row["name"],
        description=row["description"],
        created_at=row["created_at"],
    )


def _run_from_row(row: sqlite3.Row) -> Run:
    return Run(
        id=row["id"],
        project_id=row["project_id"],
        status=row["status"],
        created_at=row["created_at"],
    )


def _competency_question_from_row(row: sqlite3.Row) -> CompetencyQuestion:
    return CompetencyQuestion(
        id=row["id"],
        project_id=row["project_id"],
        question_text=row["question_text"],
        business_context=row["business_context"],
        created_at=row["created_at"],
    )


def _require_text(field: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MetadataError(f"{field} is required")
    return value.strip()


def _timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")
