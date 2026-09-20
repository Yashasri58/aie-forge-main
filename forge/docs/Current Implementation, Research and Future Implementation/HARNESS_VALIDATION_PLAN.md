# Forge Harness Validation — Implementation Plan

**Status:** Planned — next implementation phase  
**Owner:** Forge / AIE Hyderabad  
**Date:** September 2026  
**Context:** After enrichment layer (package deps, DB schemas, OpenAPI, env vars) was added to
Kuzu and all 5 agents were updated, the next step is to add harness validation across all agents
to ensure the whole pipeline is genuine and not hallucinated.

---

## Background and Motivation

### The Core Problem

An LLM agent can produce a convincing-looking output without ever doing the work. Examples in
Forge today:

- ContextGathererAgent could output `services: ["fraud-service"]` — a service that does not
  exist in the codebase. Nothing catches this.
- ImpactAgent could write a report saying "payment-processor has 3 callers" without ever
  querying the graph. Nothing verifies it used the tools.
- VerificationAgent could claim "all callers traced, confidence HIGH" without calling
  `trace_callers()` once.

### The Weather Agent Analogy

Your manager's example captures the principle exactly:

> User asks: "What is the weather in Chennai?"
> User Query Agent must: extract `chennai` and pass it to Weather Agent.
> Weather Agent must: call `get_weather("chennai")` — not answer from training data.
> Harness must verify: (1) the field was extracted, (2) the tool was actually called,
>   (3) the tool was called with the right input, (4) the answer came from the tool result.

This is exactly what is missing in Forge's impact analysis pipeline (Agents 1–3).
The code generation pipeline (Agents 4–7) is already well harnessed via DeterministicGate.

### Industry Backing

- **Spillwave, 2026:** "Instructions get followed most of the time. Contracts get enforced
  every time. Prompts persuade. Hooks enforce."
- **arXiv 2603.10060 (NabaOS), March 2026:** Tool receipt verification catches 94.2% of
  fabricated tool references at <15ms overhead.
- **Thoughtworks / Martin Fowler, April 2026:** Sensors = feedback controls that observe
  after the agent acts and produce signals for self-correction.

---

## The 5 Validation Points (applies to every agent)

```
User / upstream agent sends input
        │
        ▼  ① INPUT VALIDATION
           - Are required fields present?
           - Do named entities (services, functions) actually exist?
           - Is the format correct?
        │
        ▼  ② ACTION BOUNDARY (pre-tool check)
           - Before any tool fires: are the tool arguments valid?
           - Does the target symbol/service exist in the graph?
           - Is the tool being called appropriate for this step?
        │
        ▼  ③ TOOL RECEIPT LOGGING
           - Record every tool call: name, input, result count, timestamp
           - Minimum tool call count per agent role must be met
           - Agent cannot claim tool output it never received
        │
        ▼  ④ OUTPUT CONTRACT CHECK
           - Does the JSON response have all required fields?
           - Are field values drawn from known data (not invented)?
           - Do named services/functions in the output exist in the graph?
        │
        ▼  ⑤ ANSWER GROUNDING CHECK
           - Cross-reference claims in the output against tool receipts
           - Every service named in the report must appear in a graph query result
           - Confidence level must be justified by verified paths
```

---

## Current State of Each Agent

| Agent | ① Input | ② Action Boundary | ③ Tool Receipts | ④ Output Contract | ⑤ Grounding |
|-------|---------|-------------------|----------------|-------------------|-------------|
| ContextGathererAgent | ❌ None | ❌ None | ❌ None | ⚠️ parse_json only | ❌ None |
| ImpactAgent | ❌ None | ❌ None | ❌ None | ❌ None | ❌ None |
| VerificationAgent | ❌ None | ❌ None | ❌ None | ⚠️ parse_json only | ❌ None |
| DesignAgent | ❌ None | ✅ CoordinatorAgent | N/A | ✅ CoordinatorAgent | N/A |
| CoordinatorAgent | ✅ plan.json schema | ✅ file_exists checks | N/A | ✅ valid/errors dict | N/A |
| ImplementationAgent | ✅ reads live file | N/A | ✅ read_current_file | ✅ DeterministicGate | ✅ ContractChecker |
| VerifierAgent (codegen) | ✅ diff + plan | N/A | ✅ parse_diff | ✅ DeterministicGate | ✅ HallucinationDetector |

