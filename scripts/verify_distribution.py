#!/usr/bin/env python3
"""Validate KDAF wheel/sdist metadata, contents, and optional dependency boundaries."""

from __future__ import annotations

import argparse
import email.parser
import tarfile
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

REQUIRED_PACKAGE_FILES = frozenset(
    {
        "kdaf/__init__.py",
        "kdaf/_version.py",
        "kdaf/resources/benchmarks/fpna_v1.json",
        "kdaf/resources/starter_dwh/sample_queries.sql",
        "kdaf/resources/starter_dwh/schema.sql",
        "kdaf/resources/starter_dwh/seed.sql",
        "kdaf/resources/starter_graph/sample_queries.cypher",
        "kdaf/resources/starter_graph/seed.cypher",
        "kdaf/resources/starter_questions/catalog.json",
    }
)
REQUIRED_SDIST_ROOT_FILES = frozenset({"LICENSE", "PYPI.md", "pyproject.toml"})
FORBIDDEN_PARTS = frozenset(
    {
        ".env",
        ".git",
        ".kdaf",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "AGENTS.md",
        "README.md",
        "carp-manuscript-guidance.md",
    }
)


@dataclass(frozen=True)
class Archive:
    path: Path
    kind: str
    members: frozenset[str]
    metadata_text: str


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dist", type=Path, help="Directory containing one KDAF wheel and sdist")
    parser.add_argument(
        "--expected-tag",
        help="Optional immutable release tag, such as v0.6.0, that must match metadata",
    )
    return parser.parse_args()


def _one(paths: Iterable[Path], kind: str) -> Path:
    matches = sorted(paths)
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one {kind}; found {len(matches)}")
    return matches[0]


def _wheel(path: Path) -> Archive:
    with zipfile.ZipFile(path) as archive:
        members = frozenset(name.rstrip("/") for name in archive.namelist() if name.rstrip("/"))
        metadata_names = [name for name in members if name.endswith(".dist-info/METADATA")]
        metadata_name = _one((Path(name) for name in metadata_names), "wheel METADATA")
        metadata_text = archive.read(metadata_name.as_posix()).decode("utf-8")
    return Archive(path=path, kind="wheel", members=members, metadata_text=metadata_text)


def _sdist(path: Path) -> Archive:
    with tarfile.open(path, mode="r:gz") as archive:
        raw_members = [member.name.rstrip("/") for member in archive.getmembers() if member.name]
        roots = {PurePosixPath(name).parts[0] for name in raw_members}
        if len(roots) != 1:
            raise ValueError(f"Expected one sdist root directory; found {sorted(roots)}")
        root = next(iter(roots))
        members = frozenset(
            PurePosixPath(name).relative_to(root).as_posix()
            for name in raw_members
            if PurePosixPath(name).as_posix() != root
        )
        metadata_member = archive.extractfile(f"{root}/PKG-INFO")
        if metadata_member is None:
            raise ValueError("Source distribution does not contain PKG-INFO")
        metadata_text = metadata_member.read().decode("utf-8")
    return Archive(path=path, kind="sdist", members=members, metadata_text=metadata_text)


def _metadata(archive: Archive) -> tuple[str, str]:
    message = email.parser.Parser().parsestr(archive.metadata_text)
    name = message.get("Name", "")
    version = message.get("Version", "")
    if name != "kdaf":
        raise ValueError(f"{archive.kind} has unexpected project name: {name!r}")
    if not version:
        raise ValueError(f"{archive.kind} has no version")

    requirements = message.get_all("Requires-Dist", [])
    live_requirements = [
        requirement for requirement in requirements if requirement.startswith(("neo4j", "psycopg"))
    ]
    if not live_requirements or any("extra ==" not in item for item in live_requirements):
        raise ValueError(f"{archive.kind} must expose Neo4j/Postgres only through optional extras")
    extras = set(message.get_all("Provides-Extra", []))
    if not {"neo4j", "postgres", "all"}.issubset(extras):
        raise ValueError(f"{archive.kind} is missing live integration extras: {sorted(extras)}")
    return name, version


def _assert_safe_members(archive: Archive) -> None:
    violations = sorted(
        member
        for member in archive.members
        if FORBIDDEN_PARTS.intersection(PurePosixPath(member).parts)
    )
    if violations:
        raise ValueError(f"{archive.kind} contains forbidden files: {violations}")


def _assert_required_members(archive: Archive) -> None:
    if archive.kind == "wheel":
        required = REQUIRED_PACKAGE_FILES
    else:
        required = REQUIRED_SDIST_ROOT_FILES.union(
            {f"src/{member}" for member in REQUIRED_PACKAGE_FILES}
        )
    missing = sorted(required.difference(archive.members))
    if missing:
        raise ValueError(f"{archive.kind} is missing runtime files: {missing}")


def main() -> int:
    args = _arguments()
    if not args.dist.is_dir():
        raise SystemExit(f"Distribution directory does not exist: {args.dist}")

    wheel = _wheel(_one(args.dist.glob("kdaf-*.whl"), "wheel"))
    sdist = _sdist(_one(args.dist.glob("kdaf-*.tar.gz"), "source distribution"))
    versions = set()
    for archive in (wheel, sdist):
        _assert_safe_members(archive)
        _assert_required_members(archive)
        _, version = _metadata(archive)
        versions.add(version)
        print(f"Verified {archive.kind}: {archive.path.name} ({len(archive.members)} files)")

    if len(versions) != 1:
        raise SystemExit(f"Wheel and sdist versions do not match: {sorted(versions)}")
    version = next(iter(versions))
    if args.expected_tag:
        expected_version = args.expected_tag.removeprefix("v")
        if expected_version != version:
            raise SystemExit(
                f"Release tag {args.expected_tag!r} does not match package version {version!r}"
            )
    print(f"KDAF distribution verified: {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
