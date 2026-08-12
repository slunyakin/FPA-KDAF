"""Package metadata and durable framework workflow metadata."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Any
from uuid import uuid4

SCHEMA_VERSION = 3
VALIDATION_STATUSES = frozenset({"pending", "approved", "rejected", "needs_changes"})
TERMINAL_VALIDATION_STATUSES = frozenset({"approved", "rejected"})


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
        version = "0.5.0"
    return PackageMetadata(name="kdaf", version=version)


class MetadataError(ValueError):
    """Raised when metadata repository operations cannot be completed."""

    def __init__(self, message: str, code: str = "metadata_error") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Project:
    id: str
    name: str
    description: str
    created_at: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class Run:
    id: str
    project_id: str
    status: str
    created_at: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class Source:
    id: str
    name: str
    source_type: str
    locator: str
    metadata: dict[str, Any]
    content_hash: str | None
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExtractionBatch:
    id: str
    source_id: str
    status: str
    row_count: int
    error_code: str | None
    error_message: str | None
    started_at: str
    completed_at: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProvenanceLink:
    id: str
    source_id: str
    batch_id: str
    target_store: str
    target_type: str
    target_id: str
    created_at: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class ValidationDecision:
    id: str
    validation_id: str
    action: str
    from_status: str | None
    to_status: str
    reviewer: str
    comment: str
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ValidationItem:
    id: str
    subject_type: str
    subject_id: str
    status: str
    payload: dict[str, Any]
    reviewer: str | None
    comment: str
    created_at: str
    updated_at: str
    decided_at: str | None
    decisions: tuple[ValidationDecision, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["decisions"] = [decision.to_dict() for decision in self.decisions]
        return result


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


@dataclass(frozen=True)
class AuditEvent:
    id: str
    event_type: str
    subject_type: str | None
    subject_id: str | None
    payload: dict[str, Any]
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class MetadataRepository:
    """SQLite local adapter for framework, MVG, and audit workflow metadata."""

    def __init__(self, store_path: str | Path) -> None:
        self.store_path = Path(store_path)

    def initialize_schema(self) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(_schema_sql())
            _add_missing_columns(connection, "kdaf_source_registry", _source_migration_columns())
            _add_missing_columns(
                connection, "kdaf_validation_queue", _validation_migration_columns()
            )
            _add_missing_columns(connection, "kdaf_audit_log", _audit_migration_columns())
            connection.execute(
                "INSERT OR IGNORE INTO kdaf_schema_migrations (version, applied_at) VALUES (?, ?)",
                (SCHEMA_VERSION, _timestamp()),
            )

    def create_project(self, name: str, description: str = "") -> Project:
        cleaned_name = _require_text("project.name", name)
        cleaned_description = description.strip() if isinstance(description, str) else ""
        project = Project(str(uuid4()), cleaned_name, cleaned_description, _timestamp())
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO kdaf_projects (id, name, description, created_at) VALUES (?, ?, ?, ?)",
                (project.id, project.name, project.description, project.created_at),
            )
        return project

    def list_projects(self) -> list[Project]:
        return self._select_projects()

    def _select_projects(self) -> list[Project]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, name, description, created_at
                FROM kdaf_projects ORDER BY created_at, id
                """
            ).fetchall()
        return [Project(**dict(row)) for row in rows]

    def get_project(self, project_id: str) -> Project:
        row = self._fetch_one(
            "SELECT id, name, description, created_at FROM kdaf_projects WHERE id = ?",
            (_require_text("project.id", project_id),),
        )
        if row is None:
            raise MetadataError(f"Project not found: {project_id}", "not_found")
        return Project(**dict(row))

    def create_run(self, project_id: str, status: str = "created") -> Run:
        project = self.get_project(project_id)
        run = Run(str(uuid4()), project.id, _require_text("run.status", status), _timestamp())
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO kdaf_runs (id, project_id, status, created_at) VALUES (?, ?, ?, ?)",
                (run.id, run.project_id, run.status, run.created_at),
            )
        return run

    def list_runs(self, project_id: str | None = None) -> list[Run]:
        query = "SELECT id, project_id, status, created_at FROM kdaf_runs"
        params: tuple[str, ...] = ()
        if project_id is not None:
            query += " WHERE project_id = ?"
            params = (_require_text("project.id", project_id),)
        with self._connect() as connection:
            rows = connection.execute(query + " ORDER BY created_at, id", params).fetchall()
        return [Run(**dict(row)) for row in rows]

    def get_run(self, run_id: str) -> Run:
        cleaned_id = _require_text("run.id", run_id)
        row = self._fetch_one(
            "SELECT id, project_id, status, created_at FROM kdaf_runs WHERE id = ?",
            (cleaned_id,),
        )
        if row is None:
            raise MetadataError(f"Run not found: {cleaned_id}", "not_found")
        return Run(**dict(row))

    def record_audit_event(
        self,
        event_type: str,
        subject_type: str | None,
        subject_id: str | None,
        payload: dict[str, Any],
    ) -> AuditEvent:
        """Persist framework audit metadata without crossing into the financial DWH."""

        cleaned_event_type = _require_text("audit.event_type", event_type)
        cleaned_payload = _require_object("audit.payload", payload)
        event = AuditEvent(
            id=str(uuid4()),
            event_type=cleaned_event_type,
            subject_type=(
                _require_text("audit.subject_type", subject_type)
                if subject_type is not None
                else None
            ),
            subject_id=(
                _require_text("audit.subject_id", subject_id) if subject_id is not None else None
            ),
            payload=cleaned_payload,
            created_at=_timestamp(),
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO kdaf_audit_log
                    (id, event_type, subject_type, subject_id, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    event.id,
                    event.event_type,
                    event.subject_type,
                    event.subject_id,
                    _json(event.payload),
                    event.created_at,
                ),
            )
        return event

    def list_audit_events(self, event_type: str | None = None) -> list[AuditEvent]:
        query = "SELECT * FROM kdaf_audit_log"
        params: tuple[str, ...] = ()
        if event_type is not None:
            query += " WHERE event_type = ?"
            params = (_require_text("audit.event_type", event_type),)
        with self._connect() as connection:
            rows = connection.execute(query + " ORDER BY created_at, id", params).fetchall()
        return [
            AuditEvent(
                id=row["id"],
                event_type=row["event_type"],
                subject_type=row["subject_type"],
                subject_id=row["subject_id"],
                payload=json.loads(row["payload_json"]),
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def create_source(
        self,
        name: str,
        source_type: str,
        locator: str,
        metadata: dict[str, Any] | None = None,
    ) -> Source:
        cleaned_type = _require_text("source.source_type", source_type).lower()
        if cleaned_type != "csv":
            raise MetadataError(
                f"Unsupported source type: {cleaned_type}", "unsupported_source_type"
            )
        cleaned_metadata = _require_object("source.metadata", {} if metadata is None else metadata)
        now = _timestamp()
        source = Source(
            str(uuid4()),
            _require_text("source.name", name),
            cleaned_type,
            _require_text("source.locator", locator),
            cleaned_metadata,
            None,
            now,
            now,
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO kdaf_source_registry
                    (id, name, source_type, locator, metadata_json, content_hash,
                     created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source.id,
                    source.name,
                    source.source_type,
                    source.locator,
                    _json(source.metadata),
                    source.content_hash,
                    source.created_at,
                    source.updated_at,
                ),
            )
            self._audit(connection, "source.registered", "source", source.id, source.to_dict())
        return source

    def list_sources(self) -> list[Source]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM kdaf_source_registry ORDER BY created_at, id"
            ).fetchall()
        return [_source_from_row(row) for row in rows]

    def get_source(self, source_id: str) -> Source:
        cleaned_id = _require_text("source.id", source_id)
        row = self._fetch_one("SELECT * FROM kdaf_source_registry WHERE id = ?", (cleaned_id,))
        if row is None:
            raise MetadataError(f"Source not found: {cleaned_id}", "not_found")
        return _source_from_row(row)

    def update_source_hash(self, source_id: str, content_hash: str) -> Source:
        self.get_source(source_id)
        with self._connect() as connection:
            connection.execute(
                "UPDATE kdaf_source_registry SET content_hash = ?, updated_at = ? WHERE id = ?",
                (_require_text("source.content_hash", content_hash), _timestamp(), source_id),
            )
        return self.get_source(source_id)

    def start_extraction(self, source_id: str) -> ExtractionBatch:
        source = self.get_source(source_id)
        batch = ExtractionBatch(
            str(uuid4()), source.id, "running", 0, None, None, _timestamp(), None
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO kdaf_extraction_batches
                    (id, source_id, status, row_count, error_code, error_message,
                     started_at, completed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                tuple(asdict(batch).values()),
            )
            self._audit(connection, "extraction.started", "extraction", batch.id, batch.to_dict())
        return batch

    def finish_extraction(
        self,
        batch_id: str,
        *,
        status: str,
        row_count: int = 0,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> ExtractionBatch:
        self.get_extraction(batch_id)
        if status not in {"completed", "failed"}:
            raise MetadataError(f"Invalid extraction status: {status}", "invalid_status")
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE kdaf_extraction_batches
                SET status = ?, row_count = ?, error_code = ?, error_message = ?, completed_at = ?
                WHERE id = ?
                """,
                (status, row_count, error_code, error_message, _timestamp(), batch_id),
            )
            self._audit(
                connection,
                f"extraction.{status}",
                "extraction",
                batch_id,
                {"row_count": row_count, "error_code": error_code},
            )
        return self.get_extraction(batch_id)

    def get_extraction(self, batch_id: str) -> ExtractionBatch:
        cleaned_id = _require_text("extraction.id", batch_id)
        row = self._fetch_one("SELECT * FROM kdaf_extraction_batches WHERE id = ?", (cleaned_id,))
        if row is None:
            raise MetadataError(f"Extraction not found: {cleaned_id}", "not_found")
        return ExtractionBatch(**dict(row))

    def list_extractions(self, source_id: str | None = None) -> list[ExtractionBatch]:
        query = "SELECT * FROM kdaf_extraction_batches"
        params: tuple[str, ...] = ()
        if source_id is not None:
            source = self.get_source(source_id)
            query += " WHERE source_id = ?"
            params = (source.id,)
        with self._connect() as connection:
            rows = connection.execute(query + " ORDER BY started_at, id", params).fetchall()
        return [ExtractionBatch(**dict(row)) for row in rows]

    def add_provenance_link(
        self,
        source_id: str,
        batch_id: str,
        target_store: str,
        target_type: str,
        target_id: str,
    ) -> ProvenanceLink:
        self.get_source(source_id)
        self.get_extraction(batch_id)
        link = ProvenanceLink(
            str(uuid4()),
            source_id,
            batch_id,
            _require_text("provenance.target_store", target_store),
            _require_text("provenance.target_type", target_type),
            _require_text("provenance.target_id", target_id),
            _timestamp(),
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO kdaf_provenance_links
                    (id, source_id, batch_id, target_store, target_type, target_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                tuple(asdict(link).values()),
            )
        return link

    def list_provenance_links(self, batch_id: str) -> list[ProvenanceLink]:
        self.get_extraction(batch_id)
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM kdaf_provenance_links WHERE batch_id = ? ORDER BY created_at, id",
                (batch_id,),
            ).fetchall()
        return [ProvenanceLink(**dict(row)) for row in rows]

    def enqueue_validation(
        self,
        subject_type: str,
        subject_id: str,
        payload: dict[str, Any] | None = None,
    ) -> ValidationItem:
        cleaned_type = _require_text("validation.subject_type", subject_type)
        cleaned_id = _require_text("validation.subject_id", subject_id)
        cleaned_payload = _require_object("validation.payload", {} if payload is None else payload)
        if cleaned_type == "source":
            self.get_source(cleaned_id)
        elif cleaned_type == "extraction":
            self.get_extraction(cleaned_id)
        else:
            raise MetadataError(
                f"Unsupported validation subject type: {cleaned_type}",
                "invalid_subject_type",
            )
        now = _timestamp()
        validation_id = str(uuid4())
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO kdaf_validation_queue
                    (id, subject_type, subject_id, status, payload_json, reviewer, comment,
                     created_at, updated_at, decided_at)
                VALUES (?, ?, ?, 'pending', ?, NULL, '', ?, ?, NULL)
                """,
                (validation_id, cleaned_type, cleaned_id, _json(cleaned_payload), now, now),
            )
            self._insert_decision(
                connection, validation_id, "enqueue", None, "pending", "system", ""
            )
            self._audit(
                connection,
                "validation.enqueued",
                "validation",
                validation_id,
                {"subject_type": cleaned_type, "subject_id": cleaned_id},
            )
        return self.get_validation(validation_id)

    def list_validations(self, status: str | None = None) -> list[ValidationItem]:
        query = "SELECT id FROM kdaf_validation_queue"
        params: tuple[str, ...] = ()
        if status is not None:
            cleaned_status = _validation_status(status)
            query += " WHERE status = ?"
            params = (cleaned_status,)
        with self._connect() as connection:
            rows = connection.execute(query + " ORDER BY created_at, id", params).fetchall()
        return [self.get_validation(row["id"]) for row in rows]

    def get_validation(self, validation_id: str) -> ValidationItem:
        cleaned_id = _require_text("validation.id", validation_id)
        row = self._fetch_one("SELECT * FROM kdaf_validation_queue WHERE id = ?", (cleaned_id,))
        if row is None:
            raise MetadataError(f"Validation item not found: {cleaned_id}", "not_found")
        with self._connect() as connection:
            decisions = connection.execute(
                """
                SELECT * FROM kdaf_validation_decisions
                WHERE validation_id = ? ORDER BY created_at, id
                """,
                (cleaned_id,),
            ).fetchall()
        return _validation_from_row(
            row, tuple(ValidationDecision(**dict(item)) for item in decisions)
        )

    def decide_validation(
        self,
        validation_id: str,
        status: str,
        reviewer: str,
        comment: str = "",
    ) -> ValidationItem:
        item = self.get_validation(validation_id)
        target = _validation_status(status)
        if target not in TERMINAL_VALIDATION_STATUSES:
            raise MetadataError(f"Invalid decision status: {target}", "invalid_status")
        if item.status not in {"pending", "needs_changes"}:
            raise MetadataError(
                f"Validation item in {item.status} state cannot move to {target}",
                "invalid_transition",
            )
        return self._transition_validation(item, target, target, reviewer, comment)

    def comment_validation(self, validation_id: str, reviewer: str, comment: str) -> ValidationItem:
        item = self.get_validation(validation_id)
        if item.status in TERMINAL_VALIDATION_STATUSES:
            raise MetadataError(
                f"Validation item in {item.status} state cannot move to needs_changes",
                "invalid_transition",
            )
        cleaned_comment = _require_text("validation.comment", comment)
        return self._transition_validation(
            item, "needs_changes", "comment", reviewer, cleaned_comment
        )

    def _transition_validation(
        self,
        item: ValidationItem,
        target: str,
        action: str,
        reviewer: str,
        comment: str,
    ) -> ValidationItem:
        cleaned_reviewer = _require_text("validation.reviewer", reviewer)
        if not isinstance(comment, str):
            raise MetadataError("validation.comment must be text", "invalid_input")
        cleaned_comment = comment.strip()
        now = _timestamp()
        decided_at = now if target in TERMINAL_VALIDATION_STATUSES else None
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE kdaf_validation_queue
                SET status = ?, reviewer = ?, comment = ?, updated_at = ?, decided_at = ?
                WHERE id = ?
                """,
                (target, cleaned_reviewer, cleaned_comment, now, decided_at, item.id),
            )
            self._insert_decision(
                connection,
                item.id,
                action,
                item.status,
                target,
                cleaned_reviewer,
                cleaned_comment,
            )
            self._audit(
                connection,
                f"validation.{action}",
                "validation",
                item.id,
                {"from_status": item.status, "to_status": target, "reviewer": cleaned_reviewer},
            )
        return self.get_validation(item.id)

    def _insert_decision(
        self,
        connection: sqlite3.Connection,
        validation_id: str,
        action: str,
        from_status: str | None,
        to_status: str,
        reviewer: str,
        comment: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO kdaf_validation_decisions
                (id, validation_id, action, from_status, to_status, reviewer, comment, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid4()),
                validation_id,
                action,
                from_status,
                to_status,
                reviewer,
                comment,
                _timestamp(),
            ),
        )

    def _audit(
        self,
        connection: sqlite3.Connection,
        event_type: str,
        subject_type: str,
        subject_id: str,
        payload: dict[str, Any],
    ) -> None:
        connection.execute(
            """
            INSERT INTO kdaf_audit_log
                (id, event_type, subject_type, subject_id, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (str(uuid4()), event_type, subject_type, subject_id, _json(payload), _timestamp()),
        )

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
            raise MetadataError(f"Competency question not found: {cleaned_id}", "not_found")
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
            raise MetadataError(f"MVG artifact not found: {cleaned_id}", "not_found")
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
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name LIKE 'kdaf_%'"
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

    def _fetch_one(self, query: str, params: tuple[str, ...]) -> sqlite3.Row | None:
        with self._connect() as connection:
            return connection.execute(query, params).fetchone()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.store_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection


def _schema_sql() -> str:
    return """
    CREATE TABLE IF NOT EXISTS kdaf_schema_migrations (
        version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS kdaf_projects (
        id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS kdaf_runs (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES kdaf_projects(id),
        status TEXT NOT NULL, created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS kdaf_audit_log (
        id TEXT PRIMARY KEY, event_type TEXT NOT NULL, subject_type TEXT,
        subject_id TEXT, payload_json TEXT NOT NULL, created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS kdaf_source_registry (
        id TEXT PRIMARY KEY, name TEXT NOT NULL, source_type TEXT NOT NULL, locator TEXT NOT NULL,
        metadata_json TEXT NOT NULL DEFAULT '{}', content_hash TEXT, created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS kdaf_extraction_batches (
        id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES kdaf_source_registry(id),
        status TEXT NOT NULL, row_count INTEGER NOT NULL DEFAULT 0, error_code TEXT,
        error_message TEXT, started_at TEXT NOT NULL, completed_at TEXT
    );
    CREATE TABLE IF NOT EXISTS kdaf_provenance_links (
        id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES kdaf_source_registry(id),
        batch_id TEXT NOT NULL REFERENCES kdaf_extraction_batches(id), target_store TEXT NOT NULL,
        target_type TEXT NOT NULL, target_id TEXT NOT NULL, created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS kdaf_validation_queue (
        id TEXT PRIMARY KEY, subject_type TEXT NOT NULL, subject_id TEXT NOT NULL,
        status TEXT NOT NULL, payload_json TEXT NOT NULL DEFAULT '{}', reviewer TEXT,
        comment TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        decided_at TEXT
    );
    CREATE TABLE IF NOT EXISTS kdaf_validation_decisions (
        id TEXT PRIMARY KEY, validation_id TEXT NOT NULL REFERENCES kdaf_validation_queue(id),
        action TEXT NOT NULL, from_status TEXT, to_status TEXT NOT NULL, reviewer TEXT NOT NULL,
        comment TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS kdaf_eval_results (
        id TEXT PRIMARY KEY, run_id TEXT REFERENCES kdaf_runs(id), metric_name TEXT NOT NULL,
        metric_value TEXT NOT NULL, created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS kdaf_competency_questions (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES kdaf_projects(id),
        question_text TEXT NOT NULL, business_context TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS kdaf_mvg_artifacts (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES kdaf_projects(id),
        name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS kdaf_mvg_questions (
        mvg_id TEXT NOT NULL REFERENCES kdaf_mvg_artifacts(id) ON DELETE CASCADE,
        question_id TEXT NOT NULL REFERENCES kdaf_competency_questions(id),
        PRIMARY KEY (mvg_id, question_id)
    );
    CREATE TABLE IF NOT EXISTS kdaf_mvg_concepts (
        mvg_id TEXT NOT NULL REFERENCES kdaf_mvg_artifacts(id) ON DELETE CASCADE,
        concept_id TEXT NOT NULL, PRIMARY KEY (mvg_id, concept_id)
    );
    """


def _source_migration_columns() -> dict[str, str]:
    return {
        "name": "TEXT NOT NULL DEFAULT 'Unnamed source'",
        "metadata_json": "TEXT NOT NULL DEFAULT '{}'",
        "content_hash": "TEXT",
        "updated_at": "TEXT NOT NULL DEFAULT ''",
    }


def _validation_migration_columns() -> dict[str, str]:
    return {
        "subject_type": "TEXT NOT NULL DEFAULT 'legacy'",
        "subject_id": "TEXT NOT NULL DEFAULT 'legacy'",
        "reviewer": "TEXT",
        "comment": "TEXT NOT NULL DEFAULT ''",
        "updated_at": "TEXT NOT NULL DEFAULT ''",
        "decided_at": "TEXT",
    }


def _audit_migration_columns() -> dict[str, str]:
    return {"subject_type": "TEXT", "subject_id": "TEXT"}


def _add_missing_columns(
    connection: sqlite3.Connection, table: str, columns: dict[str, str]
) -> None:
    existing = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}
    for name, declaration in columns.items():
        if name not in existing:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} {declaration}")


