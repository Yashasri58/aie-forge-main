# Reverse Engineering Pipeline — Deep Research Findings

**Status:** Research complete — informs implementation approach  
**Date:** September 2026  
**Sources:** arXiv, GitHub, PyPI, Praetorian, MongoDB, industry case studies

---

## Overview: What the Research Revealed

The research uncovered implementations across **5 distinct categories**, ranging from pure
programmatic log analysis to full multi-agent AI pipelines. Each category offers something
valuable. The combination is what makes the Forge implementation genuinely differentiated.

---

## CATEGORY 1: Academic Multi-Agent Reverse Engineering Frameworks

These are the gold mines — peer-reviewed, tested systems doing exactly what we need.

---

### 1.1 Reversa (arXiv 2605.18684 — May 2026)

**The most directly relevant system found.**

Reversa is a production framework specifically for reverse engineering legacy software into
operational specifications. Published by Federal Institute of Goias, Brazil.

**Architecture — 6 specialized agents:**

| Agent | Role | Output Artifact |
|-------|------|----------------|
| `reversa-scout` | Maps project surface, stack, dependencies, entry points | Inventory + evidence signals |
| `reversa-archaeologist` | Deep technical analysis of modules and internal structures | Modular analysis + technical facts |
| `reversa-detective` | Extracts business rules, states, permissions, implicit exceptions | Recovered rules + gaps + decisions |
| `reversa-architect` | Synthesizes architecture, dependencies, data, impact across components | Architecture + diagrams + impact matrix |
| `reversa-writer` | Converts extracted knowledge into unit-level specifications | requirements.md, design.md, tasks.md |
| `reversa-reviewer` | Reviews claims, confidence, and gaps for human validation | Confidence report + questions + gaps |

**Confidence model (the most important innovation):**
```
CONFIRMED — direct evidence in code or verifiable artifact
INFERRED  — supported by patterns, names, flows, structure
GAP       — cannot be determined safely, needs human validation
```

**Key results from COBOL→Go ATM case study:**
- 517 claims classified: 490 confirmed, 24 inferred, 3 gaps
- Internal confidence index: 97.1%
- 10 registered gaps (3 critical, 3 moderate, 2 cosmetic, 2 out of scope)
- 53 Gherkin parity scenarios generated automatically
- 9/11 reconstruction tasks completed

**GitHub:** `github.com/sandeco/reversa` — installable Node.js CLI  
**Installs as skills into:** Claude Code, Codex, Cursor, Gemini CLI, Kiro, Copilot, Aider, etc.

**What to borrow for Forge:**
- The 3-tier confidence model (CONFIRMED/INFERRED/GAP) — adopt exactly this
- The agent role names and their distinct responsibilities
- The artifact structure: `_reversa_sdd/` containing inventory, analysis, confidence-report
- The "reviewer agent" pattern — a dedicated agent to re-read and reclassify fragile claims
- Gherkin scenario generation from reverse-engineered specs

---

### 1.2 AgentModernize / Behavioral Specification Graph (arXiv 2605.17535 — May 2026)

**The best implementation of "business logic preservation" from black-box systems.**

Framework from University of Texas Arlington for legacy-to-modern code migration.
Key insight: business logic must be made **explicit and inspectable** before any
generation happens.

**Architecture — 4 agents + BSG intermediate artifact:**

```
Agent 1: Legacy Analyzer
   → extracts explicit AND implicit business rules
   → phases: structural parsing, rule extraction, constraint discovery
   → outputs: Business Rule Inventory (JSON)

                  ↓ BSG (TRUST BOUNDARY)

Agent 2: Specification Generator
   → transforms BRI into Behavioral Specification Graph
   → BSG = directed acyclic graph with:
       - operation nodes (discrete business operations)
       - pre/post-conditions per node
       - global invariants
       - edge labels: sequence, conditional, parallel, error
       - confidence score + source location per rule
   → outputs: BSG JSON

                  ↓

Agent 3: Modernization Transformer
   → generates modern implementation FROM BSG (not from legacy code directly)
   → follows 4 principles: operation-to-endpoint, contract preservation,
     data model derivation, flow preservation

                  ↓

Agent 4: Equivalence Validator
   → generates test cases from BSG spec
   → checks: contract verification, boundary testing, differential trace analysis
   → feeds failures back to Agent 3 (max 3 iterations)
```

