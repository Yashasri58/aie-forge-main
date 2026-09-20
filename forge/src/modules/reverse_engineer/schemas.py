"""
Schemas for the Reverse Engineer pipeline.

All Pydantic models used across the 5 pipeline stages and the REST API.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


# ─── Stage enum ──────────────────────────────────────────────────────────────

class REStage(str, Enum):
    UPLOADING   = "uploading"    # File received, not yet parsed
    PARSING     = "parsing"      # Stage 1: deterministic log parser
    EXTRACTING  = "extracting"   # Stage 2: Drain3 template mining
    INFERRING   = "inferring"    # Stage 3: InferenceAgent (Gemini Pro)
    GAP_REVIEW  = "gap_review"   # Stage 4: GapAgent (Gemini Flash)
    WRITING     = "writing"      # Stage 5: SpecWriterAgent (Gemini Flash)
    COMPLETE    = "complete"     # All 11 sections ready
    FAILED      = "failed"       # Unrecoverable error


# ─── Confidence taxonomy (from Reversa / research) ───────────────────────────

class Confidence(str, Enum):
    CONFIRMED = "CONFIRMED"   # Directly observed in log
    INFERRED  = "INFERRED"    # Derived from patterns
    GAP       = "GAP"         # Cannot be determined from available data


# ─── Stage 1 output: ExtractedFacts ─────────────────────────────────────────

@dataclass
class ServiceInfo:
    name: str
    event_count: int
    log_levels: Dict[str, int]       # INFO/WARN/ERROR counts
    endpoints: List[str]             # HTTP endpoints handled
    calls_to: List[str]              # Services this service calls
    called_by: List[str]             # Services that call this service


@dataclass
class EndpointInfo:
    method: str
    path: str
    path_template: str               # Normalized, e.g. /orders/{id}
    caller_services: List[str]
    response_codes: List[int]
    latencies_ms: List[float]
    confidence: Confidence = Confidence.CONFIRMED


@dataclass
class TraceFlow:
    trace_id: str
    service_sequence: List[str]      # Ordered list of services in trace
    scenario_name: str               # Human-readable scenario name
    events: List[Dict[str, Any]]     # Raw parsed events in the trace
    outcome: str                     # success / error / timeout / rejected
    kafka_events: List[str]          # Topics published in this trace


@dataclass
class KafkaTopicInfo:
    topic: str
    producers: List[str]
    consumers: List[str]
    partitions_observed: Optional[int] = None
    lag_observed: Optional[int] = None


@dataclass
class ServiceDataStore:
    service: str
    db_type: str                     # postgres / redis / mongo / etc.
    evidence: str                    # Log line that implies this
    cache_pattern: Optional[str] = None  # cache-aside / write-through / etc.
    cache_ttl_seconds: Optional[int] = None


@dataclass
class ResiliencePattern:
    pattern_name: str                # retry / circuit_breaker / saga / etc.
    service: str
    config: Dict[str, Any]          # attempts, timeout, threshold, etc.
    trigger: str                     # what triggers it
    evidence: str                    # log snippet


@dataclass
class SLOMetric:
    metric_name: str
    service: str
    threshold: Optional[float]
    observed_value: Optional[float]
    unit: str                        # ms / percent / count
    status: str                      # ok / warn / breach / unknown
    evidence: str


@dataclass
class ErrorEvent:
    service: str
    level: str                       # ERROR / WARN
    message: str
    trace_id: Optional[str]
    timestamp: str
    category: str                    # auth / payment / inventory / infra / etc.


@dataclass
class ExtractedFacts:
    """Complete output of Stage 1 (log_parser) + Stage 2 (template_extractor)."""
    session_id: str
    log_file_name: str
    total_log_lines: int
    parsed_at: float

    # Core discoveries
    services: List[ServiceInfo] = field(default_factory=list)
    endpoints: List[EndpointInfo] = field(default_factory=list)
    trace_flows: List[TraceFlow] = field(default_factory=list)
    kafka_topics: List[KafkaTopicInfo] = field(default_factory=list)
    data_stores: List[ServiceDataStore] = field(default_factory=list)
    resilience_patterns: List[ResiliencePattern] = field(default_factory=list)
    slo_metrics: List[SLOMetric] = field(default_factory=list)
    errors: List[ErrorEvent] = field(default_factory=list)

    # Stage 2 addition
    log_templates: List[Dict[str, Any]] = field(default_factory=list)
    # Each entry: { template: str, count: int, parameters: list, services: list }

    # Derived counts
    @property
    def service_count(self) -> int:
        return len(self.services)

    @property
    def endpoint_count(self) -> int:
        return len(self.endpoints)

    @property
    def trace_count(self) -> int:
        return len(self.trace_flows)

    def to_dict(self) -> Dict[str, Any]:
        import dataclasses
        return dataclasses.asdict(self)


# ─── Stage 3 output: Application Specification Graph ────────────────────────

@dataclass
class ASGClaim:
    """A single claim in the Application Specification Graph."""
    claim_id: str
    category: str        # service / endpoint / flow / data / resilience / tech / risk
    subject: str         # what this claim is about
    predicate: str       # what is being claimed
    value: Any           # the claimed value
    confidence: Confidence
    evidence: List[str]  # log lines or facts that support this
    gaps: List[str] = field(default_factory=list)  # what would increase confidence


@dataclass
class ASGServiceNode:
    service_name: str
    responsibility: str
    tech_stack_hints: List[str]
    preconditions: List[str]
    postconditions: List[str]
    invariants: List[str]
    confidence: Confidence
    evidence: List[str]


@dataclass
class ASGDependencyEdge:
    source: str
    target: str
    protocol: str         # HTTP / Kafka / Redis / etc.
    direction: str        # sync / async
    call_frequency: str   # always / conditional / rare
    confidence: Confidence
    evidence: List[str]


@dataclass
class ApplicationSpecGraph:
    """The structured intermediate artifact produced by InferenceAgent."""
    session_id: str
    inferred_at: float
    service_nodes: List[ASGServiceNode] = field(default_factory=list)
    dependency_edges: List[ASGDependencyEdge] = field(default_factory=list)
    all_claims: List[ASGClaim] = field(default_factory=list)

    @property
    def confirmed_count(self) -> int:
        return sum(1 for c in self.all_claims if c.confidence == Confidence.CONFIRMED)

    @property
    def inferred_count(self) -> int:
        return sum(1 for c in self.all_claims if c.confidence == Confidence.INFERRED)

    @property
    def gap_count(self) -> int:
        return sum(1 for c in self.all_claims if c.confidence == Confidence.GAP)

    def to_dict(self) -> Dict[str, Any]:
        import dataclasses
        return dataclasses.asdict(self)


# ─── Stage 5 output: SpecSection ────────────────────────────────────────────

SPEC_SECTIONS = [
    "executive_summary",
    "service_inventory",
    "api_catalog",
    "business_logic",
    "event_topology",
    "data_model",
    "cross_cutting",
    "slos_and_observability",
    "resilience_patterns",
    "tech_stack",
    "risks_and_gaps",
    "confidence_report",
]


@dataclass
class SpecSection:
    section_id: str       # e.g. "service_inventory"
    title: str
    content_md: str       # Full Markdown content
    confidence_score: float  # 0.0 – 1.0, fraction of CONFIRMED claims
    gap_count: int
    generated_at: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "section_id": self.section_id,
            "title": self.title,
            "content_md": self.content_md,
            "confidence_score": self.confidence_score,
            "gap_count": self.gap_count,
            "generated_at": self.generated_at,
        }


# ─── Top-level session state ─────────────────────────────────────────────────

@dataclass
class RESession:
    """
    Full state of one Reverse Engineer pipeline run.
    Stored in SQLite and returned by the REST API.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    stage: REStage = REStage.UPLOADING
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    # Input
    log_file_name: str = ""
    log_file_path: str = ""
    user_comments: Optional[str] = None   # Optional user context

    # Stage outputs (populated progressively)
    extracted_facts: Optional[Dict[str, Any]] = None  # Stage 1+2
    asg: Optional[Dict[str, Any]] = None              # Stage 3
    spec_sections: Dict[str, SpecSection] = field(default_factory=dict)  # Stage 5

    # Progress
    current_stage_detail: str = ""
    activity_log: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None

    # Harness receipts
    tool_receipts: List[Dict[str, Any]] = field(default_factory=list)

    def add_activity(self, message: str, level: str = "info",
                     event_type: Optional[str] = None,
                     metadata: Optional[Dict] = None) -> None:
        self.activity_log.append({
            "time": time.time(),
            "message": message,
            "level": level,
            "event_type": event_type or "info",
            "metadata": metadata or {},
        })
        self.updated_at = time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "stage": self.stage.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "log_file_name": self.log_file_name,
            "user_comments": self.user_comments,
            "extracted_facts": self.extracted_facts,
            "asg": self.asg,
            "spec_sections": {
                k: v.to_dict() for k, v in self.spec_sections.items()
            },
            "current_stage_detail": self.current_stage_detail,
            "activity_log": self.activity_log,
            "error": self.error,
            "tool_receipts": self.tool_receipts,
            # Computed convenience fields for the UI
            "service_count": (
                self.extracted_facts.get("services", [])
                if self.extracted_facts else []
            ).__len__(),
            "spec_section_count": len(self.spec_sections),
            "available_sections": list(self.spec_sections.keys()),
        }
