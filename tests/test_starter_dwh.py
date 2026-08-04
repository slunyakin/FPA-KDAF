from __future__ import annotations

import sqlite3

import pytest

from kdaf.core import KdafCore
from kdaf.metadata import MetadataRepository
from kdaf.starter_dwh import StarterDwhError, StarterDwhRepository, starter_dwh_sql_artifacts


def test_starter_dwh_seed_populates_dimensions_and_financial_facts(tmp_path) -> None:
    repository = StarterDwhRepository(tmp_path / "starter_dwh.sqlite3")

    summary = repository.load_seed_data()

    assert summary.schema_version == 1
    assert summary.row_counts == {
        "fpna_entities": 1,
        "fpna_departments": 4,
        "fpna_accounts": 6,
        "fpna_periods": 3,
        "fpna_scenarios": 3,
        "fpna_facts": 24,
    }


def test_starter_dwh_seed_is_idempotent(tmp_path) -> None:
    repository = StarterDwhRepository(tmp_path / "starter_dwh.sqlite3")

    first = repository.load_seed_data()
    second = repository.load_seed_data()

    assert second.row_counts == first.row_counts


def test_sample_budget_vs_actuals_return_expected_financial_facts(tmp_path) -> None:
    repository = StarterDwhRepository(tmp_path / "starter_dwh.sqlite3")
    repository.load_seed_data()

    assert repository.sample_budget_vs_actuals() == [
        {
            "period_id": "2026-01",
            "account_name": "Revenue",
            "actual_amount": 100000,
            "budget_amount": 95000,
            "variance_amount": 5000,
        },
        {
            "period_id": "2026-02",
            "account_name": "Revenue",
            "actual_amount": 108000,
            "budget_amount": 102000,
            "variance_amount": 6000,
        },
        {
            "period_id": "2026-03",
            "account_name": "Revenue",
            "actual_amount": 115000,
            "budget_amount": 110000,
            "variance_amount": 5000,
        },
    ]


def test_sample_department_spend_returns_expected_march_spend(tmp_path) -> None:
    repository = StarterDwhRepository(tmp_path / "starter_dwh.sqlite3")
    repository.load_seed_data()

    assert repository.sample_department_spend() == [
        {"period_id": "2026-03", "department_name": "Engineering", "actual_spend": 57230},
        {"period_id": "2026-03", "department_name": "Sales", "actual_spend": 20500},
        {"period_id": "2026-03", "department_name": "G&A", "actual_spend": 15750},
        {"period_id": "2026-03", "department_name": "Marketing", "actual_spend": 15000},
    ]


def test_sample_queries_require_loaded_starter_dwh(tmp_path) -> None:
    repository = StarterDwhRepository(tmp_path / "empty.sqlite3")

    with pytest.raises(StarterDwhError, match="Starter DWH has not been loaded"):
        repository.sample_budget_vs_actuals()


def test_financial_numbers_are_not_stored_in_metadata_repository(tmp_path) -> None:
    metadata_store = tmp_path / "metadata.sqlite3"
    dwh_store = tmp_path / "starter_dwh.sqlite3"

    core = KdafCore(metadata_store_path=metadata_store)
    core.load_starter_dwh(dwh_store_path=dwh_store)

    metadata_tables = MetadataRepository(metadata_store).table_names()
    assert "fpna_facts" not in metadata_tables

    with sqlite3.connect(dwh_store) as connection:
        row = connection.execute("SELECT SUM(amount) FROM fpna_facts").fetchone()

    assert row[0] > 0


def test_postgres_sql_artifacts_are_packaged() -> None:
    artifacts = starter_dwh_sql_artifacts()

    assert "CREATE TABLE IF NOT EXISTS fpna_facts" in artifacts["schema"]
    assert "INSERT INTO fpna_facts" in artifacts["seed"]
    assert "fpna_budget_vs_actual_monthly" in artifacts["sample_queries"]