**BSG node example (this is brilliant):**
```json
{
  "operation": "ValidateDisconnectOrder",
  "source_rule": "BR-004",
  "source_location": "ORDER_VALIDATION.cob:118-142",
  "preconditions": [
    "account_status in ['ACTIVE', 'SUSPENDED']",
    "order_type == 'DISCONNECT'"
  ],
  "postconditions": [
    "suspended accounts proceed for disconnect orders",
    "non-disconnect orders rejected for suspended"
  ],
  "invariants": ["order_total == sum(line_items)"],
  "confidence": "high"
}
```

**Results:**
- BSG captures 92.3% recall, 90.2% precision of gold-standard business rules
- Multi-agent (23%) nearly doubles single-prompt baseline (12.4%)
- The bottleneck is code generation, NOT rule extraction
- For regulated industries: the BSG provides the audit trail single-prompt cannot

**Tech stack:** LangGraph + Python, GPT-4o-mini, cost <$15 for full evaluation

**What to borrow for Forge:**
- The BSG concept adapted to our use case: a structured intermediate artifact
  (call it **Application Specification Graph / ASG**) that captures all
  inferred behavior before the spec document is written
- The explicit/implicit rule categorization
- The "trust boundary" concept: extraction upstream, generation downstream
- The feedback loop: validator finds gaps, inference agent fills them

---

### 1.3 BlackBoxToBlueprint (arXiv 2507.00180 — 2026)

**The only approach that works when you have NO source code — just I/O behavior.**

Uses Reinforcement Learning to extract business logic from systems treated as black boxes.

**Approach:**
1. RL agent explores the input space to find critical decision boundaries
2. Rewards actions that cause meaningful changes in output (counterfactual analysis)
3. State transitions (where output changes) are collected and clustered with K-Means
4. Decision trees trained on clusters to extract human-readable rules

**Why relevant to Forge:**
- GPP is a black box — we have no source code
- Logs = observations of I/O behavior under various inputs
- This approach treats logs exactly as evidence of system behavior at boundaries
- The Kafka consumer lag and payment decline patterns are "counterfactual transitions"

**What to borrow:**
- Treat every ERROR/WARN/409/402 log as a "decision boundary observation"
- Cluster similar decision patterns across traces
- Extract rules from those clusters: "when X condition → Y behavior"

---

### 1.4 ErrorPrism (arXiv — ByteDance, 2026)

**97% accuracy reconstructing error propagation paths in 67 production microservices.**

ByteDance built a system to reconstruct error propagation paths from logs.
Evaluated on real production microservices.

**Their approach:**
- Log template mining to extract event types
- Trace correlation to link events across service boundaries
- Graph construction: service call graph from trace IDs
- Path reconstruction: "which service caused which error in which other service"

**Results:** 97.0% accuracy on 102 real-world errors. Outperforms both static analysis
and LLM-based approaches.

**What to borrow:**
- Log template mining (exact implementation of trace-to-graph conversion)
- Error propagation path as a key spec output (the "Saga rollback" we see in our log
  is exactly this — payment-processor → order-service inventory release chain)

---

### 1.5 Microservice Architecture Reconstruction from Log Traces (arXiv 2207.02988)

**Academic comparison of static vs. dynamic (log-based) reconstruction methods.**

Key finding: "Log trace-based methods outperform static analysis for cross-service
dependency recovery because static analysis cannot see the HTTP calls."

**Two approaches compared:**
1. Static: analyze source code imports, annotations
2. Dynamic: analyze runtime log traces (our scenario — we only have logs)

Dynamic analysis advantages for our case:
- Captures actual runtime behavior (what happens, not what code says)
- Catches HTTP calls that static analysis misses
- Captures conditional flows that only appear under certain inputs
- Works without source code ← this is us

**What to borrow:**
- Dynamic analysis is the right approach for our use case — confirmed by academia
- Trace correlation methodology (group by traceId → call sequence)
- Service dependency edge construction from co-occurring service log lines

---

## CATEGORY 2: Traffic and Log-Based API Discovery Tools

