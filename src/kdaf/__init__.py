"""KDAF public package surface."""

from kdaf.answers import (
    AnswerError,
    GroundedAnswerService,
    OllamaProvider,
    OpenAICompatibleProvider,
)
from kdaf.config import (
    ConfigError,
    DatabaseConfig,
    KdafConfig,
    Neo4jConfig,
    RuntimeConfig,
    load_config,
)
from kdaf.core import KdafCore, KdafError
from kdaf.extraction import CsvExtractor, ExtractionDwhRepository, ExtractionError
from kdaf.graph import GraphProvenanceRepository
from kdaf.metadata import (
    AuditEvent,
    CompetencyQuestion,
    ExtractionBatch,
    MetadataError,
    MetadataRepository,
    MvgArtifact,
    PackageMetadata,
    Project,
    ProvenanceLink,
    Run,
    Source,
    ValidationItem,
    package_metadata,
)
from kdaf.retrieval import (
    CarpRetrievalService,
    EvidencePacketBuilder,
    Neo4jGraphContextProvider,
    PackagedGraphContextProvider,
    PostgresDwhQueryService,
    ReadOnlyDwhQueryService,
    RetrievalError,
)
from kdaf.starter_dwh import StarterDwhError, StarterDwhRepository, starter_dwh_sql_artifacts
from kdaf.starter_graph import (
    Neo4jConnectionSettings,
    StarterGraphError,
    StarterGraphRepository,
    starter_graph_cypher_artifacts,
)
from kdaf.starter_kit import StarterKitLoadSummary, StarterKitService
from kdaf.starter_kit_demo import run_starter_kit_demo
from kdaf.starter_questions import (
    StarterQuestion,
    StarterQuestionCatalog,
    StarterQuestionCatalogError,
    StarterQuestionLoadSummary,
    starter_question_catalog,
)

__version__ = "0.6.0"
__all__ = [
    "AnswerError",
    "AuditEvent",
    "CarpRetrievalService",
    "ConfigError",
    "CompetencyQuestion",
    "CsvExtractor",
    "DatabaseConfig",
    "ExtractionBatch",
    "ExtractionDwhRepository",
    "ExtractionError",
    "EvidencePacketBuilder",
    "GraphProvenanceRepository",
    "KdafCore",
    "KdafConfig",
    "KdafError",
    "MetadataError",
    "MetadataRepository",
    "MvgArtifact",
    "Neo4jConfig",
    "Neo4jConnectionSettings",
    "Neo4jGraphContextProvider",
    "GroundedAnswerService",
    "OllamaProvider",
    "OpenAICompatibleProvider",
    "PackageMetadata",
    "Project",
    "ProvenanceLink",
    "PackagedGraphContextProvider",
    "PostgresDwhQueryService",
    "ReadOnlyDwhQueryService",
    "RetrievalError",
    "RuntimeConfig",
    "Run",
    "Source",
    "StarterDwhError",
    "StarterDwhRepository",
    "StarterGraphError",
    "StarterGraphRepository",
    "StarterKitLoadSummary",
    "StarterKitService",
    "StarterQuestion",
    "StarterQuestionCatalog",
    "StarterQuestionCatalogError",
    "StarterQuestionLoadSummary",
    "ValidationItem",
    "__version__",
    "load_config",
    "package_metadata",
    "run_starter_kit_demo",
    "starter_question_catalog",
    "starter_graph_cypher_artifacts",
    "starter_dwh_sql_artifacts",
]
