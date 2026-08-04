"""Starter FP&A data warehouse schema, seed data, and sample queries."""

from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass
from importlib import resources
from pathlib import Path
from typing import Any

STARTER_DWH_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class StarterDwhLoadSummary:
    schema_version: int
    dwh_store_path: str
    tables: list[str]
    row_counts: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class StarterDwhError(ValueError):
    """Raised when starter DWH setup or queries cannot be completed."""


class StarterDwhRepository:
    """SQLite-backed local execution harness for the FP&A starter DWH.

    The packaged SQL artifacts are Postgres-oriented. This repository keeps the first public slice
    runnable without adding a database driver dependency, while preserving the DWH boundary.
    """

    def __init__(self, store_path: str | Path) -> None:
        self.store_path = Path(store_path)

    def load_seed_data(self) -> StarterDwhLoadSummary:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(_sqlite_schema_sql())
            _seed_sqlite(connection)
            row_counts = {
                table: _count_rows(connection, table)
                for table in (
                    "fpna_entities",
                    "fpna_departments",
                    "fpna_accounts",
                    "fpna_periods",
                    "fpna_scenarios",
                    "fpna_facts",
                )
            }

        return StarterDwhLoadSummary(
            schema_version=STARTER_DWH_SCHEMA_VERSION,
            dwh_store_path=str(self.store_path),
            tables=list(row_counts),
            row_counts=row_counts,
        )

    def sample_budget_vs_actuals(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            _require_loaded(connection)
            rows = connection.execute(
                """
                SELECT period_id, account_name, actual_amount, budget_amount, variance_amount
                FROM fpna_budget_vs_actual_monthly
                WHERE account_id = 'revenue'
                ORDER BY period_id
                """
            ).fetchall()
        return [_row_to_dict(row) for row in rows]

    def sample_department_spend(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            _require_loaded(connection)
            rows = connection.execute(
                """
                SELECT period_id, department_name, actual_spend
                FROM fpna_department_spend_monthly
                WHERE period_id = '2026-03'
                ORDER BY actual_spend DESC, department_name
                """
            ).fetchall()
        return [_row_to_dict(row) for row in rows]

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.store_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection


def starter_dwh_sql_artifacts() -> dict[str, str]:
    """Return packaged Postgres SQL artifacts for the starter DWH."""

    root = resources.files("kdaf").joinpath("resources/starter_dwh")
    return {
        "schema": root.joinpath("schema.sql").read_text(encoding="utf-8"),
        "seed": root.joinpath("seed.sql").read_text(encoding="utf-8"),
        "sample_queries": root.joinpath("sample_queries.sql").read_text(encoding="utf-8"),
    }


def _sqlite_schema_sql() -> str:
    return """
    CREATE TABLE IF NOT EXISTS fpna_entities (
        entity_id TEXT PRIMARY KEY,
        entity_name TEXT NOT NULL,
        currency_code TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS fpna_departments (
        department_id TEXT PRIMARY KEY,
        department_name TEXT NOT NULL,
        parent_department_id TEXT REFERENCES fpna_departments(department_id)
    );

    CREATE TABLE IF NOT EXISTS fpna_accounts (
        account_id TEXT PRIMARY KEY,
        account_name TEXT NOT NULL,
        statement_section TEXT NOT NULL,
        normal_balance TEXT NOT NULL CHECK (normal_balance IN ('debit', 'credit')),
        is_driver INTEGER NOT NULL CHECK (is_driver IN (0, 1))
    );

    CREATE TABLE IF NOT EXISTS fpna_periods (
        period_id TEXT PRIMARY KEY,
        fiscal_year INTEGER NOT NULL,
        fiscal_quarter INTEGER NOT NULL,
        month_number INTEGER NOT NULL,
        month_name TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS fpna_scenarios (
        scenario_id TEXT PRIMARY KEY,
        scenario_name TEXT NOT NULL,
        scenario_type TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS fpna_facts (
        fact_id TEXT PRIMARY KEY,
        entity_id TEXT NOT NULL REFERENCES fpna_entities(entity_id),
        department_id TEXT NOT NULL REFERENCES fpna_departments(department_id),
        account_id TEXT NOT NULL REFERENCES fpna_accounts(account_id),
        period_id TEXT NOT NULL REFERENCES fpna_periods(period_id),
        scenario_id TEXT NOT NULL REFERENCES fpna_scenarios(scenario_id),
        amount NUMERIC NOT NULL,
        source_system TEXT NOT NULL,
        UNIQUE (entity_id, department_id, account_id, period_id, scenario_id)
    );

    CREATE VIEW IF NOT EXISTS fpna_budget_vs_actual_monthly AS
    SELECT
        actual.period_id,
        actual.account_id,
        account.account_name,
        SUM(actual.amount) AS actual_amount,
        SUM(budget.amount) AS budget_amount,
        SUM(actual.amount - budget.amount) AS variance_amount
    FROM fpna_facts AS actual
    JOIN fpna_facts AS budget
      ON budget.entity_id = actual.entity_id
     AND budget.department_id = actual.department_id
     AND budget.account_id = actual.account_id
     AND budget.period_id = actual.period_id
     AND budget.scenario_id = 'budget'
    JOIN fpna_accounts AS account
      ON account.account_id = actual.account_id
    WHERE actual.scenario_id = 'actual'
    GROUP BY actual.period_id, actual.account_id, account.account_name;

    CREATE VIEW IF NOT EXISTS fpna_department_spend_monthly AS
    SELECT
        fact.period_id,
        department.department_name,
        SUM(fact.amount) AS actual_spend
    FROM fpna_facts AS fact
    JOIN fpna_accounts AS account
      ON account.account_id = fact.account_id
    JOIN fpna_departments AS department
      ON department.department_id = fact.department_id
    WHERE fact.scenario_id = 'actual'
      AND account.statement_section = 'operating_expense'
    GROUP BY fact.period_id, department.department_name;
    """


def _seed_sqlite(connection: sqlite3.Connection) -> None:
    connection.executemany(
        """
        INSERT OR REPLACE INTO fpna_entities (entity_id, entity_name, currency_code)
        VALUES (?, ?, ?)
        """,
        [("acme-us", "Acme Software US", "USD")],
    )
    connection.executemany(
        """
        INSERT OR REPLACE INTO fpna_departments
            (department_id, department_name, parent_department_id)
        VALUES (?, ?, ?)
        """,
        [
            ("sales", "Sales", None),
            ("marketing", "Marketing", None),
            ("engineering", "Engineering", None),
            ("g_and_a", "G&A", None),
        ],
    )
    connection.executemany(
        """
        INSERT OR REPLACE INTO fpna_accounts
            (account_id, account_name, statement_section, normal_balance, is_driver)
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            ("revenue", "Revenue", "revenue", "credit", 0),
            ("cogs", "Cost of Goods Sold", "cost_of_revenue", "debit", 0),
            ("payroll", "Payroll Expense", "operating_expense", "debit", 0),
            ("cloud_hosting", "Cloud Hosting", "operating_expense", "debit", 0),
            ("marketing_spend", "Marketing Spend", "operating_expense", "debit", 0),
            ("headcount", "Headcount", "driver", "debit", 1),
        ],
    )
    connection.executemany(
        """
        INSERT OR REPLACE INTO fpna_periods
            (period_id, fiscal_year, fiscal_quarter, month_number, month_name)
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            ("2026-01", 2026, 1, 1, "January"),
            ("2026-02", 2026, 1, 2, "February"),
            ("2026-03", 2026, 1, 3, "March"),
        ],
    )
    connection.executemany(
        """
        INSERT OR REPLACE INTO fpna_scenarios (scenario_id, scenario_name, scenario_type)
        VALUES (?, ?, ?)
        """,
        [
            ("actual", "Actuals", "actual"),
            ("budget", "Board Budget", "plan"),
            ("forecast", "Q1 Forecast", "forecast"),
        ],
    )
    connection.executemany(
        """
        INSERT OR REPLACE INTO fpna_facts
            (
                fact_id,
                entity_id,
                department_id,
                account_id,
                period_id,
                scenario_id,
                amount,
                source_system
            )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        _starter_fact_rows(),
    )


def _starter_fact_rows() -> list[tuple[str, str, str, str, str, str, int, str]]:
    rows: list[tuple[str, str, str, str, str, str, int, str]] = []

    def add(
        department_id: str,
        account_id: str,
        period_id: str,
        scenario_id: str,
        amount: int,
    ) -> None:
        fact_id = f"acme-us:{department_id}:{account_id}:{period_id}:{scenario_id}"
        rows.append(
            (
                fact_id,
                "acme-us",
                department_id,
                account_id,
                period_id,
                scenario_id,
                amount,
                "kdaf_starter_seed",
            )
        )

    for period_id, actual, budget, forecast in (
        ("2026-01", 100000, 95000, 101000),
        ("2026-02", 108000, 102000, 109000),
        ("2026-03", 115000, 110000, 116000),
    ):
        add("sales", "revenue", period_id, "actual", actual)
        add("sales", "revenue", period_id, "budget", budget)
        add("sales", "revenue", period_id, "forecast", forecast)

    for period_id, sales, marketing, engineering, g_and_a in (
        ("2026-01", 18000, 12000, 46000, 15000),
        ("2026-02", 19000, 13500, 47000, 15250),
        ("2026-03", 20500, 15000, 48500, 15750),
    ):
        add("sales", "payroll", period_id, "actual", sales)
        add("marketing", "marketing_spend", period_id, "actual", marketing)
        add("engineering", "payroll", period_id, "actual", engineering)
        add("engineering", "cloud_hosting", period_id, "actual", round(engineering * 0.18))
        add("g_and_a", "payroll", period_id, "actual", g_and_a)

    return rows


def _count_rows(connection: sqlite3.Connection, table: str) -> int:
    row = connection.execute(f"SELECT COUNT(*) AS row_count FROM {table}").fetchone()
    return int(row["row_count"])


def _require_loaded(connection: sqlite3.Connection) -> None:
    row = connection.execute(
        """
        SELECT name FROM sqlite_master
        WHERE type = 'table' AND name = 'fpna_facts'
        """
    ).fetchone()
    if row is None:
        raise StarterDwhError("Starter DWH has not been loaded")


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return dict(row)
