"""Shared core APIs used by the CLI and MCP-style tool server."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from kdaf.config import KdafConfig, load_config
from kdaf.metadata import MetadataError, MetadataRepository, package_metadata


class KdafError(ValueError):
    """Stable v0.2 application error for operator and agent surfaces."""


@dataclass(frozen=True)
class HealthStatus:
    status: str
    service: str
    version: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


class KdafCore:
    """Shared service facade for KDAF operator and agent entrypoints."""

    def __init__(
        self,
        config: KdafConfig | None = None,
        config_path: str | Path | None = None,
        metadata_store_path: str | Path | None = None,
    ) -> None:
        if config is not None and config_path is not None:
            raise KdafError("config and config_path cannot both be provided")

        self.config = config if config is not None else load_config(config_path)
        store_path = metadata_store_path or self.config.runtime.metadata_store_path
        self.metadata = MetadataRepository(store_path)
        self.metadata.initialize_schema()

    def health(self) -> dict[str, str]:
        metadata = package_metadata()
        return HealthStatus(status="ok", service=metadata.name, version=metadata.version).to_dict()

    def config_summary(self) -> dict[str, Any]:
        return {
            "runtime": {
                "environment": self.config.runtime.environment,
                "log_level": self.config.runtime.log_level,
                "metadata_store_path": self.config.runtime.metadata_store_path,
            },
            "metadata_db": _safe_database_summary(self.config.metadata_db),
            "dwh_db": _safe_database_summary(self.config.dwh_db),
            "neo4j": {
                "uri": self.config.neo4j.uri,
                "user": self.config.neo4j.user,
                "database": self.config.neo4j.database,
            },
        }

    def create_project(self, name: str, description: str = "") -> dict[str, str]:
        try:
            return self.metadata.create_project(name=name, description=description).to_dict()
        except MetadataError as exc:
            raise KdafError(str(exc)) from exc

    def list_projects(self) -> list[dict[str, str]]:
        return [project.to_dict() for project in self.metadata.list_projects()]

    def get_project(self, project_id: str) -> dict[str, str]:
        try:
            return self.metadata.get_project(project_id).to_dict()
        except MetadataError as exc:
            raise KdafError(str(exc)) from exc

    def create_run(self, project_id: str, status: str = "created") -> dict[str, str]:
        try:
            return self.metadata.create_run(project_id=project_id, status=status).to_dict()
        except MetadataError as exc:
            raise KdafError(str(exc)) from exc

    def list_runs(self, project_id: str | None = None) -> list[dict[str, str]]:
        try:
            return [run.to_dict() for run in self.metadata.list_runs(project_id=project_id)]
        except MetadataError as exc:
            raise KdafError(str(exc)) from exc

    def get_run(self, run_id: str) -> dict[str, str]:
        try:
            return self.metadata.get_run(run_id).to_dict()
        except MetadataError as exc:
            raise KdafError(str(exc)) from exc


def _safe_database_summary(database_config: Any) -> dict[str, Any]:
    return {
        "host": database_config.host,
        "port": database_config.port,
        "database": database_config.database,
        "user": database_config.user,
        "role": database_config.role,
    }
