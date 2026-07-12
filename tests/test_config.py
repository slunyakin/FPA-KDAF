from __future__ import annotations

from pathlib import Path

import pytest

from kdaf import ConfigError, load_config


def test_config_loads_defaults_covering_all_runtime_services() -> None:
    config = load_config()

    assert config.runtime.environment == "local"
    assert config.runtime.metadata_store_path == ".kdaf/metadata.sqlite3"
    assert config.metadata_db.role == "metadata"
    assert config.metadata_db.database == "kdaf_metadata"
    assert config.metadata_db.port == 5432
    assert config.dwh_db.role == "financial_dwh"
    assert config.dwh_db.database == "kdaf_financial_dwh"
    assert config.dwh_db.port == 5433
    assert config.neo4j.uri == "bolt://localhost:7687"


def test_config_loads_example_file() -> None:
    config = load_config(Path("config/kdaf.example.toml"))

    assert config.runtime.log_level == "INFO"
    assert config.metadata_db.user == "kdaf_metadata"
    assert config.dwh_db.user == "kdaf_dwh"
    assert config.neo4j.database == "neo4j"


def test_environment_overrides_metadata_dwh_neo4j_and_runtime_settings() -> None:
    config = load_config(
        environ={
            "KDAF_ENV": "test",
            "KDAF_LOG_LEVEL": "DEBUG",
            "KDAF_METADATA_STORE_PATH": "/tmp/kdaf-test.sqlite3",
            "KDAF_METADATA_DB_HOST": "metadata.internal",
            "KDAF_METADATA_DB_PORT": "15432",
            "KDAF_METADATA_DB_NAME": "metadata_test",
            "KDAF_METADATA_DB_USER": "metadata_user",
            "KDAF_METADATA_DB_PASSWORD": "metadata_secret",
            "KDAF_DWH_DB_HOST": "dwh.internal",
            "KDAF_DWH_DB_PORT": "15433",
            "KDAF_DWH_DB_NAME": "dwh_test",
            "KDAF_DWH_DB_USER": "dwh_user",
            "KDAF_DWH_DB_PASSWORD": "dwh_secret",
            "KDAF_NEO4J_URI": "bolt://graph.internal:7687",
            "KDAF_NEO4J_USER": "graph_user",
            "KDAF_NEO4J_PASSWORD": "graph_secret",
            "KDAF_NEO4J_DATABASE": "kdaf_graph",
        }
    )

    assert config.runtime.environment == "test"
    assert config.runtime.log_level == "DEBUG"
    assert config.runtime.metadata_store_path == "/tmp/kdaf-test.sqlite3"
    assert config.metadata_db.host == "metadata.internal"
    assert config.metadata_db.port == 15432
    assert config.metadata_db.database == "metadata_test"
    assert config.metadata_db.user == "metadata_user"
    assert config.metadata_db.password == "metadata_secret"
    assert config.dwh_db.host == "dwh.internal"
    assert config.dwh_db.port == 15433
    assert config.dwh_db.database == "dwh_test"
    assert config.dwh_db.user == "dwh_user"
    assert config.dwh_db.password == "dwh_secret"
    assert config.neo4j.uri == "bolt://graph.internal:7687"
    assert config.neo4j.user == "graph_user"
    assert config.neo4j.password == "graph_secret"
    assert config.neo4j.database == "kdaf_graph"


def test_invalid_required_values_raise_clear_errors() -> None:
    with pytest.raises(ConfigError, match="metadata_db.password is required"):
        load_config(environ={"KDAF_METADATA_DB_PASSWORD": " "})


def test_invalid_ports_raise_clear_errors() -> None:
    with pytest.raises(ConfigError, match="dwh_db.port must be an integer"):
        load_config(environ={"KDAF_DWH_DB_PORT": "not-a-port"})


def test_metadata_db_and_dwh_must_be_logically_separated() -> None:
    with pytest.raises(ConfigError, match="metadata_db and dwh_db must be logically separated"):
        load_config(
            environ={
                "KDAF_DWH_DB_PORT": "5432",
                "KDAF_DWH_DB_NAME": "kdaf_metadata",
            }
        )