def _source_from_row(row: sqlite3.Row) -> Source:
    return Source(
        id=row["id"],
        name=row["name"],
        source_type=row["source_type"],
        locator=row["locator"],
        metadata=json.loads(row["metadata_json"]),
        content_hash=row["content_hash"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _validation_from_row(
    row: sqlite3.Row, decisions: tuple[ValidationDecision, ...]
) -> ValidationItem:
    return ValidationItem(
        id=row["id"],
        subject_type=row["subject_type"],
        subject_id=row["subject_id"],
        status=row["status"],
        payload=json.loads(row["payload_json"]),
        reviewer=row["reviewer"],
        comment=row["comment"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        decided_at=row["decided_at"],
        decisions=decisions,
    )


def _competency_question_from_row(row: sqlite3.Row) -> CompetencyQuestion:
    return CompetencyQuestion(
        id=row["id"],
        project_id=row["project_id"],
        question_text=row["question_text"],
        business_context=row["business_context"],
        created_at=row["created_at"],
    )


def _require_text(field: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MetadataError(f"{field} is required", "missing_field")
    return value.strip()


def _require_object(field: str, value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise MetadataError(f"{field} must be an object", "invalid_input")
    try:
        _json(value)
    except (TypeError, ValueError) as exc:
        raise MetadataError(f"{field} must be JSON-serializable", "invalid_input") from exc
    return value


def _validation_status(value: Any) -> str:
    cleaned = _require_text("validation.status", value).replace("-", "_")
    if cleaned not in VALIDATION_STATUSES:
        raise MetadataError(f"Invalid validation status: {value}", "invalid_status")
    return cleaned


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")
