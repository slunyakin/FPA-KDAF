"""Semantic graph provenance links without financial values."""

from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from uuid import uuid4


class GraphError(ValueError):
    """Raised when graph provenance cannot be persisted."""


@dataclass(frozen=True)
class GraphProvenance:
    id: str
    context_type: str
    context_id: str
    relationship: str
    source_id: str
    batch_id: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


class GraphProvenanceRepository:
    """SQLite local adapter for Neo4j provenance relationships.

    Its schema intentionally has no value, amount, measure, or payload column.
    """

    def __init__(self, store_path: str | Path) -> None:
        self.store_path = Path(store_path)

    def initialize_schema(self) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS kdaf_graph_provenance (
                    id TEXT PRIMARY KEY,
                    context_type TEXT NOT NULL,
                    context_id TEXT NOT NULL,
                    relationship TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    batch_id TEXT NOT NULL,
                    UNIQUE(context_type, context_id, relationship, source_id, batch_id)
                )
                """
            )

    def link_source(
        self,
        *,
        source_id: str,
        batch_id: str,
        context_type: str = "SourceContext",
        context_id: str | None = None,
    ) -> GraphProvenance:
        self.initialize_schema()
        link = GraphProvenance(
            id=str(uuid4()),
            context_type=context_type,
            context_id=context_id or f"source:{source_id}",
            relationship="DERIVED_FROM",
            source_id=source_id,
            batch_id=batch_id,
        )
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO kdaf_graph_provenance
                        (id, context_type, context_id, relationship, source_id, batch_id)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    tuple(asdict(link).values()),
                )
        except sqlite3.DatabaseError as exc:
            raise GraphError("Graph provenance link could not be stored") from exc
        return link

    def list_for_batch(self, batch_id: str) -> list[GraphProvenance]:
        self.initialize_schema()
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM kdaf_graph_provenance WHERE batch_id = ? ORDER BY context_id, id",
                (batch_id,),
            ).fetchall()
        return [GraphProvenance(**dict(row)) for row in rows]

    def columns(self) -> set[str]:
        self.initialize_schema()
        with self._connect() as connection:
            rows = connection.execute("PRAGMA table_info(kdaf_graph_provenance)").fetchall()
        return {row["name"] for row in rows}

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.store_path)
        connection.row_factory = sqlite3.Row
        return connection
