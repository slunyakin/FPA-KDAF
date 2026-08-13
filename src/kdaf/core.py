"""Shared core APIs used by the CLI and MCP-style tool server."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from kdaf.answers import (
    AnswerError,
    DeterministicGroundedProvider,
    GroundedAnswerService,
    OllamaProvider,
    OpenAICompatibleProvider,
)
from kdaf.benchmark import (
    BenchmarkError,
    fpna_benchmark_catalog,
    grade_benchmark_case,
)
from kdaf.config import KdafConfig, load_config
from kdaf.evaluation import grade_evaluation_case
from kdaf.extraction import CsvExtractor, ExtractionDwhRepository, ExtractionError
from kdaf.graph import GraphError, GraphProvenanceRepository
from kdaf.metadata import MetadataError, MetadataRepository, package_metadata
from kdaf.retrieval import (
    CarpRetrievalService,
    EvidencePacketBuilder,
    Neo4jGraphContextProvider,
    PackagedGraphContextProvider,
    PostgresDwhQueryService,
    ReadOnlyDwhQueryService,
    RetrievalError,
    starter_question_for_text,
)
from kdaf.starter_dwh import StarterDwhError, StarterDwhRepository, starter_dwh_sql_artifacts
from kdaf.starter_graph import (
    Neo4jConnectionSettings,
    StarterGraphError,
    StarterGraphRepository,
    starter_graph_cypher_artifacts,
)
from kdaf.starter_kit import StarterKitService
from kdaf.starter_questions import (
    StarterQuestionCatalogError,
    load_starter_question_catalog,
    starter_question_catalog,
)


class KdafError(ValueError):
    """Stable application error for operator and agent surfaces."""

    def __init__(self, message: str, code: str = "kdaf_error") -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class HealthStatus:
    status: str
    service: str
    version: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


class KdafCore:
    """Shared service facade for KDAF operator and agent entrypoints."""

    def __init__(
        self,
        config: KdafConfig | None = None,
        config_path: str | Path | None = None,
        metadata_store_path: str | Path | None = None,
        dwh_store_path: str | Path | None = None,
        graph_store_path: str | Path | None = None,
    ) -> None:
        if config is not None and config_path is not None:
            raise KdafError("config and config_path cannot both be provided")

        self.config = config if config is not None else load_config(config_path)
        store_path = metadata_store_path or self.config.runtime.metadata_store_path
        self.metadata = MetadataRepository(store_path)
        self.metadata.initialize_schema()
        base_path = self.metadata.store_path.parent
        self._configured_dwh_store_path = dwh_store_path
        self.extraction_dwh = ExtractionDwhRepository(
            dwh_store_path or base_path / "extraction_dwh.sqlite3"
        )
        self.graph = GraphProvenanceRepository(
            graph_store_path or base_path / "graph_context.sqlite3"
        )

    def health(self) -> dict[str, str]:
        metadata = package_metadata()
        return HealthStatus(status="ok", service=metadata.name, version=metadata.version).to_dict()

    def config_summary(self) -> dict[str, Any]:
        return {
            "runtime": {
                "environment": self.config.runtime.environment,
                "log_level": self.config.runtime.log_level,
                "metadata_store_path": self.config.runtime.metadata_store_path,
            },
            "metadata_db": _safe_database_summary(self.config.metadata_db),
            "dwh_db": _safe_database_summary(self.config.dwh_db),
            "neo4j": {
                "uri": self.config.neo4j.uri,
                "user": self.config.neo4j.user,
                "database": self.config.neo4j.database,
            },
        }

    def create_project(self, name: str, description: str = "") -> dict[str, str]:
        try:
            return self.metadata.create_project(name=name, description=description).to_dict()
        except MetadataError as exc:
            raise KdafError(str(exc), code=_metadata_error_code(exc)) from exc

    def list_projects(self) -> list[dict[str, str]]:
        return [project.to_dict() for project in self.metadata.list_projects()]

    def get_project(self, project_id: str) -> dict[str, str]:
        try:
            return self.metadata.get_project(project_id).to_dict()
        except MetadataError as exc:
            raise KdafError(str(exc), code=_metadata_error_code(exc)) from exc

    def create_run(self, project_id: str, status: str = "created") -> dict[str, str]:
        try:
            return self.metadata.create_run(project_id=project_id, status=status).to_dict()
        except MetadataError as exc:
            raise KdafError(str(exc), code=_metadata_error_code(exc)) from exc

    def list_runs(self, project_id: str | None = None) -> list[dict[str, str]]:
        try:
            return [run.to_dict() for run in self.metadata.list_runs(project_id=project_id)]
        except MetadataError as exc:
            raise KdafError(str(exc), code=_metadata_error_code(exc)) from exc

    def get_run(self, run_id: str) -> dict[str, str]:
        try:
            return self.metadata.get_run(run_id).to_dict()
        except MetadataError as exc:
            raise KdafError(str(exc), code=_metadata_error_code(exc)) from exc

    def create_competency_question(
        self,
        project_id: str,
        question_text: str,
        business_context: str = "",
    ) -> dict[str, str]:
        try:
            return self.metadata.create_competency_question(
                project_id=project_id,
                question_text=question_text,
                business_context=business_context,
            ).to_dict()
        except MetadataError as exc:
            raise KdafError(str(exc), code=_metadata_error_code(exc)) from exc

    def list_competency_questions(
        self,
        project_id: str | None = None,
    ) -> list[dict[str, str]]:
        try:
            return [
                question.to_dict()
                for question in self.metadata.list_competency_questions(project_id=project_id)
            ]
        except MetadataError as exc:
            raise KdafError(str(exc), code=_metadata_error_code(exc)) from exc

    def get_competency_question(self, question_id: str) -> dict[str, str]:
        try:
            return self.metadata.get_competency_question(question_id).to_dict()
        except MetadataError as exc:
            raise KdafError(str(exc), code=_metadata_error_code(exc)) from exc

    def create_mvg_artifact(
        self,
        project_id: str,
        name: str,
        description: str = "",
        question_ids: list[str] | None = None,
        concept_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        try:
            return self.metadata.create_mvg_artifact(
                project_id=project_id,
                name=name,
                description=description,
                question_ids=question_ids,
                concept_ids=concept_ids,
            ).to_dict()
        except MetadataError as exc:
            raise KdafError(str(exc), code=_metadata_error_code(exc)) from exc

    def list_mvg_artifacts(self, project_id: str | None = None) -> list[dict[str, Any]]:
        try:
            return [artifact.to_dict() for artifact in self.metadata.list_mvg_artifacts(project_id)]
        except MetadataError as exc:
            raise KdafError(str(exc), code=_metadata_error_code(exc)) from exc

    def get_mvg_artifact(self, mvg_id: str) -> dict[str, Any]:
        try:
            return self.metadata.get_mvg_artifact(mvg_id).to_dict()
        except MetadataError as exc:
            raise KdafError(str(exc), code=_metadata_error_code(exc)) from exc

    def add_question_to_mvg(self, mvg_id: str, question_id: str) -> dict[str, Any]:
        try:
            return self.metadata.add_question_to_mvg(mvg_id, question_id).to_dict()
        except MetadataError as exc:
            raise KdafError(str(exc), code=_metadata_error_code(exc)) from exc

    def add_concept_to_mvg(self, mvg_id: str, concept_id: str) -> dict[str, Any]:
        try:
            return self.metadata.add_concept_to_mvg(mvg_id, concept_id).to_dict()
        except MetadataError as exc:
            raise KdafError(str(exc), code=_metadata_error_code(exc)) from exc

    def register_source(
        self,
        name: str,
        locator: str,
        source_type: str = "csv",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            return self.metadata.create_source(name, source_type, locator, metadata).to_dict()
        except MetadataError as exc:
            raise _core_metadata_error(exc) from exc

    def list_sources(self) -> list[dict[str, Any]]:
        return [source.to_dict() for source in self.metadata.list_sources()]

    def get_source(self, source_id: str) -> dict[str, Any]:
        try:
            return self.metadata.get_source(source_id).to_dict()
        except MetadataError as exc:
            raise _core_metadata_error(exc) from exc

    def extract_source(self, source_id: str) -> dict[str, Any]:
        try:
            source = self.metadata.get_source(source_id)
            batch = self.metadata.start_extraction(source.id)
        except MetadataError as exc:
            raise _core_metadata_error(exc) from exc

        try:
            payload = CsvExtractor().extract(source.locator)
            dwh_result = self.extraction_dwh.load(batch.id, source.id, payload)
            self.metadata.update_source_hash(source.id, payload.content_hash)
            self.metadata.add_provenance_link(
                source.id, batch.id, "dwh", "extraction_batch", batch.id
            )
            for row_id in dwh_result.row_ids:
                self.metadata.add_provenance_link(
                    source.id, batch.id, "dwh", "extracted_row", row_id
                )
            graph_link = self.graph.link_source(source_id=source.id, batch_id=batch.id)
            self.metadata.add_provenance_link(
                source.id, batch.id, "neo4j", "semantic_context", graph_link.context_id
            )
            completed = self.metadata.finish_extraction(
                batch.id, status="completed", row_count=dwh_result.row_count
            )
        except ExtractionError as exc:
            self.metadata.finish_extraction(
                batch.id,
                status="failed",
                error_code=exc.code,
                error_message=str(exc),
            )
            raise KdafError(str(exc), code=exc.code) from exc
        except (GraphError, MetadataError) as exc:
            self.metadata.finish_extraction(
                batch.id,
                status="failed",
                error_code="provenance_error",
                error_message="Extraction provenance could not be stored",
            )
            raise KdafError(
                "Extraction provenance could not be stored", code="provenance_error"
            ) from exc

        return {
            **completed.to_dict(),
            "content_hash": payload.content_hash,
            "provenance_link_count": dwh_result.row_count + 2,
        }

    def get_extraction(self, batch_id: str) -> dict[str, Any]:
        try:
            return self.metadata.get_extraction(batch_id).to_dict()
        except MetadataError as exc:
            raise _core_metadata_error(exc) from exc

    def list_extractions(self, source_id: str | None = None) -> list[dict[str, Any]]:
        try:
            return [batch.to_dict() for batch in self.metadata.list_extractions(source_id)]
        except MetadataError as exc:
            raise _core_metadata_error(exc) from exc

    def get_provenance(self, batch_id: str) -> dict[str, Any]:
        try:
            batch = self.metadata.get_extraction(batch_id)
            source = self.metadata.get_source(batch.source_id)
            links = self.metadata.list_provenance_links(batch.id)
            dwh_trace = self.extraction_dwh.trace_batch(batch.id)
            graph_links = self.graph.list_for_batch(batch.id)
        except MetadataError as exc:
            raise _core_metadata_error(exc) from exc
        except ExtractionError as exc:
            raise KdafError(str(exc), code=exc.code) from exc
        return {
            "source": source.to_dict(),
            "extraction": batch.to_dict(),
            "metadata_links": [link.to_dict() for link in links],
            "dwh": dwh_trace,
            "graph": [link.to_dict() for link in graph_links],
        }

    def enqueue_validation(
        self,
        subject_type: str,
        subject_id: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            return self.metadata.enqueue_validation(subject_type, subject_id, payload).to_dict()
        except MetadataError as exc:
            raise _core_metadata_error(exc) from exc

    def list_validations(self, status: str | None = None) -> list[dict[str, Any]]:
        try:
            return [item.to_dict() for item in self.metadata.list_validations(status)]
        except MetadataError as exc:
            raise _core_metadata_error(exc) from exc

    def get_validation(self, validation_id: str) -> dict[str, Any]:
        try:
            return self.metadata.get_validation(validation_id).to_dict()
        except MetadataError as exc:
            raise _core_metadata_error(exc) from exc

    def approve_validation(
        self, validation_id: str, reviewer: str, comment: str = ""
    ) -> dict[str, Any]:
        return self._decide_validation(validation_id, "approved", reviewer, comment)

    def reject_validation(
        self, validation_id: str, reviewer: str, comment: str = ""
    ) -> dict[str, Any]:
        return self._decide_validation(validation_id, "rejected", reviewer, comment)

    def comment_validation(self, validation_id: str, reviewer: str, comment: str) -> dict[str, Any]:
        try:
            return self.metadata.comment_validation(validation_id, reviewer, comment).to_dict()
        except MetadataError as exc:
            raise _core_metadata_error(exc) from exc

    def _decide_validation(
        self, validation_id: str, status: str, reviewer: str, comment: str
    ) -> dict[str, Any]:
        try:
            return self.metadata.decide_validation(
                validation_id, status, reviewer, comment
            ).to_dict()
        except MetadataError as exc:
            raise _core_metadata_error(exc) from exc

    def starter_dwh_schema(self) -> dict[str, str]:
        artifacts = starter_dwh_sql_artifacts()
        return {
            "dialect": "postgres",
            "schema_sql": artifacts["schema"],
            "seed_sql": artifacts["seed"],
            "sample_queries_sql": artifacts["sample_queries"],
        }

    def load_starter_dwh(self, dwh_store_path: str | Path | None = None) -> dict[str, Any]:
        repository = StarterDwhRepository(dwh_store_path or self._default_starter_dwh_path())
        try:
            return repository.load_seed_data().to_dict()
        except StarterDwhError as exc:
            raise KdafError(str(exc), code="starter_dwh_error") from exc

    def starter_dwh_sample_facts(self, dwh_store_path: str | Path | None = None) -> dict[str, Any]:
        repository = StarterDwhRepository(dwh_store_path or self._default_starter_dwh_path())
        try:
            return {
                "budget_vs_actuals": repository.sample_budget_vs_actuals(),
                "department_spend": repository.sample_department_spend(),
            }
        except StarterDwhError as exc:
            raise KdafError(str(exc), code="starter_dwh_not_loaded") from exc

    def query_dwh(
        self,
        query_id: str,
        parameters: dict[str, Any] | None = None,
        dwh_store_path: str | Path | None = None,
    ) -> dict[str, Any]:
        """Run one controlled query against the separate financial DWH boundary."""

        try:
            result = self._dwh_query_service(dwh_store_path).execute(query_id, parameters)
            self.metadata.record_audit_event(
                "dwh.query.executed",
                "dwh_query",
                result.id,
                {
                    "query_id": result.query_id,
                    "statement_fingerprint": result.statement_fingerprint,
                    "parameters": result.parameters,
                    "row_count": result.row_count,
                    "duration_ms": result.duration_ms,
                    "mode": result.mode,
                },
            )
            return result.to_dict()
        except RetrievalError as exc:
            raise KdafError(str(exc), code=exc.code) from exc
        except MetadataError as exc:
            raise _core_metadata_error(exc) from exc

    def retrieve_carp_context(
        self,
        question_id: str,
        *,
        offline_graph: bool = False,
    ) -> dict[str, Any]:
        """Retrieve relevant graph semantics, provenance links, and validation state."""

        provider = (
            PackagedGraphContextProvider()
            if offline_graph
            else Neo4jGraphContextProvider(self._neo4j_connection_settings())
        )
        try:
            return CarpRetrievalService(self.metadata, provider).retrieve(question_id)
        except RetrievalError as exc:
            raise KdafError(str(exc), code=exc.code) from exc

    def build_evidence_packet(
        self,
        question_id: str,
        run_id: str,
        *,
        dwh_store_path: str | Path | None = None,
        offline_graph: bool = False,
    ) -> dict[str, Any]:
        try:
            question = self.metadata.get_competency_question(question_id).to_dict()
            run = self.metadata.get_run(run_id).to_dict()
            if question["project_id"] != run["project_id"]:
                raise RetrievalError(
                    "Run and competency question must share a project", "invalid_id"
                )
            starter_question = starter_question_for_text(question["question_text"])
            graph_context = self.retrieve_carp_context(question_id, offline_graph=offline_graph)
            dwh_result = self._dwh_query_service(dwh_store_path).execute(starter_question.category)
            self.metadata.record_audit_event(
                "dwh.query.executed",
                "dwh_query",
                dwh_result.id,
                {
                    "query_id": dwh_result.query_id,
                    "statement_fingerprint": dwh_result.statement_fingerprint,
                    "parameters": dwh_result.parameters,
                    "row_count": dwh_result.row_count,
                    "duration_ms": dwh_result.duration_ms,
                    "mode": dwh_result.mode,
                    "run_id": run["id"],
                },
            )
            packet = EvidencePacketBuilder().build(
                question=question,
                run=run,
                dwh_query=dwh_result,
                graph_context=graph_context,
            )
            self.metadata.record_audit_event(
                "evidence_packet.built",
                "evidence_packet",
                packet["id"],
                {
                    "project_id": packet["project_id"],
                    "run_id": packet["run_id"],
                    "competency_question_id": packet["competency_question_id"],
                    "dwh_query_ids": packet["provenance"]["dwh_query_ids"],
                },
            )
            return packet
        except MetadataError as exc:
            raise _core_metadata_error(exc) from exc
        except RetrievalError as exc:
            raise KdafError(str(exc), code=exc.code) from exc

    def generate_grounded_answer(
        self,
        evidence_packet: dict[str, Any],
        *,
        provider_name: str = "deterministic",
        model: str = "kdaf-grounded-demo",
        parameters: dict[str, Any] | None = None,
        requested_claim: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
    ) -> dict[str, Any]:
        try:
            if provider_name == "deterministic":
                provider = DeterministicGroundedProvider(evidence_packet)
            elif provider_name == "ollama":
                provider = OllamaProvider(base_url or "http://localhost:11434")
            elif provider_name == "openai-compatible":
                if base_url is None:
                    raise AnswerError(
                        "Provider base URL is required for openai-compatible",
                        "missing_field",
                    )
                provider = OpenAICompatibleProvider(base_url, api_key=api_key)
            else:
                raise AnswerError(f"Unknown answer provider: {provider_name}", "invalid_provider")
            return GroundedAnswerService(self.metadata).generate(
                evidence_packet,
                provider,
                model=model,
                parameters=parameters,
                requested_claim=requested_claim,
            )
        except AnswerError as exc:
            raise KdafError(str(exc), code=exc.code) from exc
        except MetadataError as exc:
            raise _core_metadata_error(exc) from exc

    def grounded_answer_demo(
        self,
        question_id: str,
        run_id: str,
        *,
        dwh_store_path: str | Path | None = None,
        offline_graph: bool = False,
    ) -> dict[str, Any]:
        packet = self.build_evidence_packet(
            question_id,
            run_id,
            dwh_store_path=dwh_store_path,
            offline_graph=offline_graph,
        )
        answer = self.generate_grounded_answer(packet)
        refusal = self.generate_grounded_answer(
            packet,
            requested_claim="What was the unsupported cash balance?",
        )
        return {
            "evidence_packet": packet,
            "answer": answer,
            "unsupported_claim": refusal,
            "architecture": {
                "financial_facts_store": "financial_dwh",
                "graph_stores_financial_facts": False,
                "graph_content": [
                    "meaning",
                    "relationships",
                    "relevance_context",
                    "provenance_links",
                    "validation_state",
                ],
            },
        }

    def run_evaluation(
        self,
        project_id: str,
        *,
        question_ids: list[str] | None = None,
        dwh_store_path: str | Path | None = None,
        offline_graph: bool = False,
    ) -> dict[str, Any]:
        """Evaluate starter questions and persist every case in framework metadata."""

        try:
            project = self.metadata.get_project(project_id)
            questions = self.metadata.list_competency_questions(project.id)
        except MetadataError as exc:
            raise _core_metadata_error(exc) from exc
        if question_ids is not None:
            if not isinstance(question_ids, list) or not all(
                isinstance(item, str) and item.strip() for item in question_ids
            ):
                raise KdafError(
                    "question_ids must be a list of non-empty strings", "invalid_input"
                )
            selected_ids = set(question_ids)
            selected = [question for question in questions if question.id in selected_ids]
            missing = sorted(selected_ids - {question.id for question in selected})
            if missing:
                raise KdafError(f"Competency question not found: {missing[0]}", "not_found")
            questions = selected
        if not questions:
            raise KdafError("No competency questions found for evaluation", "not_found")

        run = self.metadata.create_run(project.id, "evaluating")
        results = []
        for question in questions:
            try:
                starter_question_for_text(question.question_text)
                packet = self.build_evidence_packet(
                    question.id,
                    run.id,
                    dwh_store_path=dwh_store_path,
                    offline_graph=offline_graph,
                )
                answer = self.generate_grounded_answer(packet)
                refusal = self.generate_grounded_answer(
                    packet,
                    requested_claim="What was the unsupported cash balance?",
                )
                metrics = grade_evaluation_case(packet, answer, refusal)
                status = "passed" if metrics["passed"] else "failed"
                result = self.metadata.create_evaluation_result(
                    run.id,
                    question.id,
                    status,
                    metrics,
                    {
                        "competency_question_id": question.id,
                        "evidence_packet_id": packet["id"],
                        "answer_status": answer["status"],
                        "refusal_status": refusal["status"],
                    },
                )
            except KdafError as exc:
                result = self.metadata.create_evaluation_result(
                    run.id,
                    question.id,
                    "error",
                    {"passed": False},
                    {"competency_question_id": question.id},
                    {"code": exc.code, "message": exc.message},
                )
            results.append(result.to_dict())

        passed = sum(result["status"] == "passed" for result in results)
        return {
            "run": run.to_dict(),
            "status": "passed" if passed == len(results) else "failed",
            "summary": {
                "total": len(results),
                "passed": passed,
                "failed": len(results) - passed,
            },
            "results": results,
        }

    def list_evaluation_results(self, run_id: str | None = None) -> list[dict[str, Any]]:
        try:
            return [
                result.to_dict() for result in self.metadata.list_evaluation_results(run_id)
            ]
        except MetadataError as exc:
            raise _core_metadata_error(exc) from exc

    def get_evaluation_result(self, result_id: str) -> dict[str, Any]:
        try:
            return self.metadata.get_evaluation_result(result_id).to_dict()
        except MetadataError as exc:
            raise _core_metadata_error(exc) from exc

    def fpna_benchmark_catalog(self) -> dict[str, Any]:
        try:
            return fpna_benchmark_catalog().to_dict()
        except BenchmarkError as exc:
            raise KdafError(str(exc), exc.code) from exc

    def run_fpna_benchmark(
        self,
        project_id: str,
        *,
        case_ids: list[str] | None = None,
        dwh_store_path: str | Path | None = None,
        offline_graph: bool = False,
    ) -> dict[str, Any]:
        """Run the public FP&A benchmark and persist its per-case evidence."""

        try:
            project = self.metadata.get_project(project_id)
            catalog = fpna_benchmark_catalog()
        except MetadataError as exc:
            raise _core_metadata_error(exc) from exc
        except BenchmarkError as exc:
            raise KdafError(str(exc), exc.code) from exc
        cases = list(catalog.cases)
        if case_ids is not None:
            if not isinstance(case_ids, list) or not all(
                isinstance(item, str) and item.strip() for item in case_ids
            ):
                raise KdafError("case_ids must be a list of non-empty strings", "invalid_input")
            selected_ids = set(case_ids)
            cases = [case for case in cases if case.id in selected_ids]
            missing = sorted(selected_ids - {case.id for case in cases})
            if missing:
                raise KdafError(f"Benchmark case not found: {missing[0]}", "not_found")
        if not cases:
            raise KdafError("No benchmark cases selected", "missing_field")

        questions = {
            question.question_text: question
            for question in self.metadata.list_competency_questions(project.id)
        }
        run = self.metadata.create_run(project.id, "benchmarking")
        results = []
        for benchmark_case in cases:
            try:
                question = questions.get(benchmark_case.question_text)
                if question is None:
                    raise KdafError(
                        f"Benchmark competency question not found: {benchmark_case.category}",
                        "not_found",
                    )
                packet = self.build_evidence_packet(
                    question.id,
                    run.id,
                    dwh_store_path=dwh_store_path,
                    offline_graph=offline_graph,
                )
                answer = self.generate_grounded_answer(
                    packet, requested_claim=benchmark_case.requested_claim
                )
                metrics = grade_benchmark_case(benchmark_case, packet, answer)
                status = "passed" if metrics["passed"] else "failed"
                result = self.metadata.create_evaluation_result(
                    run.id,
                    benchmark_case.id,
                    status,
                    metrics,
                    {
                        "benchmark_id": catalog.benchmark_id,
                        "benchmark_case_id": benchmark_case.id,
                        "competency_question_id": question.id,
                        "evidence_packet_id": packet["id"],
                        "answer_status": answer["status"],
                    },
                )
            except KdafError as exc:
                result = self.metadata.create_evaluation_result(
                    run.id,
                    benchmark_case.id,
                    "error",
                    {"passed": False},
                    {
                        "benchmark_id": catalog.benchmark_id,
                        "benchmark_case_id": benchmark_case.id,
                    },
                    {"code": exc.code, "message": exc.message},
                )
            results.append(result.to_dict())
        passed = sum(result["status"] == "passed" for result in results)
        return {
            "benchmark": {
                "id": catalog.benchmark_id,
                "name": catalog.name,
                "schema_version": catalog.schema_version,
            },
            "run": run.to_dict(),
            "status": "passed" if passed == len(results) else "failed",
            "summary": {
                "total": len(results),
                "passed": passed,
                "failed": len(results) - passed,
            },
            "results": results,
        }

    def run_public_demo(
        self,
        project_name: str,
        *,
        question_category: str = "budget_vs_actuals",
        dwh_store_path: str | Path | None = None,
        offline_graph: bool = False,
    ) -> dict[str, Any]:
        """Run the adoption-ready project-to-evaluation vertical slice."""

        try:
            catalog_question = next(
                question
                for question in starter_question_catalog().questions
                if question.category == question_category
            )
        except (StopIteration, StarterQuestionCatalogError) as exc:
            raise KdafError(
                f"Starter question category not found: {question_category}", "not_found"
            ) from exc
        project = self.create_project(
            project_name,
            "Generated by the KDAF v0.6 public demo workflow.",
        )
        starter_kit = self.load_starter_kit(
            project["id"],
            dwh_store_path=dwh_store_path,
            include_graph=not offline_graph,
        )
        questions = self.list_competency_questions(project["id"])
        question = next(
            item for item in questions if item["question_text"] == catalog_question.question_text
        )
        run = self.create_run(project["id"], "public_demo")
        carp_context = self.retrieve_carp_context(
            question["id"], offline_graph=offline_graph
        )
        packet = self.build_evidence_packet(
            question["id"],
            run["id"],
            dwh_store_path=dwh_store_path,
            offline_graph=offline_graph,
        )
        answer = self.generate_grounded_answer(packet)
        refusal = self.generate_grounded_answer(
            packet,
            requested_claim="What was the unsupported cash balance?",
        )
        metrics = grade_evaluation_case(packet, answer, refusal)
        evaluation = self.metadata.create_evaluation_result(
            run["id"],
            f"public_demo:{question_category}",
            "passed" if metrics["passed"] else "failed",
            metrics,
            {
                "workflow": "public_demo",
                "competency_question_id": question["id"],
                "evidence_packet_id": packet["id"],
                "answer_status": answer["status"],
                "refusal_status": refusal["status"],
            },
        )
        return {
            "project": project,
            "starter_kit": starter_kit,
            "run": run,
            "question": question,
            "carp_context": carp_context,
            "evidence_packet": packet,
            "answer": answer,
            "unsupported_claim": refusal,
            "evaluation_result": evaluation.to_dict(),
            "architecture": {
                "financial_facts_store": "financial_dwh",
                "metadata_store": "metadata_db",
                "semantic_context_store": "neo4j",
                "graph_stores_financial_facts": False,
            },
        }

    def _default_starter_dwh_path(self) -> Path:
        return self.metadata.store_path.parent / "starter_dwh.sqlite3"

    def _dwh_query_service(
        self, dwh_store_path: str | Path | None
    ) -> ReadOnlyDwhQueryService | PostgresDwhQueryService:
        local_store_path = dwh_store_path or self._configured_dwh_store_path
        if local_store_path is not None:
            return ReadOnlyDwhQueryService(local_store_path)
        config = self.config.dwh_db
        return PostgresDwhQueryService(
            host=config.host,
            port=config.port,
            database=config.database,
            user=config.user,
            password=config.password,
        )

    def starter_graph_schema(self) -> dict[str, str]:
        artifacts = starter_graph_cypher_artifacts()
        return {
            "dialect": "cypher",
            "seed_cypher": artifacts["seed"],
            "sample_queries_cypher": artifacts["sample_queries"],
        }

    def load_starter_graph(self) -> dict[str, Any]:
        repository = StarterGraphRepository(self._neo4j_connection_settings())
        try:
            return repository.load_seed_data().to_dict()
        except StarterGraphError as exc:
            raise KdafError(str(exc), code="starter_graph_error") from exc

    def starter_graph_context(self) -> dict[str, Any]:
        repository = StarterGraphRepository(self._neo4j_connection_settings())
        try:
            return repository.inspect_context()
        except StarterGraphError as exc:
            raise KdafError(str(exc), code="starter_graph_not_loaded") from exc

    def starter_question_catalog(self) -> dict[str, Any]:
        try:
            return starter_question_catalog().to_dict()
        except StarterQuestionCatalogError as exc:
            raise KdafError(str(exc), code="starter_question_catalog_error") from exc

    def load_starter_questions(self, project_id: str) -> dict[str, Any]:
        try:
            return load_starter_question_catalog(self.metadata, project_id=project_id).to_dict()
        except MetadataError as exc:
            raise KdafError(str(exc), code=_metadata_error_code(exc)) from exc
        except StarterQuestionCatalogError as exc:
            raise KdafError(str(exc), code="starter_question_catalog_error") from exc

    def load_starter_kit(
        self,
        project_id: str,
        dwh_store_path: str | Path | None = None,
        include_graph: bool = True,
    ) -> dict[str, Any]:
        service = StarterKitService(
            metadata_repository=self.metadata,
            graph_settings=self._neo4j_connection_settings(),
            default_dwh_store_path=self._default_starter_dwh_path(),
        )
        try:
            return service.load(
                project_id=project_id,
                dwh_store_path=dwh_store_path,
                include_graph=include_graph,
            ).to_dict()
        except MetadataError as exc:
            raise KdafError(str(exc), code=_metadata_error_code(exc)) from exc
        except StarterDwhError as exc:
            raise KdafError(str(exc), code="starter_dwh_error") from exc
        except StarterGraphError as exc:
            raise KdafError(str(exc), code="starter_graph_error") from exc
        except StarterQuestionCatalogError as exc:
            raise KdafError(str(exc), code="starter_question_catalog_error") from exc

    def _neo4j_connection_settings(self) -> Neo4jConnectionSettings:
        return Neo4jConnectionSettings(
            uri=self.config.neo4j.uri,
            user=self.config.neo4j.user,
            password=self.config.neo4j.password,
            database=self.config.neo4j.database,
        )


def _safe_database_summary(database_config: Any) -> dict[str, Any]:
    return {
        "host": database_config.host,
        "port": database_config.port,
        "database": database_config.database,
        "user": database_config.user,
        "role": database_config.role,
    }


def _metadata_error_code(error: MetadataError) -> str:
    return error.code


def _core_metadata_error(error: MetadataError) -> KdafError:
    return KdafError(str(error), code=_metadata_error_code(error))
