# Reverse Engineering Pipeline — Requirements Document

**Project:** Forge — GPP Reverse Engineer  
**Status:** Requirements Defined — Pending Implementation  
**Date:** September 2026  
**Author:** AIE Hyderabad  

---

## 1. Background & Problem Statement

### The Business Problem

HSBC and similar enterprises integrate with third-party vendor applications (e.g. GPP —
a payment platform) via microservice-to-microservice HTTP/event communication. These
third-party systems are **black boxes**:

- No source code access
- No API documentation (or outdated)
- No architecture diagrams
- No database schemas
- Tribal knowledge concentrated in a few people

When HSBC needs to:
- Replace the third-party vendor with an in-house system
- Migrate to a newer version
- Audit compliance of the integration
- Onboard new engineers

...they have **no systematic way to understand what the third-party system does.**

### What Exists Today

The only artifacts available are:

| Artifact | What it Contains | Reliability |
|---------|-----------------|-------------|
| Application logs | Structured log lines with timestamps, service tags, trace IDs, error messages | High — machine-generated |
| XLSX/manual analysis | Human-produced analysis of logs (good but manual, incomplete, not reproducible) | Medium — human effort, not automated |
| Jira tickets | Feature requests, bug reports, integration notes | Low — fragmented, informal |
| Confluence pages | Architecture notes, runbooks, meeting notes | Low — often outdated |
| Swagger/OpenAPI snippets | Partial API specs if they exist | Medium — may be incomplete |

### What is Needed

An AI-powered pipeline that **automatically reverse engineers a third-party application**
from available data sources and produces a **complete, structured specification document**
that an engineering team can use to rebuild the application from scratch.

---

## 2. Goal

> Given logs, Jira data, Confluence pages, and any other available artifacts of a
> third-party application, use AI agents to reverse engineer its architecture,
> business logic, APIs, data models, event flows, and resilience patterns — and
> produce a comprehensive, confidence-scored specification document.

The output spec must be detailed enough for a development team to **build the
third-party application end-to-end without any other information.**

---

## 3. Proof of Concept Data

Two files have been provided for POC validation:

### File 1: `combined-microservices.log`
**Format:** Structured log lines  
**Size:** ~50 log lines covering ~49 seconds of activity  
**Content:** 6 traced requests + background jobs + health checks + alerts  

Sample:
```
2026-09-17T08:00:01.142Z INFO  [api-gateway] [traceId=a1b2c3d4-0001] [spanId=gw-1001]
  Incoming request POST /api/v1/orders from 10.24.8.15 user-agent=Mozilla/5.0
```

**What is observable:**
- 7 microservices: api-gateway, auth-service, order-service, inventory-service,
  payment-service, user-service, notification-service
- 4 complete request traces (happy path, OOS, payment failure, cache hit)
- 2 background/scheduled jobs (inventory-sync, token-cleanup)
- Health check snapshots for all services
- Infrastructure alerts (Kafka lag, SLO breach, rate limiting)

### File 2: `microservices-analysis.xlsx`
**Format:** Excel workbook with 11 analysis sheets  
**Content:** Human-produced manual analysis of the log file  
**Purpose:** This is the TARGET OUTPUT FORMAT the AI pipeline must produce automatically.

**11 sheets (= 11 spec sections the pipeline must generate):**

| Sheet | Content |
|-------|---------|
| 1. Service Inventory | 7 services + 9 external dependencies + inferred ports/runtimes |
| 2. API & Requests | 6 external endpoints + 7 internal service-to-service calls |
| 3. Business Logic | 3 complete flow narratives + state machine + business rules per service |
| 4. Event Topology | 3 Kafka topics + producers/consumers + consumer lag data |
| 5. Data Stores | Per-service DB/cache + caching patterns |
| 6. Cross-Cutting | Auth (JWT/JWKS), rate limiting, tracing, circuit breaker, etc. |
| 7. SLOs & Observability | 9 metrics with thresholds, observed values, status |
| 8. Resilience Patterns | 10 patterns: retry, saga, circuit breaker, cache-aside, etc. |
| 9. Risks & Tech Debt | 8 risks with severity + evidence |
| 10. Tech Stack | Language, infra, databases, messaging, auth, monitoring |
| 11. Gaps & Missing | 12 items that cannot be derived + why |

**The xlsx is what a skilled human produced manually in hours. The pipeline produces
it automatically in minutes.**

---

## 4. Scope

### In Scope (POC)

