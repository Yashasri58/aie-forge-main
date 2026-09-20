"""
Stage 1 — Log Parser (Deterministic, zero LLM, zero new dependencies).

Parses structured log files of the form:
    <ISO-timestamp> <LEVEL> [<service>] [traceId=<id>] [spanId=<id>] <message>

Outputs an ExtractedFacts object containing:
- service_inventory     (7+ services with event counts, dependencies)
- dependency_graph      (service→service call frequencies)
- endpoint_catalog      (normalized HTTP endpoints)
- kafka_topology        (topics, producers, consumers)
- error_catalog         (ERROR/WARN events with context)
- resilience_patterns   (retry sequences, saga keywords, circuit breakers)
- trace_flows           (grouped by traceId)
- slo_metrics           (latency thresholds, alert states)
- health_checks         (health check snapshots)

All regex-based — no LLM calls, no third-party libraries.
"""

import re
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from .logging_config import parser_logger, log_stage_start, log_stage_complete, log_extract
from .schemas import (
    Confidence,
    EndpointInfo,
    ErrorEvent,
    ExtractedFacts,
    KafkaTopicInfo,
    ResiliencePattern,
    ServiceDataStore,
    ServiceInfo,
    SLOMetric,
    TraceFlow,
)


# ─── Regex patterns ───────────────────────────────────────────────────────────

# Main log line pattern
_LOG_LINE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z)"
    r"\s+(?P<level>INFO|WARN|WARNING|ERROR|DEBUG|TRACE|CRITICAL)"
    r"\s+\[(?P<service>[^\]]+)\]"
    r"(?:\s+\[traceId=(?P<trace_id>[^\]]+)\])?"
    r"(?:\s+\[spanId=(?P<span_id>[^\]]+)\])?"
    r"\s+(?P<message>.+)$"
)

# HTTP endpoint patterns
_HTTP_ENDPOINT = re.compile(
    r"\b(GET|POST|PUT|PATCH|DELETE|OPTIONS|HEAD)\s+(\/[^\s?#]*)",
    re.IGNORECASE,
)
_RESPONSE_SENT = re.compile(
    r"[Rr]esponse\s+(\d{3})\s+\w+\s+sent\s+in\s+([\d.]+)ms",
)
_INCOMING_REQUEST = re.compile(
    r"(?:Incoming request|Request received)\s+(GET|POST|PUT|PATCH|DELETE)\s+(\/[^\s?#]*)",
    re.IGNORECASE,
)

# Path normalization — replace common ID patterns
_PATH_NORMALIZERS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I), "/{uuid}"),
    (re.compile(r"/\d{4}-\d{2}-\d{2}"), "/{date}"),
    (re.compile(r"/[A-Z]{2,6}-\d{4,}-[A-Z0-9-]+"), "/{id}"),  # ORD-20260917-5541
    (re.compile(r"/[A-Z]{2,6}-[0-9A-Z-]+"), "/{id}"),          # TXN-9f3e7a21
    (re.compile(r"/\d{3,}"), "/{id}"),                          # numeric IDs
]

# Kafka patterns
_KAFKA_PUBLISH = re.compile(
    r"[Pp]ublish(?:ing|ed).*?(?:kafka\s+)?topic[=\s]+([^\s,]+)",
)
_KAFKA_CONSUME = re.compile(
    r"[Cc]onsume[d]?\s+.*?(?:from\s+)?(?:kafka\s+)?topic[=\s:]+([^\s,]+)",
)

# Resilience patterns
_RETRY_PATTERN = re.compile(r"attempt\s+(\d+)/(\d+)", re.IGNORECASE)
_SAGA_KEYWORDS = re.compile(
    r"\b(compensat|saga|rollback|compensating transaction)\b", re.IGNORECASE
)
_CIRCUIT_BREAKER = re.compile(
    r"\bcircuit\s*breaker\b.*?\b(OPEN|CLOSED|HALF.OPEN)\b", re.IGNORECASE
)
_TIMEOUT_PATTERN = re.compile(
    r"timeout\s+after\s+([\d]+)ms", re.IGNORECASE
)

