# Forge Architecture

*Updated: September 2026*

---

## Overview

Forge is a three-pipeline AI developer platform built on a graph-indexed codebase. All pipelines share the same KuzuDB code graph and FastAPI backend.

```
┌─────────────────────────────────────────────────────────┐
│                      Browser (React SPA)                │
└──────────────┬───────────────────┬──────────────────────┘
               │ Pipeline 1        │ Pipeline 2           │ Pipeline 3
               ▼                   ▼                      ▼
┌──────────────────────────────────────────────────────────────────────┐
│                     FastAPI  (main.py, port 8000)                    │
│                                                                      │
│  /pipeline/*   /codegen/*   /reverse-engineer/*   /cache/*          │
└──────┬────────────────┬────────────────────┬─────────────────────────┘
       │                │                    │
       ▼                ▼                    ▼
┌────────────┐  ┌───────────────┐  ┌───────────────────┐
│  Pipeline  │  │  CodeGen      │  │  RE Orchestrator  │
│  Orchestra-│  │  Orchestrator │  │  (5 stages)       │
│  tor       │  │  (6 stages)   │  └──────────┬────────┘
│  (3 agents)│  └───────┬───────┘             │
└─────┬──────┘          │                     │
      │                 ▼                     ▼
      │         ┌───────────────┐    ┌─────────────────┐
      │         │ Deterministic │    │ Gemini 2.5 Pro  │
      │         │ Gate (8 checks│    │ Gemini 2.5 Flash│
      │         └───────────────┘    └─────────────────┘
      │
      ▼
┌──────────────────────────────┐
│  KuzuDB  (code_graph.kuzu)   │
│  295 symbols, 8 services     │
│  Kuzu Cypher queries         │
└──────────────────────────────┘
```

---

## Pipeline 1 — Impact Analysis

**Entry:** `POST /pipeline/start` with a natural-language requirement  
**Exit:** Layered impact report at `/results/{id}`, approved by human

```
User message
    │
    ▼
ContextGathererAgent  (ADK, Gemini 2.5 Flash)
    │  Clarifies vague requirements through conversation
    │  Queries graph to warn about scope
    │  Returns: RequirementsOutput {services, functions, change_type, ...}
    ▼
[User confirms requirements]
    │
    ▼
ImpactAgent  (ADK, Gemini 2.5 Pro)            ◄──────────────┐
    │  Tools: search_symbols, analyze_impact,                │
    │         trace_call_path, get_service_topology,         │
    │         query_cypher                                   │
    │  Output: LAYERED IMPACT REPORT (text)                  │
    ▼                                                        │
VerificationAgent  (ADK, Gemini 2.5 Flash)                   │
    │  Extracts symbols from report                          │
    │  Calls trace_callers() on each symbol                  │
    │  Returns: {complete, confidence, gaps[]}               │
    │                                                        │
    ├─ complete=True ──────────────────► AWAITING_APPROVAL   │
    ├─ all gaps unresolvable ──────────► AWAITING_APPROVAL   │
    └─ resolvable gaps, iteration < 3 ─────────────────────►┘
                                         (re-run with gaps)
```

**Harness components:** 10 (see `docs/HARNESS_IMPLEMENTATION_REFERENCE.md` Part 1)

---

## Pipeline 2 — Code Generation

**Entry:** `POST /codegen/start` with approved pipeline ID  
**Exit:** Reviewed diffs at `/gen/{id}/approve`, approved by human

```
Impact Report (approved)
    │
    ▼
DesignAgent  (ADK, Gemini 2.5 Pro)
    │  Tools: list_services, list_directory, read_file, grep,
    │         query_code_graph, find_tests, get_similar_patterns
    │  Output: plan.json {tasks[], contracts{}, execution[]}
    ▼
CoordinatorAgent  (ADK, Gemini 2.5 Flash)
    │  Validates plan (file existence, circular deps, contract syntax)
    │  Falls back to deterministic validation if LLM fails
    │  Output: task files per agent
    ▼
ImplementationAgents  (Gemini 2.5 Flash / Flash-Lite, based on complexity)
    │  One agent per task, parallel within phases
    │  Output: unified diffs
    ▼
DeterministicGate  ◄─────────────────────────────────────────┐
    │                                                         │
    │  T1 (fail-fast): syntax:vallm, import resolution       │
    │  T2: security (vallm+native), complexity, contracts    │
    │  T3: hallucination, negative constraints (7 rules)     │
    │                                                         │
    ├─ PASS ────────────────────────────► AWAITING_APPROVAL  │
    ├─ FAIL, same errors as last time ──► AWAITING_APPROVAL  │
    └─ FAIL, new errors, iteration < 3 ─────────────────────┘
                                          (fix_diff with feedback)
```

**Harness components:** 16 (see `docs/HARNESS_IMPLEMENTATION_REFERENCE.md` Part 2)

---