These are programmable, production-ready tools. Less AI, more deterministic.

---

### 2.1 Vespasian (Praetorian, April 2026)

**The gold standard for API discovery from traffic.**

`github.com/praetorian-inc/vespasian` — Go, actively maintained (167 commits, May 2026)

**What it does:**
- Observes actual HTTP traffic (headless browser or proxy captures)
- Uses classification heuristics + active probing
- Produces structured API specifications: OpenAPI, GraphQL SDL, WSDL, WebSocket

**How it works:**
```
Traffic capture (headless browser / mitmproxy)
      ↓
Endpoint classification (is this REST? GraphQL? SOAP? WebSocket?)
      ↓
Schema inference (request/response body structure)
      ↓
OpenAPI 3.1 spec generation
```

**Key innovation:** Active probing — after observing an endpoint, it probes it
with variations to discover query parameters, headers, and error responses.

**Why relevant:** Our log file contains the equivalent of traffic observations.
The trace patterns are HTTP request/response pairs. Vespasian's classification
heuristics can be adapted to work from log lines instead of raw traffic.

**What to borrow:**
- Endpoint classification algorithm (REST vs event vs health check)
- Schema inference from observed request/response patterns
- OpenAPI generation template (adapt to generate from log evidence)

---

### 2.2 mitmproxy2swagger (Python, widely used)

`github.com/alufers/mitmproxy2swagger`

Automatically converts mitmproxy traffic captures to OpenAPI 3.0 specifications.

**Approach:**
1. Intercept HTTP traffic via mitmproxy (man-in-the-middle)
2. Record all request/response pairs
3. Parse and group by URL pattern (normalize path parameters: `/users/123` → `/users/{id}`)
4. Infer request body schema from JSON
5. Generate OpenAPI YAML

**Process:**
```python
mitmproxy2swagger -i flows -o spec.yml -p https://api.example.com -f flow
```

**Adaptation for logs:**
The log file contains `POST /api/v1/orders` and `Response 201 Created in 319ms`.
We can reconstruct the same information from log lines that mitmproxy2swagger
gets from actual traffic. The path normalization logic is directly reusable.

**What to borrow:**
- URL path normalization (`/orders/ORD-20260917-5541` → `/orders/{orderId}`)
- HTTP method + path grouping algorithm
- OpenAPI YAML template generation

---

### 2.3 DocuRift

`github.com/tienanr/docurift` — Python proxy server

Generates OpenAPI specs and Postman collections by acting as a transparent proxy.
Captures real API traffic and generates comprehensive documentation.

**Key feature:** Works as middleware — no code changes needed to the target system.

**What to borrow:**
- The "proxy as observer" pattern can be adapted to "log as observer"
- Grouping algorithm for distinguishing stable path templates from instance IDs

---

## CATEGORY 3: Log Parsing and Template Mining Packages

These are deterministic, battle-tested Python packages. No AI needed.

---

### 3.1 Drain3 (PyPI: `drain3`)

**The most widely used structured log parser for production systems.**

`github.com/logpai/logparser` / `pip install drain3`

**What it does:**
- Online log template mining from a stream of log messages
- Groups similar log lines into clusters: "Stock check: SKU-<*> available=<*>"
- Extracts the variable parts (parameters) separately from the template
- Fixed-depth parse tree — runs in milliseconds even on millions of lines

**Example:**
```
Input:  "SKU-100: available=142, reserved=2 -> OK"
Input:  "SKU-245: available=18, reserved=1 -> OK"
Output template: "SKU-<*>: available=<*>, reserved=<*> -> OK"
Parameters:      [("SKU-100", "142", "2"), ("SKU-245", "18", "1")]
```

**Usage:**
```python
from drain3 import TemplateMiner
miner = TemplateMiner()
for line in log_lines:
    result = miner.add_log_message(line)
    # result.cluster = the template group
    # result.cluster.log_template_tokens = ["SKU-<*>:", "available=<*>", ...]
```

**Why this is a diamond mine:**
- Our log lines already have structure, but Drain3 extracts the TEMPLATE from variable data
- "ORD-20260917-5541" and "ORD-20260917-5542" both match "ORD-<DATE>-<ID>"
- This is how we separate signal from noise without LLM involvement