# SLO / metric patterns
_SLO_LATENCY = re.compile(r"p99=([\d.]+)ms.*?SLO=([\d.]+)ms", re.IGNORECASE)
_HEALTH_CHECK = re.compile(r"[Hh]ealth check\s+(OK|DEGRADED|FAIL)")
_HPA_SCALING = re.compile(
    r"HPA scaling\s+(\S+)\s+replicas\s+(\d+)\s*->\s*(\d+)\s*\(cpu=(\d+)%\)"
)
_KAFKA_LAG = re.compile(
    r"[Kk]afka consumer lag alert.*lag=(\d+)\s+messages.*threshold=(\d+)"
)

# Data store patterns
_DB_PATTERNS = [
    (re.compile(r"(?:querying|connected to|SELECT|INSERT|UPDATE|DELETE).*?(postgres|postgresql|mysql|mongodb|cassandra)", re.I), "postgres"),
    (re.compile(r"(redis|cache)\s*(HIT|MISS|CONNECT)", re.I), "redis"),
    (re.compile(r"(sqlite|sqlite3)", re.I), "sqlite"),
    (re.compile(r"\b(users-db|order-db|payment-db|inventory-db|auth-db)\b", re.I), "postgres"),
]
_CACHE_PATTERN = re.compile(r"cache\s+(HIT|MISS)", re.IGNORECASE)
_CACHE_TTL = re.compile(r"ttl=(\d+)s", re.IGNORECASE)
_CACHE_KEY = re.compile(r"(?:Cached|key=|cache key)[\s:]+([^\s,]+)", re.IGNORECASE)

# Error categories
_ERROR_CATEGORIES = {
    "auth": re.compile(r"\b(token|jwt|auth|jwks|unauthorized|401|403)\b", re.I),
    "payment": re.compile(r"\b(payment|transaction|charge|gateway|declined|502)\b", re.I),
    "inventory": re.compile(r"\b(stock|inventory|sku|out.of.stock|409)\b", re.I),
    "infra": re.compile(r"\b(kafka lag|hpa|cpu|scale|replica|crash|restart)\b", re.I),
    "network": re.compile(r"\b(timeout|connect|502|503|gateway)\b", re.I),
    "database": re.compile(r"\b(sql|postgres|db|database|query|null\s*pointer)\b", re.I),
    "notification": re.compile(r"\b(ses|fcm|email|push|bounce)\b", re.I),
}


# ─── Helper: path normalization ───────────────────────────────────────────────

def _normalize_path(path: str) -> str:
    for pattern, replacement in _PATH_NORMALIZERS:
        path = pattern.sub(replacement, path)
    return path


def _endpoint_key(method: str, path: str) -> str:
    return f"{method.upper()} {_normalize_path(path)}"


# ─── Helper: scenario naming ─────────────────────────────────────────────────

def _name_scenario(events: List[Dict[str, Any]]) -> str:
    """Infer a human-readable scenario name from trace events."""
    messages = " ".join(e.get("message", "") for e in events)
    levels = {e.get("level", "") for e in events}

    if re.search(r"saga rollback|compensat", messages, re.I):
        return "Payment Failure with Saga Rollback"
    if re.search(r"out.of.stock|OUT OF STOCK|insufficient inventory", messages, re.I):
        return "Out-of-Stock Order Rejection"
    if re.search(r"cache HIT", messages, re.I):
        return "Cache Hit Serve (No DB Query)"
    if re.search(r"DECLINED|declined", messages, re.I):
        return "Payment Declined"
    if re.search(r"[Cc]reate[Oo]rder|CreateOrder", messages):
        if "ERROR" not in levels:
            return "Happy Path Order Creation"
        return "Order Creation with Errors"
    if re.search(r"profile|GET /users", messages, re.I):
        return "User Profile Fetch"
    if re.search(r"(409|Conflict|INSUFFICIENT)", messages, re.I):
        return "Conflict / Constraint Violation"
    if re.search(r"(401|403|unauthorized|token)", messages, re.I):
        return "Authentication / Authorization Flow"
    return "Unclassified Request Flow"


