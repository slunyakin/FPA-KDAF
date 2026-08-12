"""Grounded answer generation with auditable local and HTTP-compatible providers."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol

from kdaf.metadata import MetadataError, MetadataRepository

_CITATION = re.compile(r"\[evidence:([^\]]+)\]")


class AnswerError(ValueError):
    """Stable answer-generation failure."""

    def __init__(self, message: str, code: str = "answer_error") -> None:
        super().__init__(message)
        self.code = code


class AnswerProvider(Protocol):
    name: str

    def generate(self, prompt: str, model: str, parameters: dict[str, Any]) -> str: ...


@dataclass(frozen=True)
class DeterministicGroundedProvider:
    """Network-free provider used by the public demo and repeatable tests."""

    evidence_packet: dict[str, Any]
    name: str = "deterministic"

    def generate(self, prompt: str, model: str, parameters: dict[str, Any]) -> str:
        del prompt, model, parameters
        financial_entries = [
            entry
            for entry in self.evidence_packet.get("entries", [])
            if entry.get("kind") == "financial_fact"
        ]
        if not financial_entries:
            return "Insufficient evidence: the packet contains no financial facts."
        statements = []
        for entry in financial_entries:
            values = ", ".join(f"{key}={value}" for key, value in entry["data"].items())
            statements.append(f"{values} [evidence:{entry['id']}]")
        return "Grounded DWH result: " + "; ".join(statements)


class OpenAICompatibleProvider:
    """Small adapter for OpenAI-compatible chat endpoints, including local gateways."""

    name = "openai-compatible"

    def __init__(self, base_url: str, api_key: str | None = None, timeout: float = 30) -> None:
        if not isinstance(base_url, str) or not base_url.startswith(("http://", "https://")):
            raise AnswerError("Provider base URL must use http or https", "invalid_provider")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def generate(self, prompt: str, model: str, parameters: dict[str, Any]) -> str:
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            **parameters,
        }
        response = self._post("/v1/chat/completions", payload)
        try:
            return str(response["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise AnswerError("Provider returned an invalid response", "provider_error") from exc

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = urllib.request.Request(
            self.base_url + path,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                decoded = json.loads(response.read().decode("utf-8"))
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            raise AnswerError("Provider request failed", "provider_unavailable") from exc
        if not isinstance(decoded, dict):
            raise AnswerError("Provider returned an invalid response", "provider_error")
        return decoded


class OllamaProvider(OpenAICompatibleProvider):
    """Adapter for Ollama's native generation endpoint."""

    name = "ollama"

    def generate(self, prompt: str, model: str, parameters: dict[str, Any]) -> str:
        response = self._post(
            "/api/generate",
            {"model": model, "prompt": prompt, "stream": False, "options": parameters},
        )
        output = response.get("response")
        if not isinstance(output, str):
            raise AnswerError("Provider returned an invalid response", "provider_error")
        return output