## Pipeline 3 — Reverse Engineer

**Entry:** `POST /reverse-engineer/start` with a log file  
**Exit:** 12-section spec at `/reverse-engineer/{id}/spec`, ZIP download

```
Log file (.log / .txt / .jsonl / .json / .csv / .tsv)
    │
    ▼  [Policy Gate: file extension + path traversal check]
    │
    ▼
Stage 1: LogParser  (deterministic, 0 LLM calls, ~10ms)
    │  Regex extraction: services, endpoints, trace flows,
    │  Kafka topics, SLO metrics, error events
    │  Output: ExtractedFacts
    ▼
Stage 2: TemplateExtractor  (drain3, 0 LLM calls, ~5ms)
    │  Groups similar log lines into N unique templates
    │  Masks: IPs, UUIDs, order IDs, metrics
    │  Output: List[LogTemplate]
    ▼
Stage 3: InferenceAgent  (Gemini 2.5 Pro, 1 LLM call, ~60s)
    │  Builds ApplicationSpecGraph (ASG):
    │    service_nodes[], dependency_edges[], all_claims[]
    │  Each claim tagged: CONFIRMED / INFERRED / GAP
    │  Harness: budget enforcer, loop detector, input sanitizer,
    │           hallucination grounder, JSON parse retry
    │  Output: ApplicationSpecGraph
    ▼
Stage 4: GapAgent  (Gemini 2.5 Flash, 1 LLM call, ~70s)
    │  Downgrades over-confident CONFIRMED → INFERRED
    │  Identifies true GAPs not observable from logs
    │  Logs every reclassification with evidence + reason
    │  Harness: budget enforcer, loop detector
    │  Output: {reclassifications[], gaps[], confidence_summary}
    ▼
Stage 5: SpecWriterAgent  (Gemini 2.5 Flash, 12 LLM calls, ~4min)
    │  Generates 12 Markdown sections:
    │  Executive Summary, Service Inventory, API Catalog,
    │  Business Logic, Event Topology, Data Model,
    │  Cross-Cutting, SLOs & Observability, Resilience,
    │  Tech Stack, Risks & Gaps, Confidence Report
    │  1 retry per section on failure (budget: 15 calls)
    │  Output: Dict[section_id → SpecSection]
    ▼
Spec files written to reverse-engineer/output/{session_id}/
Auto-saved to DemoCache
```

**Harness components:** 10 (see `docs/RE_HARNESS_IMPLEMENTATION_REFERENCE.md`)

---

## Demo Cache

All completed pipeline runs are automatically saved to `forge_demo_cache.db`:

```
┌──────────────────────────────────────────────────────────┐
│  Pipeline completes / human approves                     │
│           │                                              │
│           ▼                                              │
│  DemoCache.save(id, type, label, input, output)         │
│           │                                              │
│           ▼                                              │
│  Dashboard "Past Requests & Results" panel               │
│  → Click entry → /history/{id}                           │
│  → Request tab: input details                            │
│  → Result tab:  impact report / diffs / spec sections    │
└──────────────────────────────────────────────────────────┘
```

---

## Code Graph

The code graph is pre-built from the `services/` directory using `codegraph-tools` and stored in KuzuDB:

```
services/codegraph-out/
├── combined_extraction.json   ← AST extraction (codegraph-tools)
└── code_graph.kuzu            ← KuzuDB graph database

Schema:
  (Service) -[:CONTAINS]→ (Symbol)
  (Symbol)  -[:CALLS]→    (Symbol)
  (Symbol)  -[:HTTP_CALLS]→ (Service)
```

Queries use Kuzu Cypher. The graph is **read-only at runtime** — the Cypher Write Guard blocks any CREATE/DELETE/MERGE from the impact agent.

To rebuild the graph after applying diffs:
```bash
# From services/ directory
npx codegraph-tools extract --output codegraph-out/
```

---

## Logging

All three pipelines log structured output to stdout. Every LLM call, tool call, and harness check is logged with timestamps and prefixes:

```
[RE:ORCHESTRATOR]  >> STAGE START: ORCHESTRATOR:PARSING
[RE:PARSER]        📦 EXTRACTED: 16 services
[RE:INFERENCE]     🤖 LLM: gemini-2.5-pro | prompt=15066 chars
[RE:INFERENCE]     📊 CONFIDENCE: 15 CONFIRMED / 1 INFERRED / 4 GAP
[HARNESS] [GATE]   >> HARNESS START: service=payment-processor, diffs=2
[HARNESS] [GATE]   [T1] Syntax check via vallm (tree-sitter)... → PASS
[HARNESS] [GATE]   [T2] Security scan (23 patterns)... → PASS
[HARNESS] [GATE]   << HARNESS DONE: PASS in 29ms — errors=0 warnings=4
[ORCHESTRATOR]     📈 Best report updated: confidence=HIGH (iteration 1)
```