def _outcome_from_events(events: List[Dict[str, Any]]) -> str:
    """Determine the outcome of a trace."""
    messages = " ".join(e.get("message", "") for e in events)
    levels = [e.get("level", "") for e in events]

    if re.search(r"saga rollback|rollback complete", messages, re.I):
        return "saga_rollback"
    if re.search(r"Response 20[01] ", messages):
        return "success"
    if re.search(r"Response 409|Conflict|OUT OF STOCK|insufficient", messages, re.I):
        return "rejected"
    if re.search(r"Response 402|DECLINED|INSUFFICIENT_FUNDS", messages, re.I):
        return "payment_declined"
    if re.search(r"Response 429|Too Many Requests", messages, re.I):
        return "rate_limited"
    if "ERROR" in levels:
        return "error"
    return "unknown"


# ─── Main parser ─────────────────────────────────────────────────────────────

class LogParser:
    """
    Pure Python deterministic log parser.
    No LLM. No third-party dependencies beyond stdlib.
    """

    def __init__(self) -> None:
        self._events: List[Dict[str, Any]] = []
        self._traces: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self._services: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
            "event_count": 0,
            "level_counts": defaultdict(int),
            "endpoints_handled": set(),
            "outgoing_calls": set(),
        })
        self._endpoints: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
            "callers": set(),
            "response_codes": [],
            "latencies": [],
        })
        self._kafka: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
            "producers": set(),
            "consumers": set(),
            "lags": [],
        })
        self._data_stores: Dict[str, Dict[str, Any]] = {}
        self._resilience: List[ResiliencePattern] = []
        self._slo_metrics: List[SLOMetric] = []
        self._errors: List[ErrorEvent] = []
        self._retry_tracking: Dict[str, Dict] = {}   # trace_id -> retry state

    # ─── Parse a single line ─────────────────────────────────────────────────

    def _parse_line(self, line: str) -> Optional[Dict[str, Any]]:
        """Parse one log line. Returns None if not parseable."""
        line = line.strip()
        if not line:
            return None

        m = _LOG_LINE.match(line)
        if not m:
            return None

        return {
            "ts": m.group("ts"),
            "level": m.group("level").upper(),
            "service": m.group("service").strip(),
            "trace_id": m.group("trace_id"),
            "span_id": m.group("span_id"),
            "message": m.group("message").strip(),
            "raw": line,
        }

    # ─── Process a parsed event ───────────────────────────────────────────────

    def _process_event(self, event: Dict[str, Any]) -> None:
        svc = event["service"]
        svc_data = self._services[svc]
        svc_data["event_count"] += 1
        svc_data["level_counts"][event["level"]] += 1

        msg = event["message"]
        tid = event.get("trace_id")

        # Group by trace
        if tid:
            self._traces[tid].append(event)

        # HTTP endpoint detection
        self._extract_endpoint(event, svc)

        # Kafka detection
        self._extract_kafka(event, svc)

        # Data store detection
        self._extract_data_store(event, svc)

        # Resilience patterns
        self._extract_resilience(event, svc)

        # SLO / infra metrics
        self._extract_slo(event, svc)

        # Error logging
        if event["level"] in ("ERROR", "WARN", "WARNING"):
            self._errors.append(ErrorEvent(
                service=svc,
                level=event["level"],
                message=msg[:300],
                trace_id=tid,
                timestamp=event["ts"],
                category=self._categorize_error(msg),
            ))

    def _extract_endpoint(self, event: Dict[str, Any], svc: str) -> None:
        msg = event["message"]
        tid = event.get("trace_id")

        # Incoming request
        m = _INCOMING_REQUEST.search(msg)
        if m:
            method, path = m.group(1).upper(), m.group(2)
            key = _endpoint_key(method, path)
            ep = self._endpoints[key]
            ep["callers"].add(svc)
            self._services[svc]["endpoints_handled"].add(key)

        # Response sent line → extract status + latency
        m2 = _RESPONSE_SENT.search(msg)
        if m2 and tid:
            code = int(m2.group(1))
            latency = float(m2.group(2))
            # Try to associate with an endpoint from the same trace
            for key, ep in self._endpoints.items():
                if svc in ep["callers"]:
                    ep["response_codes"].append(code)
                    ep["latencies"].append(latency)

        # Any GET/POST/PUT/DELETE in any message → routing hints
        for m3 in _HTTP_ENDPOINT.finditer(msg):
            method, path = m3.group(1).upper(), m3.group(2)
            key = _endpoint_key(method, path)
            self._endpoints[key]["callers"].add(svc)

    def _extract_kafka(self, event: Dict[str, Any], svc: str) -> None:
        msg = event["message"]

        m = _KAFKA_PUBLISH.search(msg)
        if m:
            topic = m.group(1).strip(".,\"'")
            self._kafka[topic]["producers"].add(svc)

        m2 = _KAFKA_CONSUME.search(msg)
        if m2:
            topic = m2.group(1).strip(".,\"'")
            self._kafka[topic]["consumers"].add(svc)

        # Consumer lag alert
        m3 = _KAFKA_LAG.search(msg)
        if m3:
            lag = int(m3.group(1))
            threshold = int(m3.group(2))
            self._kafka.get(svc, {})
            self._slo_metrics.append(SLOMetric(
                metric_name="kafka_consumer_lag",
                service=svc,
                threshold=float(threshold),
                observed_value=float(lag),
                unit="messages",
                status="breach" if lag > threshold else "ok",
                evidence=msg[:200],
            ))

    def _extract_data_store(self, event: Dict[str, Any], svc: str) -> None:
        msg = event["message"]

        for pattern, db_type in _DB_PATTERNS:
            if pattern.search(msg):
                store_key = f"{svc}:{db_type}"
                if store_key not in self._data_stores:
                    self._data_stores[store_key] = {
                        "service": svc,
                        "db_type": db_type,
                        "evidence": msg[:200],
                        "cache_pattern": None,
                        "cache_ttl": None,
                    }
                # Cache-specific enrichment
                cm = _CACHE_PATTERN.search(msg)
                if cm:
                    self._data_stores[store_key]["cache_pattern"] = "cache-aside"
                ttl_m = _CACHE_TTL.search(msg)
                if ttl_m:
                    self._data_stores[store_key]["cache_ttl"] = int(ttl_m.group(1))
                break

    def _extract_resilience(self, event: Dict[str, Any], svc: str) -> None:
        msg = event["message"]
        tid = event.get("trace_id", "no-trace")

        # Retry pattern
        m = _RETRY_PATTERN.search(msg)
        if m:
            attempt, max_attempts = int(m.group(1)), int(m.group(2))
            key = f"{tid}:{svc}:retry"
            if key not in self._retry_tracking:
                self._retry_tracking[key] = {
                    "service": svc,
                    "max_attempts": max_attempts,
                    "first_evidence": msg[:200],
                }
            if attempt == max_attempts:
                rp = self._retry_tracking.pop(key)
                self._resilience.append(ResiliencePattern(
                    pattern_name="retry",
                    service=svc,
                    config={"max_attempts": rp["max_attempts"]},
                    trigger="transient failure",
                    evidence=rp["first_evidence"],
                ))

        # Saga / compensating transaction
        if _SAGA_KEYWORDS.search(msg):
            self._resilience.append(ResiliencePattern(
                pattern_name="saga_rollback",
                service=svc,
                config={},
                trigger="downstream failure",
                evidence=msg[:200],
            ))

        # Circuit breaker state
        m2 = _CIRCUIT_BREAKER.search(msg)
        if m2:
            state = m2.group(1).upper()
            self._resilience.append(ResiliencePattern(
                pattern_name="circuit_breaker",
                service=svc,
                config={"state": state},
                trigger="error threshold",
                evidence=msg[:200],
            ))

        # Timeout
        m3 = _TIMEOUT_PATTERN.search(msg)
        if m3:
            timeout_ms = int(m3.group(1))
            self._resilience.append(ResiliencePattern(
                pattern_name="timeout",
                service=svc,
                config={"timeout_ms": timeout_ms},
                trigger="downstream slow",
                evidence=msg[:200],
            ))

    def _extract_slo(self, event: Dict[str, Any], svc: str) -> None:
        msg = event["message"]

        # p99 / SLO latency
        m = _SLO_LATENCY.search(msg)
        if m:
            observed = float(m.group(1))
            threshold = float(m.group(2))
            self._slo_metrics.append(SLOMetric(
                metric_name="latency_p99",
                service=svc,
                threshold=threshold,
                observed_value=observed,
                unit="ms",
                status="breach" if observed > threshold else "ok",
                evidence=msg[:200],
            ))

        # Health check
        m2 = _HEALTH_CHECK.search(msg)
        if m2:
            status = m2.group(1).lower()
            self._slo_metrics.append(SLOMetric(
                metric_name="health_check",
                service=svc,
                threshold=None,
                observed_value=None,
                unit="status",
                status=status,
                evidence=msg[:200],
            ))

        # HPA scaling
        m3 = _HPA_SCALING.search(msg)
        if m3:
            cpu = int(m3.group(4))
            self._slo_metrics.append(SLOMetric(
                metric_name="cpu_utilization",
                service=m3.group(1),
                threshold=80.0,
                observed_value=float(cpu),
                unit="percent",
                status="breach" if cpu > 80 else "ok",
                evidence=msg[:200],
            ))

    @staticmethod
    def _categorize_error(message: str) -> str:
        for category, pattern in _ERROR_CATEGORIES.items():
            if pattern.search(message):
                return category
        return "general"

    # ─── Build service dependency graph ──────────────────────────────────────

    def _build_dependency_graph(self) -> None:
        """
        Infer service-to-service calls from trace ordering.
        Within each trace, consecutive distinct services imply a call.
        """
        for trace_id, events in self._traces.items():
            sorted_events = sorted(events, key=lambda e: e["ts"])
            prev_svc: Optional[str] = None
            for event in sorted_events:
                cur_svc = event["service"]
                if prev_svc and prev_svc != cur_svc:
                    self._services[prev_svc]["outgoing_calls"].add(cur_svc)
                prev_svc = cur_svc

    # ─── Public API ──────────────────────────────────────────────────────────

    def parse_file(self, file_path: str, session_id: str) -> ExtractedFacts:
        """
        Parse a log file and return ExtractedFacts.

        Args:
            file_path: Path to the log file
            session_id: Session ID for linking outputs

        Returns:
            ExtractedFacts with all discoveries
        """
        start = time.time()
        path = Path(file_path)
        log_stage_start(parser_logger, "LOG_PARSER", str(path.name))

        raw_lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        parser_logger.info(f"   Read {len(raw_lines)} lines from {path.name}")

        # Parse every line
        for line in raw_lines:
            event = self._parse_line(line)
            if event:
                self._events.append(event)
                self._process_event(event)

        # Build dependency graph from trace ordering
        self._build_dependency_graph()

        parsed_events = len(self._events)
        parser_logger.info(f"   Parsed {parsed_events}/{len(raw_lines)} lines successfully")

        # ─── Build ServiceInfo list ───────────────────────────────────────────
        all_services: List[ServiceInfo] = []
        for svc_name, svc_data in self._services.items():
            calls_to = list(svc_data["outgoing_calls"])
            called_by = [
                s for s, d in self._services.items()
                if svc_name in d["outgoing_calls"]
            ]
            all_services.append(ServiceInfo(
                name=svc_name,
                event_count=svc_data["event_count"],
                log_levels=dict(svc_data["level_counts"]),
                endpoints=list(svc_data["endpoints_handled"]),
                calls_to=calls_to,
                called_by=called_by,
            ))

        log_extract(parser_logger, "services", len(all_services))

        # ─── Build EndpointInfo list ──────────────────────────────────────────
        all_endpoints: List[EndpointInfo] = []
        for key, ep_data in self._endpoints.items():
            parts = key.split(" ", 1)
            if len(parts) != 2:
                continue
            method, path_tmpl = parts
            all_endpoints.append(EndpointInfo(
                method=method,
                path=path_tmpl,
                path_template=path_tmpl,
                caller_services=list(ep_data["callers"]),
                response_codes=ep_data["response_codes"],
                latencies_ms=ep_data["latencies"],
                confidence=Confidence.CONFIRMED,
            ))

        log_extract(parser_logger, "endpoints", len(all_endpoints))

        # ─── Build TraceFlow list ─────────────────────────────────────────────
        all_flows: List[TraceFlow] = []
        for trace_id, events in self._traces.items():
            sorted_events = sorted(events, key=lambda e: e["ts"])
            service_seq = []
            seen: Set[str] = set()
            for e in sorted_events:
                svc = e["service"]
                if not service_seq or service_seq[-1] != svc:
                    service_seq.append(svc)

            kafka_evts = [
                m.group(1)
                for e in sorted_events
                for m in [_KAFKA_PUBLISH.search(e["message"])]
                if m
            ]

            all_flows.append(TraceFlow(
                trace_id=trace_id,
                service_sequence=service_seq,
                scenario_name=_name_scenario(sorted_events),
                events=sorted_events,
                outcome=_outcome_from_events(sorted_events),
                kafka_events=kafka_evts,
            ))

        log_extract(parser_logger, "trace flows", len(all_flows))

        # ─── Build KafkaTopicInfo list ────────────────────────────────────────
        all_kafka: List[KafkaTopicInfo] = []
        for topic, kdata in self._kafka.items():
            lags = kdata.get("lags", [])
            all_kafka.append(KafkaTopicInfo(
                topic=topic,
                producers=list(kdata["producers"]),
                consumers=list(kdata["consumers"]),
                lag_observed=max(lags) if lags else None,
            ))

        log_extract(parser_logger, "Kafka topics", len(all_kafka))

        # ─── Data stores ──────────────────────────────────────────────────────
        all_stores: List[ServiceDataStore] = []
        for store_key, sdata in self._data_stores.items():
            all_stores.append(ServiceDataStore(
                service=sdata["service"],
                db_type=sdata["db_type"],
                evidence=sdata["evidence"],
                cache_pattern=sdata.get("cache_pattern"),
                cache_ttl_seconds=sdata.get("cache_ttl"),
            ))

        log_extract(parser_logger, "data stores", len(all_stores))

        # ─── Deduplicate resilience patterns ─────────────────────────────────
        seen_patterns: Set[str] = set()
        unique_resilience: List[ResiliencePattern] = []
        for rp in self._resilience:
            key = f"{rp.pattern_name}:{rp.service}"
            if key not in seen_patterns:
                seen_patterns.add(key)
                unique_resilience.append(rp)

        log_extract(parser_logger, "resilience patterns", len(unique_resilience))
        log_extract(parser_logger, "SLO metrics", len(self._slo_metrics))
        log_extract(parser_logger, "error events", len(self._errors))

        duration_ms = (time.time() - start) * 1000
        log_stage_complete(
            parser_logger, "LOG_PARSER", duration_ms,
            f"{parsed_events} events, {len(all_services)} services"
        )

        return ExtractedFacts(
            session_id=session_id,
            log_file_name=path.name,
            total_log_lines=len(raw_lines),
            parsed_at=time.time(),
            services=all_services,
            endpoints=all_endpoints,
            trace_flows=all_flows,
            kafka_topics=all_kafka,
            data_stores=all_stores,
            resilience_patterns=unique_resilience,
            slo_metrics=self._slo_metrics,
            errors=self._errors,
        )

    def parse_text(self, log_text: str, session_id: str, file_name: str = "log.txt") -> ExtractedFacts:
        """
        Parse log content from a string (used when file is uploaded as bytes).

        Args:
            log_text:   Raw log content
            session_id: Session ID
            file_name:  Original filename for display
        """
        import tempfile, os
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".log", delete=False, encoding="utf-8"
        ) as f:
            f.write(log_text)
            tmp_path = f.name
        try:
            facts = self.parse_file(tmp_path, session_id)
            facts.log_file_name = file_name
            return facts
        finally:
            os.unlink(tmp_path)
