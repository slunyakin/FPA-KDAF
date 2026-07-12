"""Package and runtime metadata helpers."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import metadata as importlib_metadata
from pathlib import Path
from uuid import uuid4

SCHEMA_VERSION = 1


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


class MetadataRepository:
    """SQLite-backed repository for v0.2 project and run metadata."""

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

    def table_names(self) -> set[str]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type = 'table' AND name LIKE 'kdaf_%'
                """
            ).fetchall()
        return {row["name"] for row in rows}

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


def _require_text(field: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MetadataError(f"{field} is required")
    return value.strip()


def _timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")