**Gap summary:** Agents 1–3 (impact analysis pipeline) have almost no harness validation.
Agents 5–7 (code generation pipeline) are already well covered.

---

## Implementation Items

---

### ITEM 1: Agent-to-Agent Input Contract Validator

**What:** Before passing requirements from ContextGathererAgent to ImpactAgent (at the
`confirm_requirements` gate in `orchestrator.py`), enforce that all required fields are
present and all named services exist in the graph.

**Where:** `forge/src/modules/agents/orchestrator.py` — `confirm_requirements()` method

**File to edit:** `forge/src/modules/agents/orchestrator.py`

**Code to add** (inside `confirm_requirements`, after the stage check):

```python
def _validate_requirements(self, requirements: dict) -> list[str]:
    """
    Validate requirements before passing to ImpactAgent.
    Returns list of error strings. Empty list = valid.

    Checks:
    1. Required fields present
    2. Description is non-trivial (not just whitespace)
    3. All named services exist in the codebase graph
    """
    errors = []
    known_services = self.tools.services if self.tools else []

    # Check required fields
    if not requirements.get("description", "").strip():
        errors.append("description is empty — cannot start analysis")

    # Check services exist in graph
    for svc in requirements.get("services", []):
        if known_services and svc not in known_services:
            errors.append(
                f"Service '{svc}' not found in codebase. "
                f"Known services: {', '.join(known_services)}"
            )

    # Check functions exist if specified
    if requirements.get("functions") and self.tools:
        for fn in requirements["functions"]:
            result = self.tools.search_symbols(fn)
            if result.get("count", 0) == 0:
                errors.append(
                    f"Function '{fn}' not found in codebase. "
                    f"Use search to find the correct name."
                )

    return errors
```

Then in `confirm_requirements()`, add before `_run_analysis_loop`:

```python
# HARNESS: Validate requirements before analysis starts
validation_errors = self._validate_requirements(state.requirements)
if validation_errors:
    state.stage = PipelineStage.GATHERING
    state.current_question = (
        "I found issues with the requirements before I could start analysis: "
        + "; ".join(validation_errors)
        + ". Please clarify."
    )
    state.log_activity("Requirements validation failed: " + "; ".join(validation_errors), "error")
    return state
```

**Why this matters:** Equivalent to checking "Chennai" is a valid city before passing to
the weather agent. Stops hallucinated service names from flowing into ImpactAgent.

**Effort:** ~30 lines, no new dependencies.

---

### ITEM 2: ContextGathererAgent Output Grounding

**What:** After `parse_json()` in `context_gatherer.py`, validate that every service name
in the output JSON actually exists in the graph. Remove or flag hallucinated service names.

**Where:** `forge/src/modules/agents/context_gatherer.py` — `process()` method

**File to edit:** `forge/src/modules/agents/context_gatherer.py`

**Code to add** (after `result = self.parse_json(response)` in `process()`):

```python
def _ground_output(self, result: dict) -> dict:
    """
    Remove hallucinated service and function names from agent output.
    Cross-references against the actual graph.

    Modifies result in-place and returns it.
    """
    if not _graph_tools:
        return result

    known_services = _graph_tools.services

    # Filter services to only those that exist
    raw_services = result.get("services", [])
    valid_services = [s for s in raw_services if s in known_services]
    hallucinated_services = [s for s in raw_services if s not in known_services]

    if hallucinated_services:
        # Don't silently drop — report back to agent as incomplete
        result["services"] = valid_services
        existing_note = (
            f"Note: services {hallucinated_services} were not found in the codebase "
            f"and were removed. Available services: {known_services}"
        )
        # Append to follow-up question so the agent can self-correct
        existing_q = result.get("follow_up_question") or ""
        result["follow_up_question"] = (existing_q + " " + existing_note).strip()
        result["complete"] = False  # Force another round to confirm

    return result
```

Then in `process()`, add after `result = self.parse_json(response)`:

```python
# HARNESS: Ground output against actual graph data
result = self._ground_output(result)
```

**Why this matters:** Prevents hallucinated service names from appearing in the requirements
that drive the entire impact analysis.

**Effort:** ~25 lines, no new dependencies.

