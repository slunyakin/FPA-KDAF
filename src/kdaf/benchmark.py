"""Versioned public FP&A benchmark catalog and deterministic rubric."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from importlib import resources
from typing import Any


class BenchmarkError(ValueError):
    def __init__(self, message: str, code: str = "benchmark_error") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class BenchmarkCase:
    id: str
    category: str
    question_text: str
    expected_answer_status: str
    expected_evidence: dict[str, Any]
    requested_claim: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BenchmarkCatalog:
    schema_version: int
    benchmark_id: str
    name: str
    description: str
    rubric: dict[str, str]
    cases: tuple[BenchmarkCase, ...]

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["cases"] = [case.to_dict() for case in self.cases]
        return result


def fpna_benchmark_catalog() -> BenchmarkCatalog:
    resource = resources.files("kdaf").joinpath("resources/benchmarks/fpna_v1.json")
    try:
        payload = json.loads(resource.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BenchmarkError("FP&A benchmark catalog could not be loaded") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("cases"), list):
        raise BenchmarkError("FP&A benchmark catalog is malformed", "invalid_benchmark")
    try:
        cases = tuple(BenchmarkCase(**case) for case in payload["cases"])
        catalog = BenchmarkCatalog(
            schema_version=payload["schema_version"],
            benchmark_id=payload["benchmark_id"],
            name=payload["name"],
            description=payload["description"],
            rubric=payload["rubric"],
            cases=cases,
        )
    except (KeyError, TypeError) as exc:
        raise BenchmarkError("FP&A benchmark catalog is malformed", "invalid_benchmark") from exc
    if len({case.id for case in cases}) != len(cases):
        raise BenchmarkError("FP&A benchmark case IDs must be unique", "invalid_benchmark")
    return catalog


def grade_benchmark_case(
    benchmark_case: BenchmarkCase,
    evidence_packet: dict[str, Any],
    answer: dict[str, Any],
) -> dict[str, bool]:
    expected = benchmark_case.expected_evidence
    graph_ids = {
        node.get("id")
        for node in evidence_packet.get("graph_nodes", [])
        if isinstance(node, dict)
    }
    required_graph = set(expected.get("required_graph_concepts", []))
    provenance = evidence_packet.get("provenance", {})
    graph_nodes = evidence_packet.get("graph_nodes", [])
    entry_ids = {
        entry.get("id")
        for entry in evidence_packet.get("entries", [])
        if isinstance(entry, dict)
    }
    citations = answer.get("citations", [])
    metrics = {
        "required_graph_concepts": required_graph <= graph_ids,
        "financial_facts": not expected.get("financial_facts", False)
        or any(
            isinstance(entry, dict) and entry.get("kind") == "financial_fact"
            for entry in evidence_packet.get("entries", [])
        ),
        "provenance": not expected.get("provenance", False)
        or (
            bool(provenance.get("dwh_query_ids"))
            and isinstance(provenance.get("graph"), dict)
            and provenance["graph"].get("question_id")
            == evidence_packet.get("competency_question_id")
        ),
        "validation_state": not expected.get("validation_state", False)
        or (
            bool(graph_nodes)
            and all(isinstance(node.get("validation_state"), str) for node in graph_nodes)
        ),
        "answer_behavior": answer.get("status") == benchmark_case.expected_answer_status,
        "citations": (
            bool(citations) and all(citation in entry_ids for citation in citations)
            if benchmark_case.expected_answer_status == "grounded"
            else citations == []
        ),
    }
    return {**metrics, "passed": all(metrics.values())}