1. **Log file parsing** — structured log ingestion and event extraction
2. **Trace reconstruction** — grouping log events by traceId to rebuild request flows
3. **Service topology inference** — identifying services, their roles, and dependencies
4. **API catalog extraction** — extracting HTTP endpoints, methods, response codes
5. **Business flow reconstruction** — narrative description of each observable scenario
6. **Event topology mapping** — Kafka topics, producers, consumers, schemas (from log evidence)
7. **Data store inference** — which service uses what database/cache and what pattern
8. **Cross-cutting concern detection** — auth patterns, tracing, rate limiting, etc.
9. **Resilience pattern recognition** — retries, circuit breakers, sagas, cache-aside
10. **SLO and observability extraction** — latency thresholds, error rates, alert states
11. **Risk identification** — bugs, breaches, degradations visible in logs
12. **Tech stack inference** — language (Java from NPE), infra (Kubernetes from HPA), etc.
13. **Gap analysis** — what cannot be inferred, what needs investigation
14. **Confidence scoring** — every inference tagged as CONFIRMED/INFERRED/UNKNOWN
15. **Spec document generation** — structured Markdown output mirroring the 11 xlsx sections

### Out of Scope (POC)

- Jira integration (data source not yet available)
- Confluence integration (data source not yet available)
- OpenAPI YAML generation (can be Phase 2)
- Database schema inference beyond entity hints
- UI/frontend behavior (no frontend logs provided)
- Multi-file log ingestion (single file for POC)
- Real-time streaming log analysis
- Connecting to the actual third-party system

### Future Scope (Post-POC)

- Jira ticket ingestion and cross-referencing with log evidence
- Confluence page ingestion for context enrichment
- OpenAPI YAML spec generation from inferred API catalog
- Diagram generation (service topology, sequence diagrams, state machines)
- Multi-log-file ingestion with deduplication
- Incremental analysis (update spec as new logs arrive)
- Feeding the output spec directly into Forge's existing code generation pipeline

---

## 5. Inputs and Data Sources

### Primary Input: Log Files

**Format support (POC):** Single structured log file  
**Expected format:**
```
<timestamp> <LEVEL> [<service-name>] [traceId=<id>] [spanId=<id>] <message>
```

**Minimum log quality requirements for meaningful output:**
- Structured format (not free-text paragraphs)
- Service name in log tag (`[service-name]`)
- Trace/correlation ID present on most lines
- Mix of INFO, WARN, ERROR levels
- At least 3-5 complete request traces visible

**What the pipeline should handle gracefully:**
- Missing trace IDs on some lines (background jobs, health checks)
- Multi-line error stack traces
- Log lines from the same service across multiple instances
- Varying log formats across services (best-effort normalization)

### Secondary Inputs (Future)

| Source | What It Adds | Priority |
|--------|-------------|---------|
| Jira tickets | Feature context, business intent behind APIs | P1 |
| Confluence pages | Architecture decisions, runbooks, data dictionaries | P1 |
| Swagger/OpenAPI files | Exact endpoint signatures, request/response schemas | P2 |
| Existing manual analysis (xlsx) | Validation and gap-filling | P2 |
| Environment configs / docker-compose | Port mappings, service URLs, env vars | P3 |

---

## 6. Output Specification

### 6.1 Output Format

**Primary output:** Set of Markdown files (one per spec section)  
**Secondary output (future):** OpenAPI YAML, Mermaid diagrams

### 6.2 Output File Structure

```
reverse-engineer/output/<session-id>/
  ├── 00_executive_summary.md
  ├── 01_service_inventory.md
  ├── 02_api_catalog.md
  ├── 03_business_logic.md
  ├── 04_event_topology.md
  ├── 05_data_model.md
  ├── 06_cross_cutting.md
  ├── 07_slos_and_observability.md
  ├── 08_resilience_patterns.md
  ├── 09_tech_stack.md
  ├── 10_risks_and_gaps.md
  └── 11_confidence_report.md
```

### 6.3 Section Requirements

#### 00. Executive Summary
- What application was analyzed
- Data sources used
- Number of services discovered
- Number of endpoints discovered
- Key business flows identified
- Overall confidence level
- Top 3 risks
- Top 3 gaps that need investigation

#### 01. Service Inventory
For each discovered service:
- Service name (from log tag)
- Inferred port (if present in logs)
- Inferred runtime / language
- Primary responsibility (1-2 sentence description)
- Dependencies (services it calls)
- Dependents (services that call it)
- Confidence: CONFIRMED / INFERRED