---

### ITEM 3: Tool Receipt Logger

**What:** Wrap every tool function in the ImpactAgent with a receipt logger. After
`analyze_for_pipeline()` returns, verify the agent actually called graph tools.
If `_tool_receipts` is empty, the agent answered from training data — reject it.

**Where:** `forge/src/modules/agents/impact/agent.py`

**File to edit:** `forge/src/modules/agents/impact/agent.py`

**Code to add** (module level, after `_store` and `_tools` globals):

```python
import time as _time

# Receipt log — records every actual tool call in this analysis run
_tool_receipts: list[dict] = []


def _log_receipt(tool_name: str, inputs: dict, result: dict):
    """Record a tool execution receipt that the LLM cannot forge."""
    _tool_receipts.append({
        "tool": tool_name,
        "inputs": inputs,
        "result_count": len(result) if isinstance(result, (list, dict)) else 1,
        "timestamp": _time.time(),
    })


def _reset_receipts():
    """Clear receipts at the start of each new analysis run."""
    global _tool_receipts
    _tool_receipts = []


def _get_receipts() -> list[dict]:
    """Return a copy of the current receipt log."""
    return list(_tool_receipts)
```

Then wrap each tool function. Example for `analyze_impact`:

```python
def analyze_impact(symbol_name: str) -> dict:
    result = _tools.analyze_impact(symbol_name)
    _log_receipt("analyze_impact", {"symbol_name": symbol_name}, result)  # HARNESS
    return result
```

Apply the same `_log_receipt(...)` line to: `search_symbols`, `trace_call_path`,
`get_service_topology`, `query_cypher`.

**Minimum call validation** — add to `ImpactAgent.analyze_for_pipeline()` after getting
the report:

```python
# HARNESS: Verify agent actually used graph tools, not just training data
_reset_receipts()
report = await self.analyze(query)

receipts = _get_receipts()
if len(receipts) == 0:
    raise ValueError(
        "ImpactAgent produced a report without calling any graph tools. "
        "This indicates the agent answered from training data. Rejecting."
    )

graph_tools_used = [r["tool"] for r in receipts]
print(f"  [HARNESS] Tool receipts: {graph_tools_used}")
```

**Why this matters:** Directly addresses your weather agent concern — proves the agent
used the tool, not its own knowledge. Equivalent to checking that `get_weather()` was
actually invoked.

**Effort:** ~40 lines, no new dependencies.

---

### ITEM 4: ImpactAgent Report Grounding Check

**What:** After `analyze_for_pipeline()` returns the report text, scan it for service names
and verify every service mentioned actually exists in the graph. Log any hallucinated
service names as warnings in the activity log.

**Where:** `forge/src/modules/agents/orchestrator.py` — `_run_analysis_loop()` method

**File to edit:** `forge/src/modules/agents/orchestrator.py`

**Code to add** (new method on `PipelineOrchestrator`):

```python
def _check_report_grounding(self, report: str) -> list[str]:
    """
    Scan impact report for service names and verify they exist in the graph.
    Returns list of hallucinated service names found in the report.

    Pattern matched: 'SERVICE: <name>' lines in the layered report format.
    """
    import re
    if not self.tools:
        return []

    known = set(self.tools.services)
    mentioned = re.findall(r'SERVICE:\s+([\w-]+)', report)
    hallucinated = [s for s in mentioned if s and s not in known]
    return list(set(hallucinated))  # deduplicate
```

Then in `_run_analysis_loop()`, after `state.report = report`:

```python
# HARNESS: Ground report against actual graph — catch hallucinated service names
hallucinated_svcs = self._check_report_grounding(report)
if hallucinated_svcs:
    state.log_activity(
        f"HARNESS WARNING: Report mentions services not in codebase: "
        f"{hallucinated_svcs}. These may be hallucinated.",
        "warning"
    )
    # Add to gaps so verification loop investigates
    if state.verification is None:
        state.verification = {}
    existing_gaps = state.verification.get("gaps", [])
    for svc in hallucinated_svcs:
        existing_gaps.append({
            "missing_caller": "UNKNOWN",
            "missing_caller_service": svc,
            "should_call": "VERIFY_EXISTS",
            "should_be_in_layer": 0,
            "evidence": "harness_grounding_check — service not in graph"
        })
    state.verification["gaps"] = existing_gaps
```

**Why this matters:** If ImpactAgent writes "SERVICE: fraud-service" and that service
doesn't exist, this catches it immediately and flags it for the verification loop.

**Effort:** ~25 lines, no new dependencies.

---

### ITEM 5: VerificationAgent Tool Receipt Check

**What:** VerificationAgent must call `trace_callers()` for every Layer 0 symbol in the
report. Add a minimum call count check — if it returned a "complete" verdict without
calling any tools, reject it.

**Where:** `forge/src/modules/agents/verification_agent.py` — `verify()` method

**File to edit:** `forge/src/modules/agents/verification_agent.py`

**Code to add** (module level):

```python
_verification_receipts: list[dict] = []

def _log_verification_receipt(tool_name: str, symbol: str, result_count: int):
    _verification_receipts.append({
        "tool": tool_name,
        "symbol": symbol,
        "result_count": result_count,
        "timestamp": __import__("time").time()
    })
```

Wrap `trace_callers` and `trace_callees`:

```python
def trace_callers(symbol: str, max_depth: int = 2) -> dict:
    if _graph_tools:
        result = _graph_tools.trace_call_path(symbol, direction="incoming", max_depth=max_depth)
        _log_verification_receipt("trace_callers", symbol, len(result.get("paths", [])))  # HARNESS
        return result
    return {"paths": []}
```

In `verify()`, after `response = await self.run(prompt)`:

```python
# HARNESS: Verify agent actually traced call paths
receipts = [r for r in _verification_receipts if r["tool"] in ("trace_callers", "trace_callees")]

if len(symbols) > 0 and len(receipts) == 0:
    # Agent claimed to verify without using any tools
    return {
        "complete": False,
        "confidence": "LOW",
        "gaps": [{
            "missing_caller": "UNKNOWN",
            "missing_caller_service": "UNKNOWN",
            "should_call": "UNKNOWN",
            "should_be_in_layer": 1,
            "evidence": "harness_receipt_check — verification agent made no tool calls"
        }],
        "verified_paths": 0,
        "recommendation": "Verification agent did not use graph tools. Re-running."
    }
```

**Why this matters:** Verification agent is the last guard before human approval.
If it claims "complete" without tracing any paths, it has self-certified a hallucinated
report. This check catches that.

**Effort:** ~35 lines, no new dependencies.

---

### ITEM 6: Action Boundary on Tool Arguments (ImpactAgent)

**What:** Before `query_cypher()` executes a raw Cypher query, validate the query is
read-only (no WRITE/DELETE/MERGE). Before `analyze_impact()` runs, verify the symbol
name is non-empty and reasonably formatted.

**Where:** `forge/src/modules/agents/impact/agent.py` — tool wrapper functions

**File to edit:** `forge/src/modules/agents/impact/agent.py`

**Code to add:**

```python
def query_cypher(cypher_query: str) -> dict:
    # HARNESS: Action boundary — block write operations
    _FORBIDDEN = ("CREATE ", "DELETE ", "MERGE ", "SET ", "REMOVE ", "DROP ")
    upper = cypher_query.upper().strip()
    for kw in _FORBIDDEN:
        if upper.startswith(kw) or f"\n{kw}" in cypher_query.upper():
            return {
                "error": f"Write operation '{kw.strip()}' is not allowed. "
                         "Only read queries are permitted.",
                "query": cypher_query,
            }
    # ... existing implementation
    result = _store.query(cypher_query)
    _log_receipt("query_cypher", {"query": cypher_query[:100]}, result)
    return {"query": cypher_query, "results": result[:100], ...}


def analyze_impact(symbol_name: str) -> dict:
    # HARNESS: Validate input before hitting the graph
    if not symbol_name or not symbol_name.strip():
        return {"error": "symbol_name cannot be empty"}
    if len(symbol_name) > 200:
        return {"error": "symbol_name too long — likely a malformed input"}
    # ... existing implementation
```

**Why this matters:** A write Cypher query could corrupt the Kuzu database.
Even if the agent is well-intentioned, a malformed prompt could cause it to issue
destructive queries. This is the "action boundary" pattern from industry research —
deterministic check between decision and side effect.

**Effort:** ~20 lines, no new dependencies.

---

## Implementation Order

Build in this order — each item builds on the previous:

```
Phase 1 — Input and Output Grounding (low risk, high value, no infrastructure needed)
  ├── ITEM 2: ContextGathererAgent output grounding       (~25 lines)
  └── ITEM 4: ImpactAgent report grounding check          (~25 lines)

Phase 2 — Action Boundaries (safety, prevents data corruption)
  └── ITEM 6: query_cypher write guard + analyze_impact input check  (~20 lines)

Phase 3 — Agent-to-Agent Contract (the main gate)
  └── ITEM 1: confirm_requirements input contract validator  (~30 lines)

Phase 4 — Tool Receipt Logging (proof of work)
  ├── ITEM 3: ImpactAgent tool receipt logger               (~40 lines)
  └── ITEM 5: VerificationAgent tool receipt check          (~35 lines)
```

Total: ~175 lines of Python across 3 files. No new pip dependencies.

---

## Files to Edit

| File | Items | Lines Added |
|------|-------|------------|
| `forge/src/modules/agents/orchestrator.py` | ITEM 1, ITEM 4 | ~55 |
| `forge/src/modules/agents/context_gatherer.py` | ITEM 2 | ~25 |
| `forge/src/modules/agents/impact/agent.py` | ITEM 3, ITEM 6 | ~60 |
| `forge/src/modules/agents/verification_agent.py` | ITEM 5 | ~35 |

---

## What This Achieves

After implementation, the pipeline guarantee becomes:

```
User requirement
      │
      ▼
ContextGathererAgent
      │ ← ITEM 2: services exist in graph
      ▼
[GATE] confirm_requirements
      │ ← ITEM 1: all fields valid, services real, functions exist
      ▼
ImpactAgent
      │ ← ITEM 6: no write queries, symbol names valid
      │ ← ITEM 3: tool receipts prove graph was queried
      │ ← ITEM 4: report services cross-checked against graph
      ▼
VerificationAgent
      │ ← ITEM 5: trace_callers actually called
      ▼
Human Approval
```

Every stage has a deterministic check. The report that reaches the human is provably
grounded in actual graph data — not the model's training data.

---

## Relationship to Existing DeterministicGate

The DeterministicGate (`forge/src/modules/codegen/harness/`) already covers the code
generation pipeline thoroughly:

- `SyntaxChecker` — node --check on every diff
- `ImportResolver` — require() paths verified on disk
- `ContractChecker` — function signatures match plan.json
- `HallucinationDetector` — calls to non-existent functions flagged
- `SecurityScanner` — hardcoded secrets, eval(), SQL injection

The items above bring the **impact analysis pipeline** to the same standard the code
generation pipeline already meets. Together they form a complete harness:

```
┌────────────────────────────────────────────────────────┐
│  IMPACT ANALYSIS HARNESS (Items 1–6, to be built)      │
│  Service grounding, tool receipts, action boundaries   │
├────────────────────────────────────────────────────────┤
│  CODE GENERATION HARNESS (DeterministicGate, built)    │
│  Syntax, imports, contracts, hallucination, security   │
└────────────────────────────────────────────────────────┘
```

---

## Test Cases for Each Item

Once implemented, each item should be validated with these cases:

| Item | Test Input | Expected Harness Behaviour |
|------|-----------|--------------------------|
| ITEM 1 | `services: ["fraud-service"]` | Rejected at gate, agent asked to clarify |
| ITEM 1 | `description: ""` | Rejected at gate, description required |
| ITEM 2 | Agent returns `services: ["nonexistent-svc"]` | Removed from output, complete=false |
| ITEM 3 | Agent produces report without tool calls | Rejected with "no tool receipts" error |
| ITEM 4 | Report contains `SERVICE: ghost-service` | Warning logged, gap added to verification |
| ITEM 5 | Verification returns complete=true, 0 tool calls | Overridden to complete=false, LOW confidence |
| ITEM 6 | `query_cypher("DELETE (n) RETURN n")` | Blocked with write operation error |

---

*Document prepared: September 2026*  
*Based on: research from arXiv 2603.10060, Spillwave Harness Engineering Guide,
Thoughtworks/Martin Fowler harness engineering article, and Forge codebase analysis.*