class GroundedAnswerService:
    """Generate and validate cited answers from one evidence packet."""

    def __init__(self, metadata: MetadataRepository) -> None:
        self.metadata = metadata

    def generate(
        self,
        evidence_packet: dict[str, Any],
        provider: AnswerProvider,
        *,
        model: str,
        parameters: dict[str, Any] | None = None,
        requested_claim: str | None = None,
    ) -> dict[str, Any]:
        _validate_evidence_packet(evidence_packet)
        try:
            project = self.metadata.get_project(evidence_packet["project_id"])
            run = self.metadata.get_run(evidence_packet["run_id"])
            question = self.metadata.get_competency_question(
                evidence_packet["competency_question_id"]
            )
        except MetadataError as exc:
            raise AnswerError(str(exc), exc.code) from exc
        if run.project_id != project.id or question.project_id != project.id:
            raise AnswerError(
                "Evidence packet project, run, and competency question do not match",
                "invalid_id",
            )
        cleaned_parameters = {} if parameters is None else parameters
        if not isinstance(cleaned_parameters, dict):
            raise AnswerError("Provider parameters must be an object", "invalid_input")
        if not isinstance(model, str) or not model.strip():
            raise AnswerError("Model is required", "missing_field")
        if requested_claim is not None and (
            not isinstance(requested_claim, str) or not requested_claim.strip()
        ):
            raise AnswerError("Requested claim must be a non-empty string", "invalid_input")
        prompt = _build_prompt(evidence_packet, requested_claim)
        if requested_claim and not _claim_is_supported(requested_claim, evidence_packet):
            output = "Insufficient evidence: the requested claim is not supported by this packet."
            result = {
                "status": "insufficiently_supported",
                "answer": output,
                "citations": [],
            }
        else:
            output = provider.generate(prompt, model.strip(), cleaned_parameters)
            if not isinstance(output, str):
                raise AnswerError("Provider returned an invalid response", "provider_error")
            citations = _CITATION.findall(output)
            valid_entry_ids = {
                entry["id"] for entry in evidence_packet["entries"] if isinstance(entry, dict)
            }
            if not citations or any(citation not in valid_entry_ids for citation in citations):
                result = {
                    "status": "insufficiently_supported",
                    "answer": (
                        "Insufficient evidence: provider output did not contain valid "
                        "evidence citations."
                    ),
                    "citations": [],
                }
            else:
                result = {"status": "grounded", "answer": output, "citations": citations}
        audit = self.metadata.record_audit_event(
            "answer.generated",
            "run",
            evidence_packet["run_id"],
            {
                "evidence_packet_id": evidence_packet["id"],
                "project_id": evidence_packet["project_id"],
                "run_id": evidence_packet["run_id"],
                "prompt": prompt,
                "provider": provider.name,
                "model": model.strip(),
                "parameters": cleaned_parameters,
                "output": result["answer"],
                "status": result["status"],
            },
        )
        return {
            **result,
            "evidence_packet_id": evidence_packet["id"],
            "project_id": evidence_packet["project_id"],
            "run_id": evidence_packet["run_id"],
            "provider": provider.name,
            "model": model.strip(),
            "audit_event_id": audit.id,
        }


def _validate_evidence_packet(packet: Any) -> None:
    if not isinstance(packet, dict):
        raise AnswerError("Evidence packet must be an object", "invalid_input")
    for field in ("id", "project_id", "run_id", "competency_question_id", "question"):
        if not isinstance(packet.get(field), str) or not packet[field].strip():
            raise AnswerError(f"Evidence packet field is required: {field}", "missing_field")
    entries = packet.get("entries")
    if not isinstance(entries, list):
        raise AnswerError("Evidence packet entries must be a list", "invalid_input")
    entry_ids: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise AnswerError("Evidence packet entries must be objects", "invalid_input")
        if not isinstance(entry.get("id"), str) or not entry["id"].strip():
            raise AnswerError("Evidence packet entry ID is required", "missing_field")
        if not isinstance(entry.get("kind"), str) or not entry["kind"].strip():
            raise AnswerError("Evidence packet entry kind is required", "missing_field")
        entry_ids.append(entry["id"])
    if len(entry_ids) != len(set(entry_ids)):
        raise AnswerError("Evidence packet entry IDs must be unique", "invalid_input")


def _build_prompt(packet: dict[str, Any], requested_claim: str | None) -> str:
    claim = requested_claim or packet["question"]
    evidence = json.dumps(packet["entries"], sort_keys=True, separators=(",", ":"))
    return (
        "Answer only from the evidence entries below. Cite every factual claim as "
        "[evidence:<entry-id>]. If the evidence is insufficient, say so.\n"
        f"Question: {claim}\nEvidence: {evidence}"
    )


def _claim_is_supported(claim: str, packet: dict[str, Any]) -> bool:
    ignored = {"what", "where", "which", "this", "that"}
    words = {word for word in re.findall(r"[a-z]{4,}", claim.lower()) if word not in ignored}
    corpus = (packet["question"] + " " + json.dumps(packet["entries"])).lower()
    return bool(words) and sum(word in corpus for word in words) >= min(2, len(words))