**What to use it for:**
- Stage 1 of our pipeline: template extraction before any LLM call
- Reduces 50 log lines → 15 templates → much cheaper LLM context
- Identifies recurring patterns (like the retry pattern: "attempt 1/3", "attempt 2/3")

---

### 3.2 logpai/logparser (GitHub)

The benchmark toolkit that Drain3 is part of. Contains 13 log parsing algorithms:
Drain, Spell, AEL, IPLoM, LKE, LogSig, MoLFI, and more.

For structured logs (our case), Drain is the best choice.
For unstructured logs (future GPP logs that might not have trace IDs), Spell is better.

---

### 3.3 Matryoshka (GitHub: `github.com/julien-piet/matryoshka`)

**LLM-powered log ingestion — first end-to-end system using LLMs for log parsing.**

Combines LLM semantic understanding with deterministic structure extraction.

**Approach:**
- Uses LLM to understand the semantic meaning of log lines
- Generates "schema-aware" parsers that extract meaningful field values
- Handles semi-structured and unstructured logs that Drain cannot parse

**What to borrow:**
- For GPP logs that don't follow a clean structure, Matryoshka's hybrid approach
- Use Drain3 for structured lines, Matryoshka (or LLM) for unstructured ones

---

## CATEGORY 4: LLM-Based Log Analysis Research

Academic findings on what LLMs can and cannot do with logs.

---

### 4.1 LLM4Log Systematic Review (arXiv 2604.16359 — 2026)

**The most comprehensive survey of LLM-based log analysis.**

**What LLMs are good at in log analysis:**

| Task | LLM Performance | Notes |
|------|----------------|-------|
| Log template extraction | High | Better than Drain on ambiguous/noisy logs |
| Anomaly detection | High | Semantic understanding catches patterns regex misses |
| Root cause analysis | High | Can reason across multiple log lines |
| Failure prediction | Medium | Needs historical patterns |
| Log summarization | Very High | Natural fit for LLMs |
| Architecture inference | Medium | Strong but needs structured input |

**Key finding:**
> "The main deployment risks of LLMs for log analysis are: context limits, latency
> and cost, privacy constraints, and hallucinations."

**Context limit problem** — critical for our design:
> "A single 30-minute incident window can generate over two million log lines across
> many interdependent services — approximately 1.2 billion characters, or 26,000x
> the 46,000-character per-request budget of our enterprise LLM API."

**Solution:** Pre-process with Drain3 to extract templates + trace groups,
then feed compressed representation to the LLM. Reduce 2M lines to 200 patterns.

---

### 4.2 Neuro-Symbolic Log Analysis (arXiv 2607.08529)

**Hybrid approach combining deterministic parsing with LLM reasoning.**

Key insight: Use symbolic (rule-based) methods for what they're good at
(parsing, grouping, counting) and LLMs for semantic reasoning only.

Their architecture:
```
Raw logs
   ↓ Symbolic: parse, group, extract templates (fast, deterministic)
   ↓ Neural: understand semantics, infer causality, generate explanations
Output: structured analysis
```

This is exactly our proposed architecture. The research validates the approach.

---

## CATEGORY 5: Graph-Based Service Topology Discovery

How production systems build dependency graphs from traces.

---

### 5.1 OpenTelemetry Dependency Graph (Industry Standard, 2026)

OpenTelemetry traces contain exactly what our logs contain — traceId + spanId.
The OTel spec shows how to reconstruct dependency graphs from this data:

```python
# From OTel trace data (same structure as our logs):
# traceId = groups all spans of one request
# spanId = identifies one service's handling of that request
# parentSpanId = links child to parent (implicit in our logs via ordering)

def build_dependency_graph(traces):
    graph = {}
    for trace in traces:
        spans = sorted(trace.spans, by='timestamp')
        for i, span in enumerate(spans[1:], 1):
            parent = spans[i-1]
            graph.setdefault(parent.service, set()).add(span.service)
    return graph
```

**Our log already has this!** The ordering of service tags within a traceId IS the
call sequence. `api-gateway` → `auth-service` → `order-service` → `inventory-service`
is directly readable from the traceId=a1b2c3d4-0001 group.

---

### 5.2 DGG (Service Dependency Graph Generator, GitHub)

