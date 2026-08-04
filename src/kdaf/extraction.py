"""CSV extraction into the isolated financial DWH boundary."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4


class ExtractionError(ValueError):
    """A safe, operator-facing extraction failure."""

    def __init__(self, message: str, code: str = "extraction_error") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class CsvPayload:
    columns: tuple[str, ...]
    rows: tuple[dict[str, str], ...]
    content_hash: str


@dataclass(frozen=True)
class DwhLoadResult:
    batch_id: str
    source_id: str
    row_count: int
    row_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["row_ids"] = list(self.row_ids)
        return result


class CsvExtractor:
    """Strict CSV reader that reports stable errors without exposing row contents."""

    def extract(self, locator: str | Path) -> CsvPayload:
        path = Path(locator)
        if not path.exists():
            raise ExtractionError("CSV source file was not found", "source_file_not_found")
        if not path.is_file():
            raise ExtractionError("CSV source locator is not a file", "invalid_source_locator")

        try:
            raw = path.read_bytes()
            text = raw.decode("utf-8-sig")
        except (OSError, UnicodeError) as exc:
            raise ExtractionError("CSV source could not be read", "source_read_error") from exc

        try:
            reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
            fieldnames = reader.fieldnames
            if not fieldnames or any(not name or not name.strip() for name in fieldnames):
                raise ExtractionError("CSV header is required", "invalid_csv")
            columns = tuple(name.strip() for name in fieldnames)
            if len(set(columns)) != len(columns):
                raise ExtractionError("CSV headers must be unique", "invalid_csv")

            rows: list[dict[str, str]] = []
            for row_number, row in enumerate(reader, start=2):
                if None in row or any(value is None for value in row.values()):
                    raise ExtractionError(
                        f"CSV row {row_number} does not match the header",
                        "invalid_csv",
                    )
                rows.append(
                    {column: row[fieldnames[index]] for index, column in enumerate(columns)}
                )
        except csv.Error as exc:
            raise ExtractionError("CSV source is malformed", "invalid_csv") from exc

        return CsvPayload(columns, tuple(rows), hashlib.sha256(raw).hexdigest())


class ExtractionDwhRepository:
    """SQLite local adapter for extracted rows owned by the separate Postgres DWH."""

    def __init__(self, store_path: str | Path) -> None:
        self.store_path = Path(store_path)

    def initialize_schema(self) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS kdaf_dwh_extraction_batches (
                    batch_id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    columns_json TEXT NOT NULL,
                    content_hash TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS kdaf_dwh_extracted_rows (
                    row_id TEXT PRIMARY KEY,
                    batch_id TEXT NOT NULL REFERENCES kdaf_dwh_extraction_batches(batch_id),
                    source_id TEXT NOT NULL,
                    row_number INTEGER NOT NULL,
                    data_json TEXT NOT NULL,
                    UNIQUE(batch_id, row_number)
                );
                """
            )

    def load(self, batch_id: str, source_id: str, payload: CsvPayload) -> DwhLoadResult:
        self.initialize_schema()
        row_ids: list[str] = []
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO kdaf_dwh_extraction_batches
                        (batch_id, source_id, columns_json, content_hash)
                    VALUES (?, ?, ?, ?)
                    """,
                    (batch_id, source_id, json.dumps(payload.columns), payload.content_hash),
                )
                for row_number, row in enumerate(payload.rows, start=1):
                    row_id = str(uuid4())
                    row_ids.append(row_id)
                    connection.execute(
                        """
                        INSERT INTO kdaf_dwh_extracted_rows
                            (row_id, batch_id, source_id, row_number, data_json)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (row_id, batch_id, source_id, row_number, json.dumps(row, sort_keys=True)),
                    )
        except sqlite3.DatabaseError as exc:
            raise ExtractionError(
                "Extracted rows could not be stored in the DWH", "dwh_load_error"
            ) from exc
        return DwhLoadResult(batch_id, source_id, len(row_ids), tuple(row_ids))

    def trace_batch(self, batch_id: str) -> dict[str, Any]:
        self.initialize_schema()
        with self._connect() as connection:
            batch = connection.execute(
                """
                SELECT batch_id, source_id, content_hash
                FROM kdaf_dwh_extraction_batches WHERE batch_id = ?
                """,
                (batch_id,),
            ).fetchone()
            if batch is None:
                raise ExtractionError(f"DWH batch not found: {batch_id}", "not_found")
            rows = connection.execute(
                """
                SELECT row_id, row_number FROM kdaf_dwh_extracted_rows
                WHERE batch_id = ? ORDER BY row_number
                """,
                (batch_id,),
            ).fetchall()
        return {
            "batch_id": batch["batch_id"],
            "source_id": batch["source_id"],
            "content_hash": batch["content_hash"],
            "rows": [dict(row) for row in rows],
        }

    def read_rows(self, batch_id: str) -> list[dict[str, str]]:
        """Read DWH values for tests and future DWH services; never called by graph code."""

        self.initialize_schema()
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT data_json FROM kdaf_dwh_extracted_rows
                WHERE batch_id = ? ORDER BY row_number
                """,
                (batch_id,),
            ).fetchall()
        return [json.loads(row["data_json"]) for row in rows]

    def table_columns(self, table: str) -> set[str]:
        self.initialize_schema()
        with self._connect() as connection:
            return {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.store_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection
