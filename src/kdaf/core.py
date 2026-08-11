"""Shared core APIs used by the CLI and MCP-style tool server."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from kdaf.config import KdafConfig, load_config
from kdaf.metadata import MetadataError, MetadataRepository, package_metadata
from kdaf.starter_dwh import StarterDwhError, StarterDwhRepository, starter_dwh_sql_artifacts
from kdaf.starter_graph import (
    Neo4jConnectionSettings,
    StarterGraphError,
    StarterGraphRepository,
    starter_graph_cypher_artifacts,
)
from kdaf.starter_questions import (
    StarterQuestionCatalogError,
    load_starter_question_catalog,
    starter_question_catalog,
)


class KdafError(ValueError):
    """Stable v0.2 application error for operator and agent surfaces."""

    def __init__(self, message: str, code: str = "kdaf_error") -> None:
        super().__init__(message)
        self.code = code
        self.message = message


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
            raise KdafError(str(exc), code=_metadata_error_code(exc)) from exc

    def list_projects(self) -> list[dict[str, str]]:
        return [project.to_dict() for project in self.metadata.list_projects()]

    def get_project(self, project_id: str) -> dict[str, str]:
        try:
            return self.metadata.get_project(project_id).to_dict()
        except MetadataError as exc:
            raise KdafError(str(exc), code=_metadata_error_code(exc)) from exc

    def create_run(self, project_id: str, status: str = "created") -> dict[str, str]:
        try:
            return self.metadata.create_run(project_id=project_id, status=status).to_dict()
        except MetadataError as exc:
            raise KdafError(str(exc), code=_metadata_error_code(exc)) from exc

    def list_runs(self, project_id: str | None = None) -> list[dict[str, str]]:
        try:
            return [run.to_dict() for run in self.metadata.list_runs(project_id=project_id)]
        except MetadataError as exc:
            raise KdafError(str(exc), code=_metadata_error_code(exc)) from exc

    def get_run(self, run_id: str) -> dict[str, str]:
        try:
            return self.metadata.get_run(run_id).to_dict()
        except MetadataError as exc:
            raise KdafError(str(exc), code=_metadata_error_code(exc)) from exc

    def create_competency_question(
        self,
        project_id: str,
        question_text: str,
        business_context: str = "",
    ) -> dict[str, str]:
        try:
            return self.metadata.create_competency_question(
                project_id=project_id,
                question_text=question_text,
                business_context=business_context,
            ).to_dict()
        except MetadataError as exc:
            raise KdafError(str(exc), code=_metadata_error_code(exc)) from exc

    def list_competency_questions(
        self,
        project_id: str | None = None,
    ) -> list[dict[str, str]]:
        try:
            return [
                question.to_dict()
                for question in self.metadata.list_competency_questions(project_id=project_id)
            ]
        except MetadataError as exc:
            raise KdafError(str(exc), code=_metadata_error_code(exc)) from exc

    def get_competency_question(self, question_id: str) -> dict[str, str]:
        try:
            return self.metadata.get_competency_question(question_id).to_dict()
        except MetadataError as exc:
            raise KdafError(str(exc), code=_metadata_error_code(exc)) from exc

    def create_mvg_artifact(
        self,
        project_id: str,
        name: str,
        description: str = "",
        question_ids: list[str] | None = None,
        concept_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        try:
            return self.metadata.create_mvg_artifact(
                project_id=project_id,
                name=name,
                description=description,
                question_ids=question_ids,
                concept_ids=concept_ids,
            ).to_dict()
        except MetadataError as exc:
            raise KdafError(str(exc), code=_metadata_error_code(exc)) from exc

    def list_mvg_artifacts(self, project_id: str | None = None) -> list[dict[str, Any]]:
        try:
            return [artifact.to_dict() for artifact in self.metadata.list_mvg_artifacts(project_id)]
        except MetadataError as exc:
            raise KdafError(str(exc), code=_metadata_error_code(exc)) from exc

    def get_mvg_artifact(self, mvg_id: str) -> dict[str, Any]:
        try:
            return self.metadata.get_mvg_artifact(mvg_id).to_dict()
        except MetadataError as exc:
            raise KdafError(str(exc), code=_metadata_error_code(exc)) from exc

    def add_question_to_mvg(self, mvg_id: str, question_id: str) -> dict[str, Any]:
        try:
            return self.metadata.add_question_to_mvg(mvg_id, question_id).to_dict()
        except MetadataError as exc:
            raise KdafError(str(exc), code=_metadata_error_code(exc)) from exc

    def add_concept_to_mvg(self, mvg_id: str, concept_id: str) -> dict[str, Any]:
        try:
            return self.metadata.add_concept_to_mvg(mvg_id, concept_id).to_dict()
        except MetadataError as exc:
            raise KdafError(str(exc), code=_metadata_error_code(exc)) from exc

    def starter_dwh_schema(self) -> dict[str, str]:
        artifacts = starter_dwh_sql_artifacts()
        return {
            "dialect": "postgres",
            "schema_sql": artifacts["schema"],
            "seed_sql": artifacts["seed"],
            "sample_queries_sql": artifacts["sample_queries"],
        }

    def load_starter_dwh(self, dwh_store_path: str | Path | None = None) -> dict[str, Any]:
        repository = StarterDwhRepository(dwh_store_path or self._default_starter_dwh_path())
        try:
            return repository.load_seed_data().to_dict()
        except StarterDwhError as exc:
            raise KdafError(str(exc), code="starter_dwh_error") from exc

    def starter_dwh_sample_facts(self, dwh_store_path: str | Path | None = None) -> dict[str, Any]:
        repository = StarterDwhRepository(dwh_store_path or self._default_starter_dwh_path())
        try:
            return {
                "budget_vs_actuals": repository.sample_budget_vs_actuals(),
                "department_spend": repository.sample_department_spend(),
            }
        except StarterDwhError as exc:
            raise KdafError(str(exc), code="starter_dwh_not_loaded") from exc

    def _default_starter_dwh_path(self) -> Path:
        return self.metadata.store_path.parent / "starter_dwh.sqlite3"

    def starter_graph_schema(self) -> dict[str, str]:
        artifacts = starter_graph_cypher_artifacts()
        return {
            "dialect": "cypher",
            "seed_cypher": artifacts["seed"],
            "sample_queries_cypher": artifacts["sample_queries"],
        }

    def load_starter_graph(self) -> dict[str, Any]:
        repository = StarterGraphRepository(self._neo4j_connection_settings())
        try:
            return repository.load_seed_data().to_dict()
        except StarterGraphError as exc:
            raise KdafError(str(exc), code="starter_graph_error") from exc

    def starter_graph_context(self) -> dict[str, Any]:
        repository = StarterGraphRepository(self._neo4j_connection_settings())
        try:
            return repository.inspect_context()
        except StarterGraphError as exc:
            raise KdafError(str(exc), code="starter_graph_not_loaded") from exc

    def starter_question_catalog(self) -> dict[str, Any]:
        try:
            return starter_question_catalog().to_dict()
        except StarterQuestionCatalogError as exc:
            raise KdafError(str(exc), code="starter_question_catalog_error") from exc

    def load_starter_questions(self, project_id: str) -> dict[str, Any]:
        try:
            return load_starter_question_catalog(self.metadata, project_id=project_id).to_dict()
        except MetadataError as exc:
            raise KdafError(str(exc), code=_metadata_error_code(exc)) from exc
        except StarterQuestionCatalogError as exc:
            raise KdafError(str(exc), code="starter_question_catalog_error") from exc

    def _neo4j_connection_settings(self) -> Neo4jConnectionSettings:
        return Neo4jConnectionSettings(
            uri=self.config.neo4j.uri,
            user=self.config.neo4j.user,
            password=self.config.neo4j.password,
            database=self.config.neo4j.database,
        )


def _safe_database_summary(database_config: Any) -> dict[str, Any]:
    return {
        "host": database_config.host,
        "port": database_config.port,
        "database": database_config.database,
        "user": database_config.user,
        "role": database_config.role,
    }


def _metadata_error_code(error: MetadataError) -> str:
    if "not found" in str(error).lower():
        return "not_found"
    return "metadata_error"