`github.com/dufanrong/DGG`

Generates service dependency graphs from benchmark traces.
Key feature: adds "production-level characteristics" from real trace data.

**Algorithm:**
1. Parse all traces
2. Extract service-to-service transitions per trace
3. Build frequency matrix (how often A→B vs A→C?)
4. Derive weighted dependency graph
5. Identify critical paths (most frequently traversed)

**What to borrow:**
- Weighted edge construction (service A calls service B in 85% of order traces)
- Critical path identification

---

### 5.3 Model Discovery (arXiv 2506.11176 — "Lightweight Alternative to Chaos Engineering")

**Automated CI/CD step that extracts a live dependency graph from trace data.**

Key finding:
> "Model discovery — extracting a live dependency graph from trace data — is sufficient
> for accurate resilience prediction. This lightweight representation outperforms
> manually maintained architecture diagrams."

This confirms that log-derived graphs are MORE ACCURATE than hand-drawn diagrams
because they reflect actual runtime behavior.

---

## CATEGORY 6: Spec Generation from Code / Text

Tools specifically for generating specifications from existing artifacts.

---

### 6.1 cc-rsg / specback (GitHub)

`github.com/daishir0/cc-rsg` / `github.com/nekolife1984/specback`

General-purpose frameworks for automatically generating specification documents
from legacy or active codebases. Uses Claude Code / Codex / OpenCode as the engine.

**specback specifically bills itself as:**
> "Reverse Spec Generator: code → spec multi-agent skill for Claude Code / Codex /
> OpenCode / Copilot / Cursor"

**Pattern used:**
1. Read source code in chunks (file by file)
2. Ask LLM: "What does this code do? What are the business rules?"
3. Accumulate into a structured spec document
4. Final pass: synthesize all chunks into coherent documentation

**What to borrow:**
- The chunking strategy for large log files
- The accumulation pattern (build spec incrementally, not in one shot)
- The final synthesis pass

---

### 6.2 OpenLore (GitHub: `clay-good/OpenLore`)

Interesting approach: treats the LLM as a "code archaeologist".

Their AGENTS.md prompt:
> "You are a 'code archaeologist' — your job is to reverse-engineer OpenSpec
> specifications from existing codebases. You document what code ACTUALLY DOES,
> not what you imagine it should do."

The "code archaeologist" framing is perfect for our use case.
Adapted: "You are a log archaeologist — your job is to reverse-engineer system
behavior from observed runtime logs."

---

## Synthesis: Implementation Approach for Forge

Based on all research, the optimal implementation combines 3 layers:

### Layer 1: Deterministic Pre-Processing (no LLM, fast, cheap)

**Tools:** Drain3, custom regex, Python stdlib

```python
# 1a. Parse log lines into structured events
log_events = parse_log_lines(raw_log)  # regex

# 1b. Group by traceId (reconstruct request flows)
traces = group_by_trace_id(log_events)

# 1c. Extract log templates (remove variable data)
templates = drain3_mine_templates(log_events)

# 1d. Build service dependency graph
dep_graph = build_graph_from_traces(traces)

# 1e. Extract endpoint inventory
endpoints = extract_endpoints(log_events)  # regex on URL patterns

# 1f. Detect patterns
patterns = detect_resilience_patterns(log_events)  # retry count, saga keywords
```

**Output:** `extracted_facts.json` — structured, compact, LLM-ready

### Layer 2: AI Inference (LLM, expensive, high-value)

**Framework:** Inspired by Reversa + AgentModernize BSG  
**Model:** Gemini 2.5 Pro (reasoning tasks)

```
InferenceAgent (equivalent to Reversa's detective + architect + writer)
  Input: extracted_facts.json (compact, structured)
  Task: Produce Application Specification Graph (ASG)
     - Node per service (preconditions, postconditions, invariants)
     - Edge per dependency (sync HTTP or async Kafka)
     - Business rule per flow step
     - Confidence: CONFIRMED/INFERRED/GAP
```

### Layer 3: Spec Writing (LLM, Gemini Pro)

```
SpecWriterAgent (equivalent to Reversa's writer)
  Input: ASG JSON
  Task: Generate 11 Markdown spec sections
  Constraint: Every claim must cite evidence from extracted_facts
  Output: confidence-tagged spec documents
```

