"""Repeatable evaluation metrics for grounded FP&A workflows."""

from __future__ import annotations

from typing import Any


def grade_evaluation_case(
    evidence_packet: dict[str, Any],
    answer: dict[str, Any],
    refusal: dict[str, Any],
) -> dict[str, bool]:
    """Grade one case using deterministic, machine-readable checks."""

    entry_ids = {
        entry.get("id")
        for entry in evidence_packet.get("entries", [])
        if isinstance(entry, dict) and isinstance(entry.get("id"), str)
    }
    citations = answer.get("citations", [])
    graph_nodes = evidence_packet.get("graph_nodes", [])
    provenance = evidence_packet.get("provenance", {})
    metrics = {
        "retrieval_context_present": bool(graph_nodes),
        "grounding_evidence_present": any(
            isinstance(entry, dict) and entry.get("kind") == "financial_fact"
            for entry in evidence_packet.get("entries", [])
        ),
        "provenance_complete": bool(provenance.get("dwh_query_ids"))
        and bool(evidence_packet.get("competency_question_id")),
        "answer_citations_valid": answer.get("status") == "grounded"
        and bool(citations)
        and all(citation in entry_ids for citation in citations),
        "unsupported_claim_refused": refusal.get("status") == "insufficiently_supported"
        and refusal.get("citations") == [],
        "validation_state_complete": bool(graph_nodes)
        and all(
            isinstance(node, dict)
            and isinstance(node.get("validation_state"), str)
            and bool(node["validation_state"].strip())
            for node in graph_nodes
        ),
    }
    return {**metrics, "passed": all(metrics.values())}
