"""Unified FP&A starter-kit loader."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from kdaf.metadata import MetadataRepository
from kdaf.starter_dwh import StarterDwhRepository
from kdaf.starter_graph import Neo4jConnectionSettings, StarterGraphRepository
from kdaf.starter_questions import load_starter_question_catalog

STARTER_KIT_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class StarterKitLoadSummary:
    schema_version: int
    project_id: str
    status: str
    already_loaded: bool
    message: str
    dwh: dict[str, Any]
    graph: dict[str, Any]
    questions: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class StarterKitService:
    """Coordinates starter DWH, graph, question catalog, and MVG fixture loading."""

    def __init__(
        self,
        metadata_repository: MetadataRepository,
        graph_settings: Neo4jConnectionSettings,
        default_dwh_store_path: str | Path,
    ) -> None:
        self.metadata_repository = metadata_repository
        self.graph_settings = graph_settings
        self.default_dwh_store_path = Path(default_dwh_store_path)

    def load(
        self,
        project_id: str,
        dwh_store_path: str | Path | None = None,
        include_graph: bool = True,
    ) -> StarterKitLoadSummary:
        project = self.metadata_repository.get_project(project_id)
        dwh_summary = StarterDwhRepository(
            dwh_store_path or self.default_dwh_store_path
        ).load_seed_data()
        question_summary = load_starter_question_catalog(
            self.metadata_repository,
            project_id=project.id,
        )
        graph_summary = (
            StarterGraphRepository(self.graph_settings).load_seed_data().to_dict()
            if include_graph
            else {"skipped": True, "reason": "Graph load was skipped by request"}
        )
        already_loaded = (
            question_summary.created_question_count == 0 and question_summary.created_mvg_count == 0
        )

        return StarterKitLoadSummary(
            schema_version=STARTER_KIT_SCHEMA_VERSION,
            project_id=project.id,
            status="already_loaded" if already_loaded else "loaded",
            already_loaded=already_loaded,
            message=_load_message(already_loaded=already_loaded, include_graph=include_graph),
            dwh=dwh_summary.to_dict(),
            graph=graph_summary,
            questions=question_summary.to_dict(),
        )


def _load_message(already_loaded: bool, include_graph: bool) -> str:
    loaded_parts = "DWH seed, starter questions, and MVG artifacts"
    if include_graph:
        loaded_parts += ", plus starter graph concepts"

    if already_loaded:
        return (
            f"Starter kit was already loaded for this project; {loaded_parts} were refreshed "
            "idempotently. To rebuild from scratch, clean the local stores and load again."
        )
    return f"Starter kit loaded for this project: {loaded_parts} are available."
