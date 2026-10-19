# Forge Harness Components Report
**Scope:** Complete documentation of all harness components, their implementation, and usage throughout the codebase.

---

## Executive Summary

The Forge platform implements a comprehensive **verification harness system** following the principle:

> **The LLM is stateless compute — it proposes. The harness is deterministic truth — it verifies.**

The harness is divided into **three subsystems**:

| Subsystem | Location | Purpose |
|-----------|----------|---------|
| **Agent Harness** | `src/modules/agents/harness_utils.py` | Guards the impact-analysis and context-gathering pipeline |
| **Code-Gen Harness** | `src/modules/codegen/harness/` | Guards the code-generation and diff-verification pipeline |
| **Reverse-Engineering Harness** | `src/modules/reverse_engineer/harness.py` | Guards the log-to-spec inference pipeline |

**Total: 25 harness components**

---

## Table of Contents

1. [Agent Harness Components](#1-agent-harness-components)
2. [Code-Generation Harness Components](#2-code-generation-harness-components)
3. [Reverse-Engineering Harness Components](#3-reverse-engineering-harness-components)
4. [Integration Points](#4-integration-points)
5. [Component Quick Reference](#5-component-quick-reference)

---

## 1. Agent Harness Components

**File:** `forge/src/modules/agents/harness_utils.py`  
**Consumed by:** `impact_agent.py`, `context_gatherer.py`, `orchestrator.py`

### 1.1 Cypher Write Guard (Policy Gate)

**Function:** `check_cypher_safe(query: str) → (bool, str)`

**What it does:**  
Intercepts every Cypher query the impact agent tries to run against the KuzuDB code graph. **Blocks any query** that begins with a write keyword:

```python
_WRITE_OPS = frozenset([
    "CREATE ", "DELETE ", "MERGE ", "SET ", "REMOVE ",
    "DROP ", "DETACH ", "LOAD ",
])
```

**How it works:**
- Strips and uppercases the query
- Checks if it starts with or contains any write operation keyword
- Returns `(False, error_message)` with an actionable correction hint for the LLM

**Example:**
```
Input:  "CREATE (s:Symbol {name: 'newFn'})"
Output: (False, "Write operation 'CREATE' is not allowed on the code graph.
         Only read queries are permitted. Use MATCH/RETURN to query data.")
```

**Where called:** Every `query_cypher` tool invocation in `impact_agent.py`

---

### 1.2 Symbol Name Validator (Policy Gate)

**Function:** `check_symbol_name(name: str) → (bool, str)`

**What it does:**  
Validates the `symbol_name` argument before graph lookup tools execute.

**Checks:**
1. Name is not empty
2. Name is ≤200 characters (catches malformed/injected input)
3. No forbidden characters: `;`, `--`, `/*`, `\n`, `\r`

**Where called:** `search_symbols` and `get_symbol` tool wrappers in `impact_agent.py`

---

### 1.3 Tool Receipt Log

**Functions:**
- `receipts_reset()` — Clear at start of each analysis run
- `receipts_log(tool_name, input_preview, result_count)` — Record each tool call
- `receipts_get()` — Retrieve the log
- `receipts_assert_used(min_calls=1)` — Assert minimum tool usage

**What it does:**  
Proves that the LLM agent actually used tools (graph queries) rather than generating reports from training data. Uses thread-local storage for parallel safety.

**Example failure:**
```
"ImpactAgent produced a report with only 0 graph tool call(s) (minimum required: 1).
 Tools called: none. This suggests the report was generated from training data."
```

**Where called:**
- `receipts_reset()` at start of `pipeline.analyze()`
- `receipts_log()` after every successful tool invocation
- `receipts_assert_used()` before accepting the final report

---

### 1.4 Budget Enforcer

**Class:** `BudgetEnforcer(max_llm_calls=50, max_tool_calls=200, max_seconds=600)`

**Methods:**
- `record_llm_call()` / `record_tool_call()` — Track usage
- `check() → (bool, str)` — Check if within budget
- `get_budget_message() → Optional[str]` — Get contextual warning

**What it does:**  
Caps resources per analysis run to prevent runaway loops:
- Maximum 50 LLM calls
- Maximum 200 tool calls  
- Maximum 600 seconds wall-clock time

**Budget warnings injected into context:**
- At 10 remaining: "Note: 10 turns remaining"
- At 5 remaining: "Finish current service analysis, don't start new ones"
- At 2 remaining: "**STOP all new analysis. Write the final report NOW.**"

**Where called:** Before each LLM turn in `impact_agent.py`

---

### 1.5 Loop Detector

**Class:** `LoopDetector(window=5, threshold=3)`

**Methods:**
- `record(tool_name, inputs)` — Record a tool call
- `check() → (bool, str)` — Detect loops

**What it does:**  
Detects when an agent calls the same tool with identical arguments 3+ times within a sliding window of 5 calls — indicating the agent is stuck.

**Intervention message:**
```
"[HARNESS LOOP DETECTED] You have called 'search_symbols' with the same arguments
 3 times without new results. Stop repeating this call. Try a different tool or
 different input."
```

**Where called:** Tool execution wrapper in `impact_agent.py`, around every tool dispatch

---

### 1.6 Prompt Injection Sanitizer

**Function:** `sanitize_message(msg: str) → (str, bool)`

**What it does:**  
Scans user input for known prompt injection patterns:

```python
_INJECTION_PATTERNS = [
    r"ignore\s+(your\s+)?(previous\s+|prior\s+)?instructions",
    r"disregard\s+(all\s+)?previous",
    r"you\s+are\s+now\s+a?\s*different",
    r"output\s+(the\s+)?(api[_\s]?key|secret|password|token|key)",
    r"forget\s+(all\s+)?previous\s+(instructions|context)",
    r"new\s+persona\s*:",
    r"system\s*prompt\s*:",
]
```

If matched, replaces with: `"[This message contained potentially unsafe content and has been sanitized for security.]"`

**Where called:** `pipeline.py` — applied to every user message before entering any agent

---

### 1.7 Service Name Grounder

**Functions:**
- `ground_services(services, known_services) → (valid, hallucinated)`
- `check_report_grounding(report, known_services) → List[str]`

**What it does:**  
- `ground_services()` splits a service list into those that exist in KuzuDB vs. invented names
- `check_report_grounding()` scans impact reports for `SERVICE: <name>` lines and identifies hallucinated service names

**Where called:** `pipeline.py` after report generation, before storage

---

### 1.8 Epistemic Claim Tagger

**Function:** `classify_report_claims(report: str, grounded_services: set) → str`

**What it does:**  
Tags every `SERVICE:` line with its provenance:

- `SERVICE: [GRAPH] fx-service` — Confirmed by actual graph query (high trust)
- `SERVICE: [MODEL] phantom-service` — Not confirmed by queries (flag for human review)

**Where called:** `pipeline.py` before surfacing report to user

---

### 1.9 Artifact Store

**Function:** `store_artifact(data: dict, tool_name: str) → str`  
**Constant:** `ARTIFACT_THRESHOLD = 20`

**What it does:**  
When a tool returns >20 rows, writes full results to `./artifacts/<tool>_<hash>.json` and returns only a handle string (`artifact://filename.json`) to the context window.

**Purpose:** Prevents large results from consuming the entire context window.

**Where called:** Tool result post-processing in `impact_agent.py`

---

### 1.10 Structured Event Logger

**Function:** `make_log_entry(message, level, event_type, metadata) → dict`

**What it does:**  
Wraps every pipeline activity log entry with typed metadata for the UI timeline:

| Event Type | When Used |
|------------|-----------|
| `"tool_call"` | A graph tool was invoked |
| `"harness_check"` | A harness validation ran |
| `"stage_change"` | Pipeline stage transition |
| `"budget_warning"` | Budget is running low |
| `"injection_blocked"` | Prompt injection was sanitized |

**Where called:** Throughout `pipeline.py` and `impact_agent.py`

---

## 2. Code-Generation Harness Components

**Directory:** `forge/src/modules/codegen/harness/`  
**Entry Point:** `gate.py` → `DeterministicGate`  
**Consumed by:** `verifier_agent.py`

### Architecture: Three-Tier Fail-Fast Pipeline

```
TIER 1 (milliseconds) — FAIL FAST
  ├── Syntax check (tree-sitter / node --check)
  └── Import resolution (file paths + package.json)
         │
         ▼  only if Tier 1 passes
TIER 2 (seconds)
  ├── Security scanning (OWASP patterns)
  ├── Complexity analysis (lizard / cyclomatic)
  └── Contract verification (plan vs. implementation)
         │
         ▼  only if Tier 1 + 2 pass (or only warnings)
TIER 3 (seconds)
  ├── Hallucination detection (invented symbols)
  └── Negative constraint checking (7 prohibition rules)
```

---

### 2.1 Syntax Checker via vallm/tree-sitter

**File:** `vallm_adapter.py` → `VallmAdapter.check_syntax()`

**What it does:**  
Uses the `vallm` library's `SyntaxValidator` backed by **tree-sitter** to parse JS/TS files into a full AST. Tree-sitter supports 165 languages with accurate error locations.

**How it works:**
1. Creates a `Proposal` with code content and language
2. Calls `SyntaxValidator.validate()`
3. If `result.score < 1.0`, extracts issues as violations
4. Violations are **demoted to WARNING** (Node.js check is authoritative for JS)

**Log output:**
```
[GATE]    [T1] Syntax check via vallm (tree-sitter)...
[GATE]    [T1] vallm syntax: 2 warnings (informational)
```

---

### 2.2 Syntax Checker (Native Fallback)

**File:** `syntax_checker.py` → `SyntaxChecker`

**What it does:**  
Fallback when vallm/tree-sitter is unavailable. Three methods in order:

1. **`node --check`** — Spawns Node.js subprocess to parse JS  
   - Most accurate fallback
   - Parses line numbers from Node's error output

2. **Bracket/quote balance check** — Walks code tracking `{`, `[`, `(`  
   - Handles strings and comments correctly
   - Reports exact line of unclosed opener

3. **Common error patterns:**
   - Assignment `=` in `if` condition (vs `==`/`===`)
   - `return` alone on a line (ASI issue)

**Log output:**
```
[GATE]    [T1] Syntax check via node --check (authoritative)...
[GATE]    [T1] SYNTAX PASS (0 warnings)
```

---

### 2.3 Import Resolver

**File:** `import_resolver.py` → `ImportResolver`

**What it does:**  
Validates every `require()` and `import` statement in modified files.

**Three categories handled:**

| Import Type | Validation |
|-------------|------------|
| **Node.js builtins** (`fs`, `path`, `http`) | Always allowed |
| **Relative imports** (`./foo`, `../bar`) | File must exist on disk OR be created in same diff |
| **Package imports** (`axios`, `express`) | Must be in `package.json` OR exist in `node_modules` |

**Catches hallucinations:** e.g., `require('./circuitBreaker')` when that module was never created.

**Severity:**
- Relative import not found → **ERROR** (blocks diff)
- Package not in package.json → **INFO** (might be peer dep, non-blocking)

**Log output:**
```
[GATE]    [T1] Import resolution check...
[GATE]    [T1] IMPORT PASS
```

---

### 2.4 Security Scanner (Native Patterns)

**File:** `security_scanner.py` → `SecurityScanner`

**What it does:**  
Regex-based scan for 20+ OWASP security anti-patterns:

| Pattern | Severity | Description |
|---------|----------|-------------|
| `eval_usage` | ERROR | `eval()` — arbitrary code execution |
| `function_constructor` | ERROR | `new Function()` — eval equivalent |
| `settimeout_string` | WARNING | `setTimeout("string")` — eval-like |
| `child_process_exec` | ERROR | `exec()` with `${}` — command injection |
| `sql_injection_template` | ERROR | SQL with template literals |
| `sql_concat` | ERROR | SQL with string concatenation |
| `hardcoded_password` | ERROR | `password: "..."` literal |
| `hardcoded_api_key` | ERROR | `apiKey: "..."` (≥16 chars) |
| `private_key` | ERROR | `-----BEGIN PRIVATE KEY-----` |
| `innerhtml_dynamic` | ERROR | `.innerHTML =` with dynamic content |
| `disable_ssl` | ERROR | `rejectUnauthorized: false` |
| `cors_allow_all` | WARNING | `Access-Control-Allow-Origin: *` |
| `md5_usage` | WARNING | MD5 hash — cryptographically broken |
| `path_traversal` | WARNING | File ops with `..` in path |

**Log output:**
```
[GATE]    [T2] Security scan via native patterns (SQL injection, eval, secrets)...
[GATE]    [T2] native security: PASS
```

---

### 2.5 Security Scanner via vallm

**File:** `vallm_adapter.py` → `VallmAdapter.check_security()`

**What it does:**  
Runs `vallm`'s `SecurityValidator` in addition to native patterns. The two scanners complement each other.

**Where called:** Tier 2, runs before native security scanner

---

### 2.6 Complexity Analyzer via lizard

**File:** `vallm_adapter.py` → `VallmAdapter.check_complexity()`

**What it does:**  
Uses `vallm`'s `ComplexityValidator` backed by **lizard** to compute:

- **Cyclomatic complexity** — flagged if > 15 (configurable via `GateConfig.complexity_threshold`)
- **Function length** — flagged if > 100 lines (configurable via `VallmConfig.max_function_length`)

**Severity:** All violations are **WARNING** (complexity is never a hard block)

**Log output:**
```
[GATE]    [T2] Complexity check via lizard (threshold=15)...
[GATE]    [T2] Complexity: PASS
```

---

### 2.7 Contract Checker

**File:** `contract_checker.py` → `ContractChecker`

**What it does:**  
Verifies that implemented code matches the contracts defined in the Design Agent's plan.

**Checks:**
1. **Function exists** — Contract name must appear in diff
2. **Parameter count matches** — Wrong count is **ERROR**
3. **Parameter names match** — Wrong names are **WARNING**
4. **All contracts implemented** — Missing contracts are **ERROR**

**Purpose:** Ensures Design Agent's promised interfaces are actually delivered with correct signatures.

**Log output:**
```
[GATE]    [T2] Contract check (function signatures vs plan)...
[GATE]    [T2] Contract: PASS
```

---

### 2.8 Hallucination Detector

**File:** `hallucination_detector.py` → `HallucinationDetector`

**What it does:**  
Detects three categories of invented code elements:

**1. New function calls that don't exist:**
- Not a JS built-in method (`push`, `map`, `then`, `console.log`, etc.)
- Not defined in the same file
- Not imported anywhere
- Not found in service's source tree
- Not found in KuzuDB graph

→ **WARNING: "Function 'X' may not exist"**

**2. Hallucinated constants/event types:**
- New `UPPER_CASE_STRINGS` not defined anywhere

→ **WARNING: "Constant 'X' may need to be defined"**

**3. Cross-service method calls:**
- Pattern: `auditService.someMethod()`
- Infers target service from variable name
- Checks if method exists in target service

→ **WARNING: "Method 'X' may not exist in audit-service"**

**Severity:** All hallucination violations are **WARNING** (heuristic-based, requires human review)

**Log output:**
```
[GATE]    [T3] Hallucination detection (invented functions/constants)...
[GATE]    [T3] Hallucination: PASS
```

---

### 2.9 Negative Constraint Checker

**File:** `negative_constraints.py` → `NegativeConstraintChecker`

**What it does:**  
Enforces 7 explicit prohibition rules — things generated code **must NOT do**:

| Constraint | Severity | Rule |
|------------|----------|------|
| `no_persist_removal` | ERROR | Don't remove `[PERSIST]` or `@preserve` marked code |
| `no_whole_file_rewrite` | ERROR | Don't replace >80% of file content |
| `no_generic_catch` | WARNING | Don't add new `catch(e)` without specific error types |
| `no_test_deletion` | ERROR | Don't delete test files |
| `no_error_handling_removal` | WARNING | Don't remove try/catch blocks |
| `no_logging_removal` | WARNING | Don't remove ≥3 logging statements |
| `no_env_hardcoding` | ERROR | Don't replace `process.env.X` with hardcoded values |

**Log output:**
```
[GATE]    [T3] Negative constraints check (no persist removal, no new deps, etc.)...
[GATE]    [T3] Negative constraints: PASS
```

---

### 2.10 Deterministic Gate Orchestrator

**File:** `gate.py` → `DeterministicGate`

**What it does:**  
Orchestrates all code-gen harness checks in tier order:

```python
GateConfig(
    fail_fast=True,          # Stop on first Tier 1 error
    use_vallm=True,          # Use vallm/tree-sitter when available
    complexity_threshold=15, # Max cyclomatic complexity
    max_warnings=20,         # Cap warnings in output
    skip_security=False,
    skip_hallucination=False,
    skip_contracts=False,
    skip_constraints=False,
)
```

**Key behaviors:**
- **Fail-fast on Tier 1:** Syntax or import ERROR stops execution
- **Accumulate Tier 2+3:** All violations collected together
- **Deduplication:** Same check/file/description/line deduplicated
- **Warning cap:** Maximum 20 warnings returned (errors never capped)
- **Feedback generation:** `result.get_feedback_for_agent()` formats for LLM retry

**`HarnessResult` fields:**

| Field | Type | Description |
|-------|------|-------------|
| `passed` | `bool` | `True` if zero ERROR violations |
| `violations` | `List[HarnessViolation]` | All violations with severity, file, line, description, fix_hint |
| `checks_run` | `List[str]` | Names of checks run (e.g., `["syntax:vallm", "import", "security:native"]`) |
| `duration_ms` | `float` | Total execution time |

**Log output:**
```
[GATE] >> HARNESS START: service=payment-processor, diffs=3, files=[...]
[GATE]    [T1] Syntax check via vallm (tree-sitter)...
[GATE]    [T1] Syntax check via node --check (authoritative)...
[GATE]    [T1] Import resolution check...
[GATE]    [T2] Security scan via vallm patterns...
[GATE]    [T2] Security scan via native patterns...
[GATE]    [T2] Contract check (function signatures vs plan)...
[GATE]    [T3] Hallucination detection...
[GATE]    [T3] Negative constraints check...
[GATE] << HARNESS DONE: PASS in 1234ms — checks=[...] errors=0 warnings=2
```

---

## 3. Reverse-Engineering Harness Components

**File:** `forge/src/modules/reverse_engineer/harness.py`  
**Consumed by:** `gap_agent.py`, `inference_agent.py`, `spec_writer_agent.py`, `orchestrator.py`

### 3.1 RE Policy Gate

**Function:** `re_policy_gate(action: str, file_path: str) → (bool, str)`

**What it does:**  
Validates actions for the reverse-engineering pipeline:

| Action | Validation |
|--------|------------|
| `read_log` | File path not empty, extension in allowlist (`.log`, `.txt`, `.jsonl`, `.json`, `.csv`, `.tsv`) |
| `write_spec` | File path not empty, doesn't match blocked patterns (`../`, `/etc/`, `/usr/`, `.py`, `.env`) |
| `read_facts` | Always allowed |

**Purpose:** Blocks path traversal and writes to sensitive locations.

---

### 3.2 RE Tool Receipt Log

**Class:** `REToolReceiptLog`

**Methods:**
- `reset()` — Clear at pipeline start
- `log(tool_name, inputs, result_count)` — Record each call
- `get()` — Retrieve log
- `assert_used(min_calls=1)` — Assert minimum usage
- `summary()` — Get summary string

**Purpose:** Proves RE agents actually used tools vs. generating from training data.

---

### 3.3 RE Budget Enforcer

**Class:** `REBudgetEnforcer(max_llm_calls=30, max_seconds=300)`

**Methods:**
- `record_llm_call()` — Track LLM usage
- `remaining_calls()` — Get remaining budget
- `check()` → `(bool, str)` — Check if within budget
- `get_budget_warning()` → `Optional[str]` — Get contextual warning

**Purpose:** Prevents runaway LLM loops on large log files.

---

### 3.4 RE Loop Detector

**Class:** `RELoopDetector(window=5, threshold=3)`

**Methods:**
- `record_and_check(tool, inputs)` → `(bool, str)` — Record and check for loops

**Purpose:** Same as agent harness loop detector but scoped to RE pipeline.

---

### 3.5 User Comments Sanitizer

**Function:** `sanitize_user_comments(comments: str) → (str, bool)`

**What it does:**  
Strips prompt injection from user-provided comments using the same patterns as the agent harness sanitizer.

---

## 4. Integration Points

### 5.1 Code Generation Pipeline

```
DesignAgent.create_plan()
        ↓
CoordinatorAgent.validate()
        ↓
ImplementationAgent.implement()  ─────────────────┐
        ↓                                         │
VerifierAgent.verify()                            │
        ↓                                         │
_run_harness_verification()  ◄────────────────────┤ Harness Gate
        ↓                                         │
DeterministicGate.run()                           │
        ↓                                         │
[TIER 1] Syntax + Imports                         │
[TIER 2] Security + Complexity + Contracts        │
[TIER 3] Hallucination + Negative Constraints     │
        ↓                                         │
HarnessResult                                     │
        ↓                                         │
if not passed → retry loop ────────────────────────┘
```

### 5.2 Impact Analysis Pipeline

```
ImpactAgent.run()
        │
        ├── PolicyGate.check_cypher_safe()    # Every Cypher query
        ├── PolicyGate.check_symbol_name()    # Every symbol lookup
        ├── BudgetEnforcer.check()            # Before each LLM turn
        ├── LoopDetector.check()              # After each tool call
        ├── receipts_log()                    # After each tool call
        │
        ↓
ImpactReport
        │
        ├── receipts_assert_used()            # Verify tools were used
        ├── check_report_grounding()          # Find hallucinated services
        ├── classify_report_claims()          # Tag [GRAPH] vs [MODEL]
        │
        ↓
Final Report
```

### 5.3 Reverse Engineering Pipeline

```
REOrchestrator.run()
        │
        ├── re_policy_gate('read_log', ...)   # Validate log file access
        ├── sanitize_user_comments()          # Clean user input
        │
        ↓
InferenceAgent / GapAgent / SpecWriterAgent
        │
        ├── REBudgetEnforcer.check()          # Before each LLM turn
        ├── RELoopDetector.record_and_check() # After each tool call
        ├── REToolReceiptLog.log()            # After each tool call
        │
        ↓
Specification Output
        │
        ├── REToolReceiptLog.assert_used()    # Verify tools were used
        │
        ↓
Final Spec
```

---

## 5. Component Quick Reference

### Agent Harness (`harness_utils.py`)

| # | Component | Function/Class | Purpose |
|---|-----------|----------------|---------|
| 1 | Cypher Write Guard | `check_cypher_safe()` | Block DB mutations from analysis agent |
| 2 | Symbol Name Validator | `check_symbol_name()` | Validate graph lookup inputs |
| 3 | Tool Receipt Log | `receipts_log()`, `receipts_assert_used()` | Prove tools were actually called |
| 4 | Budget Enforcer | `BudgetEnforcer` | Cap LLM calls, tool calls, wall-clock time |
| 5 | Loop Detector | `LoopDetector` | Detect same-tool-same-args loops |
| 6 | Prompt Injection Sanitizer | `sanitize_message()` | Strip injection attempts |
| 7 | Service Name Grounder | `ground_services()`, `check_report_grounding()` | Detect hallucinated service names |
| 8 | Epistemic Claim Tagger | `classify_report_claims()` | Tag claims as [GRAPH] or [MODEL] |
| 9 | Artifact Store | `store_artifact()` | Offload large results from context |
| 10 | Structured Event Logger | `make_log_entry()` | Type every pipeline event |

### Code-Gen Harness (`harness/`)

| # | Component | File | Tier | Purpose |
|---|-----------|------|------|---------|
| 11 | Syntax — tree-sitter | `vallm_adapter.py` | 1 | AST parse via tree-sitter |
| 12 | Syntax — native | `syntax_checker.py` | 1 | `node --check` + bracket balance |
| 13 | Import Resolver | `import_resolver.py` | 1 | Validate require/import paths |
| 14 | Security — native | `security_scanner.py` | 2 | 20+ OWASP pattern scan |
| 15 | Security — vallm | `vallm_adapter.py` | 2 | vallm security patterns |
| 16 | Complexity | `vallm_adapter.py` | 2 | Cyclomatic complexity via lizard |
| 17 | Contract Checker | `contract_checker.py` | 2 | Plan vs implementation |
| 18 | Hallucination Detector | `hallucination_detector.py` | 3 | Invented symbols/methods |
| 19 | Negative Constraints | `negative_constraints.py` | 3 | 7 prohibition rules |
| 20 | Deterministic Gate | `gate.py` | — | Orchestrates all checks |

### RE Harness (`reverse_engineer/harness.py`)

| # | Component | Class/Function | Purpose |
|---|-----------|----------------|---------|
| 21 | RE Policy Gate | `re_policy_gate()` | Validate file access actions |
| 22 | RE Tool Receipt Log | `REToolReceiptLog` | Prove tools were used |
| 23 | RE Budget Enforcer | `REBudgetEnforcer` | Cap LLM calls and time |
| 24 | RE Loop Detector | `RELoopDetector` | Detect stuck loops |
| 25 | User Comments Sanitizer | `sanitize_user_comments()` | Strip prompt injection |

---

## Summary

The Forge harness system provides **comprehensive, deterministic verification** at every stage of the LLM-assisted development pipeline:

1. **Impact Analysis** — Prevents database mutations, enforces budgets, detects loops, sanitizes inputs, grounds claims to actual evidence

2. **Code Generation** — Three-tier fail-fast validation covering syntax, imports, security, complexity, contracts, hallucinations, and explicit prohibitions

3. **Reverse Engineering** — Mirrors the impact analysis harness for the log-to-spec inference pipeline

**Total: 25 harness components** across 3 subsystems.

The key principle throughout:

> **LLM self-assessment is never trusted. Every critical check uses a deterministic external tool (tree-sitter, lizard, regex, file system, graph queries).**