For each external dependency:
- Name and type (database, cache, message broker, external API, etc.)
- Which services use it
- Evidence from logs

#### 02. API Catalog
For each discovered endpoint:
- HTTP method + path
- Who calls it (external client or which internal service)
- Request parameters / body (inferred from log evidence)
- Response codes observed + meaning
- Observed latency (if available)
- Confidence level

For each internal service-to-service call:
- Caller → Callee
- Inferred endpoint path
- Protocol (sync HTTP or async Kafka)
- Direction (request/response or event)
- Evidence (log line reference)

#### 03. Business Logic
For each observed scenario / trace:
- Scenario name (e.g. "Happy Path Order Creation")
- Step-by-step flow with service transitions
- Decision points (e.g. "if stock available, else reject")
- Business rules observed
- Error handling behavior

State machines for any stateful entities:
- States observed
- Transitions observed
- States inferred but not observed (flagged)

Per-service business rules:
- Input validation rules
- Processing rules
- Output/event publication rules

#### 04. Event Topology
For each Kafka topic / async event:
- Topic name
- Producer service
- Consumer service(s)
- Consumer group (if observed)
- Purpose / trigger
- Observed partitions / offsets
- Lag observed (if any)
- Inferred payload structure (from log context)

#### 05. Data Model
For each service:
- Primary data store type (PostgreSQL, MongoDB, etc.)
- Inferred entities / tables (from log field names)
- Cache strategy (type, TTL, key pattern if observed)
- Data ownership principle (database-per-service, shared, etc.)
- Inferred relationships between entities across services

#### 06. Cross-Cutting Concerns
For each concern:
- Authentication mechanism (JWT format, JWKS, RBAC, etc.)
- Authorization model (roles observed, access patterns)
- Rate limiting (rules, thresholds, behavior)
- Distributed tracing (trace ID format, propagation)
- Logging format and conventions
- Secret management
- API versioning strategy
- Health check patterns

#### 07. SLOs & Observability
For each metric/SLO:
- Metric name
- Service that owns it
- Threshold/SLO value
- Observed value in logs
- Status (OK/WARN/BREACH/TRIPPED)
- Alert behavior observed
- Impact of breach

#### 08. Resilience Patterns
For each pattern:
- Pattern name
- Where implemented (which service/transition)
- Configuration observed (attempts, timeouts, thresholds)
- Trigger condition
- Recovery behavior
- Evidence from logs

#### 09. Tech Stack
- Programming language(s) with evidence
- Container orchestration
- Messaging infrastructure
- Databases (type, evidence)
- Caching layer
- Secret management
- Authentication infrastructure
- Observability stack (tracing, metrics, logging)
- External APIs and services
- Cloud provider (if detectable)

#### 10. Risks & Gaps
Risks:
- Description
- Severity (High / Medium / Low / Info)
- Evidence from logs
- Recommended action

Gaps (what cannot be inferred):
- What is missing
- Why it cannot be derived from available data
- What additional data source would fill the gap
- Impact on spec completeness

#### 11. Confidence Report
For every major inference:
- Claim (what was inferred)
- Evidence (log line(s) that support it)
- Confidence: CONFIRMED (directly observed) / INFERRED (derived) / ASSUMED (reasonable guess)
- Gaps (what would increase confidence)

Overall confidence metrics:
- % of services CONFIRMED vs INFERRED
- % of API endpoints CONFIRMED vs INFERRED
- % of business flows CONFIRMED vs INFERRED
- Top 5 highest-confidence inferences
- Top 5 lowest-confidence inferences

---

## 7. Multi-Agent Pipeline Architecture

### 7.1 Pipeline Overview

