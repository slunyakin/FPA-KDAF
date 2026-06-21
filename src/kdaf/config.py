"""Configuration loading for local-first KDAF runtimes."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any


class ConfigError(ValueError):
    """Raised when KDAF configuration cannot be loaded or validated."""


@dataclass(frozen=True)
class RuntimeConfig:
    environment: str = "local"
    log_level: str = "INFO"


@dataclass(frozen=True)
class DatabaseConfig:
    host: str
    port: int
    database: str
    user: str
    password: str
    role: str

    @property
    def url(self) -> str:
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"


@dataclass(frozen=True)
class Neo4jConfig:
    uri: str
    user: str
    password: str
    database: str = "neo4j"


@dataclass(frozen=True)
class KdafConfig:
    runtime: RuntimeConfig
    metadata_db: DatabaseConfig
    dwh_db: DatabaseConfig
    neo4j: Neo4jConfig


DEFAULT_CONFIG = KdafConfig(
    runtime=RuntimeConfig(),
    metadata_db=DatabaseConfig(
        host="localhost",
        port=5432,
        database="kdaf_metadata",
        user="kdaf_metadata",
        password="kdaf_metadata_password",
        role="metadata",
    ),
    dwh_db=DatabaseConfig(
        host="localhost",
        port=5433,
        database="kdaf_financial_dwh",
        user="kdaf_dwh",
        password="kdaf_dwh_password",
        role="financial_dwh",
    ),
    neo4j=Neo4jConfig(
        uri="bolt://localhost:7687",
        user="neo4j",
        password="kdaf_neo4j_password",
    ),
)

ENV_OVERRIDES = {
    "KDAF_ENV": ("runtime", "environment"),
    "KDAF_LOG_LEVEL": ("runtime", "log_level"),
    "KDAF_METADATA_DB_HOST": ("metadata_db", "host"),
    "KDAF_METADATA_DB_PORT": ("metadata_db", "port"),
    "KDAF_METADATA_DB_NAME": ("metadata_db", "database"),
    "KDAF_METADATA_DB_USER": ("metadata_db", "user"),
    "KDAF_METADATA_DB_PASSWORD": ("metadata_db", "password"),
    "KDAF_DWH_DB_HOST": ("dwh_db", "host"),
    "KDAF_DWH_DB_PORT": ("dwh_db", "port"),
    "KDAF_DWH_DB_NAME": ("dwh_db", "database"),
    "KDAF_DWH_DB_USER": ("dwh_db", "user"),
    "KDAF_DWH_DB_PASSWORD": ("dwh_db", "password"),
    "KDAF_NEO4J_URI": ("neo4j", "uri"),
    "KDAF_NEO4J_USER": ("neo4j", "user"),
    "KDAF_NEO4J_PASSWORD": ("neo4j", "password"),
    "KDAF_NEO4J_DATABASE": ("neo4j", "database"),
}


def load_config(
    config_path: str | Path | None = None, environ: dict[str, str] | None = None
) -> KdafConfig:
    """Load KDAF configuration from defaults, an optional TOML file, and environment overrides."""

    env = os.environ if environ is None else environ
    config = DEFAULT_CONFIG

    if config_path is not None:
        config = _merge_file_config(config, Path(config_path))

    config = _merge_env_config(config, env)
    _validate_config(config)
    return config


def _merge_file_config(config: KdafConfig, config_path: Path) -> KdafConfig:
    if not config_path.exists():
        raise ConfigError(f"Config file does not exist: {config_path}")

    try:
        raw = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Config file is not valid TOML: {config_path}: {exc}") from exc

    return _merge_mapping(config, raw)


def _merge_env_config(config: KdafConfig, env: dict[str, str]) -> KdafConfig:
    updates: dict[str, dict[str, Any]] = {}
    for env_name, (section, field) in ENV_OVERRIDES.items():
        if env_name not in env:
            continue
        value = env[env_name]
        updates.setdefault(section, {})[field] = _coerce_value(section, field, value)

    return _merge_mapping(config, updates)


def _merge_mapping(config: KdafConfig, updates: dict[str, Any]) -> KdafConfig:
    allowed_sections = {"runtime", "metadata_db", "dwh_db", "neo4j"}
    unknown_sections = set(updates) - allowed_sections
    if unknown_sections:
        names = ", ".join(sorted(unknown_sections))
        raise ConfigError(f"Unknown config section(s): {names}")

    values: dict[str, Any] = {}
    for section in allowed_sections:
        current = getattr(config, section)
        section_updates = updates.get(section, {})
        if not section_updates:
            values[section] = current
            continue

        valid_fields = set(current.__dataclass_fields__)
        unknown_fields = set(section_updates) - valid_fields
        if unknown_fields:
            names = ", ".join(sorted(unknown_fields))
            raise ConfigError(f"Unknown config field(s) for {section}: {names}")

        coerced = {
            field: _coerce_value(section, field, value) for field, value in section_updates.items()
        }
        values[section] = replace(current, **coerced)

    return KdafConfig(**values)


def _coerce_value(section: str, field: str, value: Any) -> Any:
    if field == "port":
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise ConfigError(f"{section}.{field} must be an integer") from exc
    return value


def _validate_config(config: KdafConfig) -> None:
    _require_non_empty("runtime.environment", config.runtime.environment)
    _require_non_empty("runtime.log_level", config.runtime.log_level)

    for name in ("metadata_db", "dwh_db"):
        db = getattr(config, name)
        _require_non_empty(f"{name}.host", db.host)
        _require_non_empty(f"{name}.database", db.database)
        _require_non_empty(f"{name}.user", db.user)
        _require_non_empty(f"{name}.password", db.password)
        if db.port < 1 or db.port > 65535:
            raise ConfigError(f"{name}.port must be between 1 and 65535")

    if (
        config.metadata_db.database == config.dwh_db.database
        and config.metadata_db.port == config.dwh_db.port
    ):
        raise ConfigError("metadata_db and dwh_db must be logically separated")

    _require_non_empty("neo4j.uri", config.neo4j.uri)
    _require_non_empty("neo4j.user", config.neo4j.user)
    _require_non_empty("neo4j.password", config.neo4j.password)
    _require_non_empty("neo4j.database", config.neo4j.database)


def _require_non_empty(field: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{field} is required and cannot be empty")
