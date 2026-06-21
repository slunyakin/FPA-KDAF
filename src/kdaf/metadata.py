"""Package metadata helpers."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import metadata as importlib_metadata


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
        version = "0.1.0"

    return PackageMetadata(name="kdaf", version=version)