```
Input Files (log, xlsx, jira, confluence)
          │
          ▼
┌─────────────────────────┐
│  STAGE 1: Ingestion     │  (deterministic)
│  Log Parser             │  Parse → structured events
│  XLSX Reader            │  Read existing analysis
│  Source Normalizer      │  Unify format across sources
└─────────────────────────┘
          │ structured_events[]
          ▼
┌─────────────────────────┐
│  STAGE 2: Extraction    │  (deterministic + LLM assist)
│  Trace Reconstructor    │  Group by traceId → flows
│  Service Detector       │  Identify unique services
│  Endpoint Extractor     │  Find HTTP calls, Kafka events
│  Pattern Detector       │  Retry, saga, circuit breaker
└─────────────────────────┘
          │ extracted_facts[]
          ▼
┌─────────────────────────┐
│  STAGE 3: Inference     │  (LLM — Gemini Pro)
│  InferenceAgent         │  Facts → business logic
│                         │  Infer state machines
│                         │  Infer data models
│                         │  Infer missing endpoints
│                         │  Score confidence
└─────────────────────────┘
          │ inferences[] with confidence
          ▼
┌─────────────────────────┐
│  STAGE 4: Gap Analysis  │  (LLM — Gemini Flash)
│  GapAgent               │  What is unknown
│                         │  What additional data needed
│                         │  Conflicting evidence
│                         │  Ambiguous patterns
└─────────────────────────┘
          │ gaps[] + confidence_scores[]
          ▼
┌─────────────────────────┐
│  STAGE 5: Spec Writer   │  (LLM — Gemini Pro)
│  SpecWriterAgent        │  Combine all → spec docs
│                         │  Generate each section
│                         │  Apply confidence tags
│                         │  Write Markdown output
└─────────────────────────┘
          │
          ▼
     Output: 11 Markdown spec files
```

### 7.2 Agent Descriptions

#### Stage 1: Log Parser (deterministic Python)
- No LLM involved
- Regex-based parsing of log lines
- Extract: timestamp, level, service_tag, trace_id, span_id, message
- Group into: request_traces, background_jobs, health_checks, alerts
- Output: structured JSON with all log events

#### Stage 2: Extraction Agents (deterministic + LLM assist)
- **Trace Reconstructor:** Group all events sharing a traceId into a flow sequence
- **Service Detector:** Extract unique `[service-name]` tags, count events per service
- **Endpoint Extractor:** Regex + LLM to find HTTP paths, methods, status codes
- **Pattern Detector:** Rule-based detection of retry patterns, saga keywords, etc.
- Output: extracted_facts.json

#### Stage 3: InferenceAgent (Gemini 2.5 Pro)
Primary intelligence agent. Takes extracted facts and infers:
- Service responsibilities from its observable behavior
- Business rules from decision points in flows
- State machines from status transitions (PENDING → CONFIRMED → CANCELLED)
- Data model entities from field names in log messages
- Inferred-but-not-observed API endpoints
- Technology stack from evidence (NPE = Java, pod IDs = Kubernetes, etc.)

Every inference is tagged with confidence level and evidence citation.

#### Stage 4: GapAgent (Gemini 2.5 Flash)
Reviews all inferences and identifies:
- What cannot be derived from available data
- Where inferences conflict
- What additional data source would fill each gap
- Ambiguities that need human clarification

#### Stage 5: SpecWriterAgent (Gemini 2.5 Pro)
Takes all inferences + gaps and generates:
- All 11 Markdown spec sections
- Executive summary
- Confidence report
- Formatted, readable, structured documentation

### 7.3 Harness Checks

Per the harness validation strategy:

| Check | Where | What |
|-------|-------|------|
| Input validation | Stage 1 | Log file is readable, has at least 10 lines, has recognizable format |
| Tool receipt logging | Stage 3 | InferenceAgent must cite evidence for every inference |
| Output grounding | Stage 3→4 | Every service name in output must come from log tag, not hallucinated |
| Action boundary | Stage 3 | Agent cannot invent service names not seen in logs |
| Confidence scoring | Stage 4 | Every inference rated CONFIRMED/INFERRED/ASSUMED |
| Gap detection | Stage 4 | All inferences reviewed for missing evidence |

---

## 8. API / UI

### 8.1 New API Endpoints

```
POST /reverse-engineer/start
  Body: { log_file_path: str, additional_sources: [] }
  Returns: { session_id, stage, status }

GET  /reverse-engineer/{session_id}
  Returns: current stage, progress, errors

GET  /reverse-engineer/{session_id}/facts
  Returns: extracted_facts from Stage 2

GET  /reverse-engineer/{session_id}/inferences
  Returns: all inferences with confidence scores

GET  /reverse-engineer/{session_id}/spec/{section}
  Returns: generated Markdown for that section
  section: summary | services | apis | business | events | data |
           crosscutting | slos | resilience | techstack | risks | confidence

GET  /reverse-engineer/{session_id}/spec/download
  Returns: zip of all 11 Markdown files
```

### 8.2 Frontend

New page in Forge UI: `/reverse-engineer`

Sections:
1. **Upload** — drag-drop log file + optional additional sources
2. **Progress** — live pipeline stages with activity log (same pattern as existing pipeline page)
3. **Facts view** — what was extracted (services, endpoints, events)
4. **Spec viewer** — tabbed view of all 11 sections with confidence indicators
5. **Gaps panel** — what is missing, what data would help
6. **Download** — export all spec files as zip