### Layer 4: Gap Review (LLM, Gemini Flash)

```
GapReviewAgent (equivalent to Reversa's reviewer)
  Input: draft specs
  Task: 
    - Re-read every CONFIRMED claim, verify it has evidence
    - Reclassify fragile CONFIRMED claims as INFERRED
    - Identify GAPS where evidence is missing
  Output: confidence-report.md, gaps.md, questions.md
```

---

## Key Packages to Install

```
# Log parsing
drain3                    # template mining from logs
logparser                 # full logpai toolkit (includes Drain, Spell, AEL)

# Graph construction
networkx                  # build and analyze dependency graphs (already in Forge)
# kuzu                    # already in Forge — use for persisting the ASG

# Log utilities
python-dateutil           # parse timestamp formats
regex                     # extended regex for log line parsing

# Optional: traffic analysis
mitmproxy                 # if actual live traffic capture is needed in future
```

No new LLM packages — all existing Gemini ADK infrastructure is sufficient.

---

## Key Design Decisions (Research-Backed)

| Decision | Recommendation | Research Basis |
|---------|---------------|----------------|
| Pre-process before LLM | YES — use Drain3 | LLM4Log: context limits kill direct LLM log analysis |
| Dynamic vs static analysis | Dynamic (log-based) | arXiv 2207.02988: log traces outperform static for cross-service discovery |
| Confidence model | 3-tier: CONFIRMED/INFERRED/GAP | Reversa: explicit uncertainty is safer than fluent but fragile docs |
| BSG-style intermediate artifact | YES — create ASG JSON | AgentModernize: extraction bottleneck is NOT the LLM; code gen is |
| Separate extraction from writing | YES | Reversa: different roles, different cognitive tasks, more auditable |
| Feedback loop (max 3x) | YES | AgentModernize: feedback helps on correctable errors |
| Confidence scoring per claim | YES | AgentModernize BSG: per-rule confidence + source location |
| RL for implicit rules | NO (for POC) | BlackBoxToBlueprint: powerful but needs more data than one log file |
| Gherkin scenarios from spec | YES (future) | Reversa: 53 scenarios auto-generated from ATM spec |

---

## The Most Valuable Insight

**From AgentModernize (p.17 of paper):**

> "The BSG captures 92.3% of gold-standard rules at 90.2% precision.
> The bottleneck is code generation, not extraction.
> If the BSG looks right after Agent 2, the problem is downstream."

For our use case (spec generation, not code generation), this means:

**The extraction and inference step is the most important step.**  
If we extract the facts correctly and build the ASG correctly, the spec writing
(our final step) is relatively easy. Invest effort in Stage 1+2 (deterministic
parsing + inference), not in Stage 5 (spec formatting).

---

## What Makes Forge's Approach Differentiated

Compared to everything found in research:

1. **Existing systems work from source code.** Reversa, AgentModernize, all work
   because they have the code. We work from **logs only** — harder problem,
   but more realistic for third-party vendor scenarios.

2. **The ASG (adapted BSG) persisted in Kuzu.** No academic paper persists the
   intermediate artifact in a graph database that can be queried later.
   Our ASG in Kuzu = queryable, evolvable, incrementally updatable.

3. **Connected to the build pipeline.** Reversa produces specs for humans.
   Forge produces specs that feed directly into Pipeline 2 (code generation).
   The reverse-engineered spec IS the impact report context for building the system.

4. **Enrichment already done.** Our existing enrichment layer (packages, DB schemas,
   OpenAPI, env vars) means when we eventually build the system, we already have
   the technology stack analysis done.

---

*Research completed: September 2026*  
*Key papers: arXiv 2605.18684 (Reversa), arXiv 2605.17535 (AgentModernize/BSG),*  
*arXiv 2507.00180 (BlackBoxToBlueprint), arXiv 2207.02988 (Microservice Reconstruction),*  
*arXiv 2607.08529 (Neuro-Symbolic Log Analysis), arXiv 2604.16359 (LLM4Log Survey)*  
*Key tools: Drain3 (PyPI), Vespasian (Praetorian), mitmproxy2swagger, specback, Reversa CLI*