---

## 9. Where This Lives in the Project

### Directory Structure

```
forge/
  src/
    modules/
      reverse_engineer/           ← NEW module
        __init__.py
        log_parser.py             ← Stage 1: deterministic parser
        extractor.py              ← Stage 2: fact extraction
        inference_agent.py        ← Stage 3: LLM inference agent
        gap_agent.py              ← Stage 4: gap analysis agent
        spec_writer_agent.py      ← Stage 5: spec generation agent
        orchestrator.py           ← Pipeline coordinator
        schemas.py                ← Pydantic models
        prompts.py                ← Agent system prompts
    interfaces/
      api/
        routes/
          reverse_engineer.py     ← NEW API routes

  frontend/
    src/
      pages/
        ReverseEngineer.tsx       ← NEW UI page

  reverse-engineer/
    output/                       ← Generated spec files
    sessions/                     ← Session state (for persistence)

  new-requirements/               ← POC input files (already here)
    combined-microservices.log
    microservices-analysis.xlsx
```

### Relationship to Existing Forge

This is a **parallel pipeline** — not replacing or modifying the existing
impact analysis or code generation pipelines.

```
Forge Application
  ├── Pipeline 1: Impact Analysis (existing)
  │   ContextGatherer → ImpactAgent → VerificationAgent → Human Approval
  │
  ├── Pipeline 2: Code Generation (existing)
  │   DesignAgent → CoordinatorAgent → ImplementationAgent(s) → VerifierAgent
  │
  └── Pipeline 3: Reverse Engineer (NEW)
      LogParser → Extractor → InferenceAgent → GapAgent → SpecWriterAgent
```

**Future integration:** The spec output from Pipeline 3 can be fed into Pipeline 1
as the "existing codebase context" when building the reverse-engineered system from scratch.

---

## 10. Success Criteria

### POC Success (using the provided files)

1. **Service discovery:** Pipeline identifies all 7 services from the log file without
   manual guidance

2. **Flow reconstruction:** At least 3 of the 4 traced request scenarios are correctly
   reconstructed end-to-end

3. **Business logic accuracy:** Saga rollback flow (payment failure) correctly described
   including inventory release and order cancellation

4. **Confidence scoring:** CONFIRMED items match only what is directly in the log;
   INFERRED items are clearly flagged as derived

5. **Gap detection:** At least 8 of the 12 gaps identified in the xlsx Sheet 11 are
   independently flagged by the pipeline

6. **Output quality:** The generated Markdown spec is comprehensive enough that a
   developer reading only the output (without the log or xlsx) could design the
   system architecture

### Quality Bar

The output spec should be **equivalent in depth** to what a skilled engineer would
produce manually from the same log data — matching the quality of the provided xlsx
analysis.

---

## 11. Constraints and Non-Goals

### Constraints
- Must run on the existing Forge Python/FastAPI backend
- Must use Google Gemini via ADK (same as other agents)
- No new infrastructure beyond what Forge already has
- POC output must be reproducible (same input → same output structure)
- No sensitive data should be logged (log lines may contain PII like user IDs)

### Non-Goals
- This is **not** a code generation pipeline for building the reverse-engineered system
  (that is the existing Pipeline 2, which can consume this spec later)
- This is **not** a real-time log monitoring system
- This is **not** a log aggregation/search tool
- This does **not** require connectivity to the actual GPP/third-party system

---

## 12. Open Questions

| # | Question | Impact | Owner |
|---|---------|--------|-------|
| 1 | What is the actual format of the real GPP logs? Same structured format or different? | High — parser design depends on this | POC team |
| 2 | Will Jira/Confluence data be available before demo? | Medium — changes pipeline inputs | HSBC liaison |
| 3 | Should output be a single unified document or multiple files? | Low — easily configurable | UX decision |
| 4 | What is the demo timeline? | High — determines depth of POC | Manager |
| 5 | Is the xlsx a one-time human exercise or will the team keep updating it? | Medium — determines whether pipeline replaces or augments human analysis | HSBC team |
| 6 | Are there data privacy concerns with the log files? | High — may need PII masking | Compliance |

---

*Document prepared: September 2026*  
*POC input files: `forge/new-requirements/combined-microservices.log`,*  
*`forge/new-requirements/microservices-analysis.xlsx`*
