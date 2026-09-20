# Forge Harness — Implementation Reference

**Status:** Current as of September 2026  
**Scope:** Every harness component that exists in the Forge codebase today,
what it does, and exactly where in the source it is implemented.

---

## Overview

The Forge harness is split into two subsystems with different responsibilities:

| Subsystem | File Location | Guards |
|---|---|---|
| **Agent Harness** | `src/modules/agents/harness_utils.py` | The impact-analysis and context-gathering pipeline |
| **Code-Gen Harness** | `src/modules/codegen/harness/` | The code-generation and diff-verification pipeline |

The key design principle across both:  
> **The LLM is stateless compute — it proposes. The harness is deterministic truth — it verifies.**

LLM self-assessment is never trusted. Every critical check uses a deterministic
external tool (tree-sitter, lizard, regex, file system, KuzuDB graph queries).

---

## Part 1 — Agent Harness (`harness_utils.py`)

**File:** `src/modules/agents/harness_utils.py`  
**Consumed by:** `src/modules/agents/impact_agent.py` (the analysis agent)

This harness wraps the agents that analyse the codebase and produce the impact
report. It contains 10 components.

---

### Component 1 — Cypher Write Guard (`PolicyGate`)

**Function:** `check_cypher_safe(query: str) → (bool, str)`

**What it does:**  
Intercepts every Cypher query the impact agent tries to run against the KuzuDB
code graph. Blocks any query that begins with a write keyword:
`CREATE`, `DELETE`, `MERGE`, `SET`, `REMOVE`, `DROP`, `DETACH`, `LOAD`.

The impact agent is allowed to *read* the graph (MATCH/RETURN) but must never
*mutate* it. If a write is attempted, the function returns `(False, error_message)`
where the error message is written for the model to act on — it explains what went
wrong and gives a correct example query.

**Where it is called:**  
Every call to `query_cypher` tool inside `impact_agent.py` passes the query
through this gate first.

**Example block:**
```
Input:  "CREATE (s:Symbol {name: 'newFn'})"
Output: (False, "Write operation 'CREATE' is not allowed on the code graph.
         Only read queries are permitted. Use MATCH/RETURN to query data.
         Example: MATCH (s:Symbol) WHERE s.name CONTAINS 'validate' RETURN s.name")
```

---

### Component 2 — Symbol Name Validator (`PolicyGate`)

**Function:** `check_symbol_name(name: str) → (bool, str)`

**What it does:**  
Validates the `symbol_name` argument before it is passed to graph lookup tools.
Checks three things:
1. Name is not empty
2. Name is not longer than 200 characters (likely a malformed/injected input)
3. Name does not contain forbidden characters: `;`, `--`, `/*`, `\n`, `\r`

If invalid, returns `(False, error_message)` with a concrete correction hint for
the model.

**Where it is called:**  
`search_symbols` and `get_symbol` tool wrappers inside `impact_agent.py`.

---

### Component 3 — Tool Receipt Log

**Functions:**  
`receipts_reset()`, `receipts_log(tool, input_preview, result_count)`,  
`receipts_get()`, `receipts_assert_used(min_calls=1)`

**What it does:**  
Records every actual tool call made by the impact agent — tool name, input
preview (truncated to 120 chars), result count, and timestamp. Stored in
thread-local storage so parallel pipeline runs don't interfere.

After the agent produces its impact report, `receipts_assert_used(min_calls)` is
called. If the agent produced a report with fewer than `min_calls` real graph
queries (i.e., it appears to have generated the report from training data rather
than actual codebase analysis), the assertion fails with an actionable error:

```
"ImpactAgent produced a report with only 0 graph tool call(s) (minimum required: 1).
 Tools called: none. This suggests the report was generated from training data
 rather than actual code graph queries. Re-run the analysis."
```

**Where it is called:**  
- `receipts_reset()` at the start of each `pipeline.analyze()` call
- `receipts_log()` after every successful tool invocation in `impact_agent.py`
- `receipts_assert_used()` in `pipeline.py` before the report is accepted

**Visible in logs as:**
```
[HARNESS] Tool receipts (7 calls): ['query_cypher', 'get_schema', 'search_symbols',
'search_symbols', 'query_cypher', 'analyze_impact', 'get_service_topology']
```

---

### Component 4 — Budget Enforcer

**Class:** `BudgetEnforcer(max_llm_calls=50, max_tool_calls=200, max_seconds=600)`

**Methods:**  
`record_llm_call()`, `record_tool_call()`, `check() → (bool, str)`,
`get_budget_message() → Optional[str]`

**What it does:**  
Caps the resources a single analysis run can consume:
- Maximum 50 LLM calls per run
- Maximum 200 tool calls per run
- Maximum 600 seconds wall-clock time

`check()` is called before each LLM turn. If any limit is exceeded, it returns
`(False, error_message)` telling the model to write the final report immediately.

`get_budget_message()` injects a contextual warning into the model's prompt:
- At 10 remaining turns: "Note: 10 turns remaining"
- At 5 remaining turns: "Note: 5 turns remaining. Finish current service, don't start new ones."
- At 2 remaining turns: "**BUDGET: Only 2 turns remaining. STOP all new analysis. Write the final report NOW.**"

**Where it is called:**  
`BudgetEnforcer` instance is created per-run in `impact_agent.py` and checked
before each agent iteration loop.

---

### Component 5 — Loop Detector

**Class:** `LoopDetector(window=5, threshold=3)`

**Methods:**  
`record(tool_name, inputs)`, `check() → (bool, str)`

**What it does:**  
Detects when an agent calls the same tool with the same arguments 3 or more
times within a sliding window of 5 calls. This pattern indicates the agent is
stuck — it's retrying the same query because it isn't reading the result.

`record()` is called before executing every tool (stores a hash of tool name +
serialised inputs).  
`check()` is called after recording. If a loop is detected, it returns
`(True, intervention_message)`:

```
"[HARNESS LOOP DETECTED] You have called 'search_symbols' with the same arguments
 3 times without new results. Stop repeating this call. Try a different tool,
 different input, or move on to the next service. If you have enough data, write
 the report."
```

This message is injected directly into the model's context as a correction.

**Where it is called:**  
Tool execution wrapper inside `impact_agent.py`, around every tool dispatch.

---

### Component 6 — Prompt Injection Sanitizer

**Function:** `sanitize_message(msg: str) → (str, bool)`

**What it does:**  
Scans user input for known prompt injection patterns before it is used as
agent input. Patterns checked (case-insensitive):

- `"ignore your previous instructions"`
- `"disregard all previous"`
- `"you are now a different agent"`
- `"output the api key / secret / password / token"`
- `"forget all previous instructions"`
- `"new persona:"`
- `"system prompt:"`

If any pattern is found, the entire message is replaced with:
```
"[This message contained potentially unsafe content and has been sanitized for security.]"
```

Returns `(sanitized_message, was_modified)`. `was_modified=True` triggers a
structured log entry with `event_type="injection_blocked"`.

**Where it is called:**  
`pipeline.py` — applied to every user message before it enters any agent
(gathering clarifications, approval responses, etc.).

---

### Component 7 — Service Name Grounder

**Functions:**  
`ground_services(services, known_services) → (valid, hallucinated)`,
`check_report_grounding(report, known_services) → List[str]`

**What it does:**  
`ground_services()` splits a list of service names into:
- `valid` — names that exist in the KuzuDB code graph
- `hallucinated` — names the LLM invented that are not in the codebase

`check_report_grounding()` scans the finished impact report text for every
`SERVICE: <name>` line and returns the list of names not present in the graph.

**Where it is called:**  
`pipeline.py` — after the impact agent produces its report, before the report
is stored. Any hallucinated services are flagged in the pipeline log and the
report confidence is downgraded.

---

### Component 8 — Epistemic Claim Tagger

**Function:** `classify_report_claims(report: str, grounded_services: set) → str`

**What it does:**  
Tags every `SERVICE:` line in the impact report with its epistemic source:

- `SERVICE: [GRAPH] fx-service` — confirmed by an actual graph query (high trust)
- `SERVICE: [MODEL] phantom-service` — not confirmed by any graph query (flag to human)

This is the provenance tagging visible in the impact report output shown in the UI.
It lets reviewers immediately see which dependency claims come from real code
analysis versus LLM inference.

**Where it is called:**  
`pipeline.py` — transforms the raw report text just before it is stored and
surfaced to the user.

**Visible in the impact report as:**
```
SERVICE: [GRAPH] fx-service      [conf: 90%  evidence: http_calls_graph]
SERVICE: [GRAPH] payment-processor [conf: 90%  evidence: http_calls_graph]
```

---

### Component 9 — Artifact Store

**Functions:**  
`store_artifact(data: dict, tool_name: str) → str`,  
constant: `ARTIFACT_THRESHOLD = 20`

**What it does:**  
When a tool returns more than 20 rows of results, the full result is written to
disk (`./artifacts/<tool>_<hash>.json`) and only a handle string
(`artifact://filename.json`) is placed on the model's context window.

This prevents large query results (e.g., a symbol search returning 200 matches)
from consuming the entire context window and crowding out the actual reasoning.

**Where it is called:**  
Tool result post-processing in `impact_agent.py` — any result with
`len(rows) > ARTIFACT_THRESHOLD` is offloaded before the result is returned
to the agent.

---

### Component 10 — Structured Event Logger

**Function:** `make_log_entry(message, level, event_type, metadata) → dict`

**What it does:**  
Wraps every pipeline activity log entry with a typed `event_type` and structured
`metadata` dict. Plain string log entries are not acceptable for the structured
activity log that powers the UI's timeline view.

Valid `event_type` values:
| Value | When used |
|---|---|
| `"tool_call"` | A graph tool was invoked |
| `"harness_check"` | A harness validation ran (pass or fail) |
| `"stage_change"` | Pipeline stage transition (e.g., GATHERING → ANALYZING) |
| `"budget_warning"` | Budget is running low |
| `"injection_blocked"` | Prompt injection was sanitized |

**Where it is called:**  
Throughout `pipeline.py` and `impact_agent.py` wherever events are appended
to `pipeline.activity_log`.

---

## Part 2 — Code-Gen Harness (`src/modules/codegen/harness/`)

**Entry point:** `src/modules/codegen/harness/gate.py` → `DeterministicGate`  
**Consumed by:** `src/modules/codegen/verifier_agent.py`

This harness verifies every diff produced by the implementation agents before
it can be approved. It runs checks in three fail-fast tiers.

### Tier Architecture

```
TIER 1 (milliseconds) — FAIL FAST
  Syntax check (tree-sitter / node --check)
  Import resolution (file paths + package.json)
         │
         ▼  only if Tier 1 passes
TIER 2 (seconds)
  Security scanning (OWASP patterns)
  Complexity analysis (lizard / cyclomatic)
  Contract verification (plan vs. implementation)
         │
         ▼  only if Tier 1 + 2 pass (or only warnings)
TIER 3 (seconds)
  Hallucination detection (invented symbols / cross-service methods)
  Negative constraint checking (7 explicit prohibition rules)
```

The gate is configured via `GateConfig`:

```python
GateConfig(
    fail_fast=True,          # Stop on first Tier 1 error
    use_vallm=True,          # Use vallm/tree-sitter when available
    complexity_threshold=15, # Max cyclomatic complexity
    max_warnings=20,         # Cap warnings in output
)
```

---

### Component 11 — Syntax Checker via vallm/tree-sitter

**Class:** `VallmAdapter` in `vallm_adapter.py`  
**Method:** `check_syntax(service_id, diffs) → CheckResult`

**What it does:**  
Uses the `vallm` library's `SyntaxValidator` which is backed by **tree-sitter**
to parse every JavaScript/TypeScript file in the diff set into a full AST.
Tree-sitter supports 165 languages and produces accurate parse error locations.

If tree-sitter finds parse errors, the diff is blocked at Tier 1 and the
orchestrator logs the error and triggers a retry.

**Where it is called:**  
`gate.py` → `DeterministicGate.run()` — first check in Tier 1.

**Visible in logs as:**
```
[VERIFICATION] └─ Harness checks run: syntax:vallm
[VERIFICATION] └─ Harness result: 1 errors, 0 warnings
[ORCHESTRATOR] └─ [error] fx-service/src/services/conversionService.js:
                   tree-sitter found 6 parse error(s) in javascript
[ORCHESTRATOR] 🔄 Starting retry iteration 2/3
```

---

### Component 12 — Syntax Checker (Native Fallback)

**Class:** `SyntaxChecker` in `syntax_checker.py`  
**Method:** `check(service_id, diffs) → CheckResult`

**What it does:**  
Used when `vallm`/tree-sitter is not installed. Falls back to three methods
in order:

1. **`node --check`** — spawns a Node.js subprocess to parse the JS. Most
   accurate fallback; parses line numbers from Node's error output.
2. **Bracket/quote balance check** — walks every character tracking `{`, `[`,
   `(` and their closing pairs, ignoring strings and comments. Catches
   unclosed brackets. Reports the exact line of the unclosed opener.
3. **Common error patterns** — detects: assignment `=` in `if` condition where
   `==`/`===` was intended; `return` on a line by itself (ASI issue where the
   return value is on the next line).

**Where it is called:**  
`gate.py` — used instead of `VallmAdapter.check_syntax()` when vallm is
unavailable. Registered as `"syntax:native"` in `checks_run`.

---

### Component 13 — Import Resolver

**Class:** `ImportResolver` in `import_resolver.py`  
**Method:** `check(service_id, diffs) → CheckResult`

**What it does:**  
Validates every `require()` and `import` statement in every modified JS/TS file.
Three categories of imports are handled:

1. **Node.js builtins** (`fs`, `path`, `http`, etc.) — always allowed, no check.
2. **Relative imports** (`./foo`, `../bar`) — the resolved file path must either
   exist on disk, or be created by another file in the same diff set (handles
   the case where a new module and its consumer are both in the same change).
3. **Package imports** (`axios`, `express`) — the package name must appear in
   the service's `package.json` `dependencies`/`devDependencies`, or the
   `node_modules` directory must exist on disk.

Catches the most common LLM hallucination: inventing a module name
(e.g., `require('./circuitBreaker')`) that was never created.

**Severity:**  
- Relative import not found → **ERROR** (blocks the diff)  
- Package not in package.json → **WARNING** (might be a peer dep)

**Where it is called:**  
`gate.py` → Tier 1, immediately after syntax check.

---

### Component 14 — Security Scanner (Native Patterns)

**Class:** `SecurityScanner` in `security_scanner.py`  
**Method:** `check(service_id, diffs) → CheckResult`

**What it does:**  
Regex-based scan of generated code for 20+ OWASP security anti-patterns.
Each pattern has a name, severity, description, and fix hint:

| Pattern | Severity | Description |
|---|---|---|
| `eval_usage` | ERROR | `eval()` — arbitrary code execution |
| `function_constructor` | ERROR | `new Function()` — equivalent to eval |
| `settimeout_string` | WARNING | `setTimeout("string")` — acts like eval |
| `setinterval_string` | WARNING | `setInterval("string")` — acts like eval |
| `child_process_exec` | ERROR | `exec()` with template literal — command injection |
| `shell_command` | WARNING | `exec()` with string concat — command injection |
| `sql_injection_template` | ERROR | SQL query with `${}` interpolation |
| `sql_concat` | ERROR | SQL with string `+` concatenation |
| `sql_concat_simple` | ERROR | SQL with `req.` params concatenated |
| `sql_string_interpolation` | ERROR | `query()` with template literal |
| `hardcoded_password` | ERROR | `password: "..."` literal |
| `hardcoded_api_key` | ERROR | `apiKey: "..."` (≥16 chars) |
| `hardcoded_token` | WARNING | `token: "..."` (≥20 chars) |
| `private_key` | ERROR | `-----BEGIN PRIVATE KEY-----` in source |
| `innerhtml_assignment` | WARNING | `.innerHTML =` |
| `innerhtml_dynamic` | ERROR | `.innerHTML =` with dynamic content |
| `document_write` | WARNING | `document.write()` |
| `md5_usage` | WARNING | MD5 hash — cryptographically broken |
| `sha1_usage` | WARNING | SHA-1 — deprecated |
| `cors_allow_all` | WARNING | `Access-Control-Allow-Origin: *` |
| `disable_ssl` | ERROR | `rejectUnauthorized: false` |
| `path_traversal` | WARNING | `readFile()` with `..` in path |

**Where it is called:**  
`gate.py` → Tier 2, registered as `"security:native"`.

---

### Component 15 — Security Scanner via vallm

**Class:** `VallmAdapter` in `vallm_adapter.py`  
**Method:** `check_security(service_id, diffs) → CheckResult`

**What it does:**  
Runs `vallm`'s own `SecurityValidator` on each diff, in addition to Component 14.
The two scanners complement each other — `vallm` uses its own curated pattern
library, while Component 14 covers JS-specific patterns (SQL injection in JS,
Node.js command injection, etc.) that `vallm` may not cover.

**Where it is called:**  
`gate.py` → Tier 2, registered as `"security:vallm"`. Runs before native security
scanner so both result sets are accumulated.

---

### Component 16 — Complexity Analyser via lizard

**Class:** `VallmAdapter` in `vallm_adapter.py`  
**Method:** `check_complexity(service_id, diffs) → CheckResult`

**What it does:**  
Uses `vallm`'s `ComplexityValidator` backed by **lizard** to compute per-function
metrics for every modified file:
- **Cyclomatic complexity** — flagged if > 15 (default threshold, configurable)
- **Function length** — flagged if > 100 lines

All violations are **WARNING** severity (complexity is never a hard block, only
a code quality signal).

**Where it is called:**  
`gate.py` → Tier 2, registered as `"complexity:vallm"`.

---

### Component 17 — Contract Checker

**Class:** `ContractChecker` in `contract_checker.py`  
**Method:** `check(service_id, diffs, plan) → CheckResult`

**What it does:**  
The Design Agent's plan includes a `contracts` list — function signatures
that the implementation agents are required to produce. This checker verifies:

1. **Function exists** — if a contract names `getFxRateWithBreaker(baseCurrency, targetCurrency)`,
   that exact function must appear in the diff.
2. **Parameter count matches** — wrong number of params is an **ERROR**.
3. **Parameter names match** — wrong parameter names are a **WARNING**.

If a contracted function is entirely missing from all diffs, the checker
flags **ERROR: Contract '<name>' not implemented**.

The purpose is to ensure that when the Design Agent promises an interface
(e.g., "the circuit breaker module will export `getFxRateWithBreaker`"), the
Implementation Agent actually delivers it with that exact signature so that
dependent tasks can import it correctly.

**Where it is called:**  
`gate.py` → Tier 2, only if `plan` is provided. Registered as `"contract"`.

---

### Component 18 — Hallucination Detector

**Class:** `HallucinationDetector` in `hallucination_detector.py`  
**Method:** `check(service_id, diffs) → CheckResult`

**What it does:**  
Detects three categories of invented/hallucinated code elements:

**1. New function calls that don't exist:**  
Compares function calls in the new content vs the original. For each *new* call:
- Not a JS built-in method (`push`, `map`, `then`, `console.log`, etc.)
- Not defined in the same file
- Not imported anywhere in the file
- Not found in the service's source tree (file scan)
- Not found in KuzuDB graph (if connected)

→ **WARNING: "Function 'X' may not exist — verify it's defined"**

**2. Hallucinated constants/event types:**  
Finds new `UPPER_CASE_STRINGS` (likely event type constants or enum values)
that don't appear in the original content. If the constant isn't defined
anywhere in the file, warns that it may need to be defined in a constants file.

**3. Cross-service method calls:**  
Pattern: `auditService.someMethod()` or `paymentClient.createTransaction()`.
Infers the target service from the variable name (camelCase → kebab-case + "-service"),
then checks whether `someMethod` exists in that service's source tree or graph.
→ **WARNING: "Method 'X' may not exist in audit-service"**

All hallucination violations are **WARNING** (not ERROR) because the detector
uses heuristics — it cannot be 100% certain. Human review is expected for warnings.

**Where it is called:**  
`gate.py` → Tier 3, registered as `"hallucination"`.

---

### Component 19 — Negative Constraint: No Persist Removal

**Class:** `NegativeConstraintChecker` in `negative_constraints.py`  
**Method:** `_check_persist_removal()`

**What it does:**  
Scans the original file content for sections marked with persistence annotations:
- `// [PERSIST]` / `// [/PERSIST]` blocks
- `/* @preserve */` blocks
- `// @preserve` lines
- `// DO NOT MODIFY` lines

If any such section exists in the original but is absent in the modified content,
the diff is **BLOCKED (ERROR)**.

**Purpose:** Prevents the implementation LLM from deleting manually-authored
code that must survive automated changes (configuration, legal notices,
hand-tuned algorithms).

---

### Component 20 — Negative Constraint: No Whole-File Rewrite

**Class:** `NegativeConstraintChecker` in `negative_constraints.py`  
**Method:** `_check_whole_file_rewrite()`

**What it does:**  
Computes the line-level preservation ratio between old and new content:

```
preserved_lines = set(old_lines) ∩ set(new_lines)
ratio = len(preserved_lines) / len(old_lines)
```

If `ratio < 0.20` (less than 20% of original lines preserved) and the file
had more than 10 lines, it's flagged as an **ERROR: Whole-file rewrite detected**.

Only applies to *modified* files (not new files — `diff.is_new_file` is checked).

**Purpose:** Prevents the LLM from replacing the entire content of a file when
only a small targeted change was requested. Whole-file rewrites erase context,
break blame history, and often introduce regressions.

---

### Component 21 — Negative Constraint: No Generic Catch

**Class:** `NegativeConstraintChecker` in `negative_constraints.py`  
**Method:** `_check_generic_catch()`

**What it does:**  
Counts `catch(e) {}`, `catch(err) {}`, `catch(error) {}`, `catch(ex) {}` blocks
in old vs new content. If the new content has *more* generic catches than the
original, a **WARNING** is raised for each new one.

**Severity:** WARNING (not a hard block — generic catches are sometimes intentional
for top-level error boundaries).

**Purpose:** Encourages specific error handling (`catch(e) { if (e instanceof NetworkError)...`)
over silent swallowing of all error types.

---

### Component 22 — Negative Constraint: No Test Deletion

**Class:** `NegativeConstraintChecker` in `negative_constraints.py`  
**Method:** `_check_test_deletion()`

**What it does:**  
If the modified file path contains `test`, `spec`, `__tests__`, `.test.`, or `.spec.`
(case-insensitive), and the new content is empty, the diff is **BLOCKED (ERROR)**.

**Purpose:** Prevents the LLM from silently deleting test files when it decides
they "aren't needed" for the change.

---

### Component 23 — Negative Constraint: No Error Handling Removal

**Class:** `NegativeConstraintChecker` in `negative_constraints.py`  
**Method:** `_check_error_handling_removal()`

**What it does:**  
Counts `try {` blocks in old and new content. If the count decreases, a
**WARNING** is raised identifying how many try/catch blocks were removed.

**Severity:** WARNING (sometimes error handling is legitimately restructured).

**Purpose:** Ensures the LLM doesn't silently remove error handling while
simplifying code, leaving callers without error propagation.

---

### Component 24 — Negative Constraint: No Logging Removal

**Class:** `NegativeConstraintChecker` in `negative_constraints.py`  
**Method:** `_check_logging_removal()`

**What it does:**  
Counts `console.log()`, `logger.info()`, `logger.error()`, etc. (pattern:
`(?:console|logger|log)\s*\.\s*(?:log|info|warn|error|debug)\s*\(`) in old and
new content. If 3 or more logging statements were removed, a **WARNING** is raised.

**Severity:** WARNING (logging is sometimes intentionally cleaned up).

**Purpose:** Maintains observability. LLMs have a tendency to remove "noisy"
log statements when refactoring, which reduces production visibility.

---

### Component 25 — Negative Constraint: No Env Var Hardcoding

**Class:** `NegativeConstraintChecker` in `negative_constraints.py`  
**Method:** `_check_env_hardcoding()`

**What it does:**  
Finds all `process.env.VAR_NAME` usages in the old content. For each one that
disappears in the new content, checks whether a literal `'VAR_NAME'` or
`"VAR_NAME"` string appears elsewhere in the new content (which would suggest
it was replaced with a hardcoded value). If so, an **ERROR** is raised.

**Purpose:** Prevents the LLM from replacing environment variable references
with hardcoded values (e.g., replacing `process.env.DB_HOST` with `'localhost'`),
which would break production deployments.

---

### Component 26 — Deterministic Gate Orchestrator

**Class:** `DeterministicGate` in `gate.py`  
**Method:** `run(service_id, diffs, plan) → HarnessResult`

**What it does:**  
Orchestrates all 15 code-gen harness checks (Components 11–25) in the correct
tier order. Key behaviours:

- **Fail-fast on Tier 1 errors:** If syntax or import checks produce any ERROR
  violations, execution stops and returns immediately without running Tier 2 or 3.
- **Accumulate Tier 2 and 3 violations:** All warnings and errors from later
  tiers are collected and returned together.
- **Deduplication:** Identical violations (same check, file, description, line)
  are deduplicated.
- **Warning cap:** At most 20 warnings are returned (errors are never capped).
- **Feedback generation:** `result.get_feedback_for_agent()` formats all ERROR
  violations into a structured, actionable prompt for the LLM to self-correct
  before the next retry.

**`HarnessResult` fields:**

| Field | Type | Description |
|---|---|---|
| `passed` | `bool` | `True` if zero ERROR violations |
| `violations` | `List[HarnessViolation]` | All violations with severity, file, line, description, fix_hint |
| `checks_run` | `List[str]` | Names of all checks that ran (e.g., `["syntax:vallm", "import", "security:native"]`) |
| `duration_ms` | `float` | Total harness execution time |

**Where it is called:**  
`src/modules/codegen/verifier_agent.py` → `_run_harness_verification(service_id, diffs, plan)`

**Visible in logs as:**
```
[VERIFICATION] └─ Running harness verification...
[VERIFICATION] └─ Harness checks run: syntax:vallm
[VERIFICATION] └─ Harness result: 1 errors, 0 warnings
[VERIFICATION] └─ Harness FAILED: 1 errors, 0 warnings
[ORCHESTRATOR] └─ [error] fx-service/src/services/conversionService.js:
                   tree-sitter found 6 parse error(s) in javascript
[ORCHESTRATOR] 🔄 Starting retry iteration 2/3
```

---

## Complete Component Index

### Agent Harness (`harness_utils.py`)

| # | Component | Function/Class | Purpose |
|---|---|---|---|
| 1 | Cypher Write Guard | `check_cypher_safe()` | Block DB mutations from analysis agent |
| 2 | Symbol Name Validator | `check_symbol_name()` | Validate graph lookup inputs |
| 3 | Tool Receipt Log | `receipts_log()`, `receipts_assert_used()` | Prove tools were actually called |
| 4 | Budget Enforcer | `BudgetEnforcer` | Cap LLM calls, tool calls, wall-clock time |
| 5 | Loop Detector | `LoopDetector` | Detect same-tool-same-args loops |
| 6 | Prompt Injection Sanitizer | `sanitize_message()` | Strip injection attempts from user input |
| 7 | Service Name Grounder | `ground_services()`, `check_report_grounding()` | Detect hallucinated service names |
| 8 | Epistemic Claim Tagger | `classify_report_claims()` | Tag report claims as [GRAPH] or [MODEL] |
| 9 | Artifact Store | `store_artifact()` | Offload large results from context window |
| 10 | Structured Event Logger | `make_log_entry()` | Type every pipeline event |

### Code-Gen Harness (`src/modules/codegen/harness/`)

| # | Component | Class/File | Tier | Purpose |
|---|---|---|---|---|
| 11 | Syntax — tree-sitter | `VallmAdapter.check_syntax()` / `vallm_adapter.py` | 1 | AST parse via tree-sitter |
| 12 | Syntax — native fallback | `SyntaxChecker` / `syntax_checker.py` | 1 | `node --check` + bracket balance |
| 13 | Import Resolver | `ImportResolver` / `import_resolver.py` | 1 | Validate require/import paths |
| 14 | Security — native patterns | `SecurityScanner` / `security_scanner.py` | 2 | 20+ OWASP pattern scan |
| 15 | Security — vallm | `VallmAdapter.check_security()` / `vallm_adapter.py` | 2 | vallm security patterns |
| 16 | Complexity — lizard | `VallmAdapter.check_complexity()` / `vallm_adapter.py` | 2 | Cyclomatic complexity + function length |
| 17 | Contract Checker | `ContractChecker` / `contract_checker.py` | 2 | Verify plan contracts are implemented |
| 18 | Hallucination Detector | `HallucinationDetector` / `hallucination_detector.py` | 3 | Detect invented symbols + cross-service methods |
| 19 | NC: No Persist Removal | `NegativeConstraintChecker` / `negative_constraints.py` | 3 | Block removal of @preserve code |
| 20 | NC: No Whole-File Rewrite | `NegativeConstraintChecker` / `negative_constraints.py` | 3 | Block >80% content replacement |
| 21 | NC: No Generic Catch | `NegativeConstraintChecker` / `negative_constraints.py` | 3 | Warn on new bare catch(e) blocks |
| 22 | NC: No Test Deletion | `NegativeConstraintChecker` / `negative_constraints.py` | 3 | Block deletion of test files |
| 23 | NC: No Error Handling Removal | `NegativeConstraintChecker` / `negative_constraints.py` | 3 | Warn on removed try/catch |
| 24 | NC: No Logging Removal | `NegativeConstraintChecker` / `negative_constraints.py` | 3 | Warn on bulk logging removal |
| 25 | NC: No Env Hardcoding | `NegativeConstraintChecker` / `negative_constraints.py` | 3 | Block replacement of process.env |
| 26 | Deterministic Gate | `DeterministicGate` / `gate.py` | — | Orchestrates all checks, produces HarnessResult |

**Total: 26 harness components across 2 subsystems.**

---

## Data Models (`models.py`)

All harness results use these shared types:

```python
class ViolationSeverity(Enum):
    ERROR   = "error"    # Hard failure — blocks the diff, triggers retry
    WARNING = "warning"  # Should review — surfaces to human but doesn't block
    INFO    = "info"     # Informational — no action needed

class CheckType(Enum):
    SYNTAX              = "syntax"
    IMPORT              = "import"
    HALLUCINATION       = "hallucination"
    SECURITY            = "security"
    CONTRACT            = "contract"
    NEGATIVE_CONSTRAINT = "negative_constraint"
```

A `HarnessViolation` always carries:
- `severity` — ERROR / WARNING / INFO
- `check` — which CheckType produced it
- `service_id` — which service the diff belongs to
- `file_path` — which file has the violation
- `description` — human-readable problem statement
- `fix_hint` — actionable correction for both humans and the LLM retry
- `line_number` — where possible, the exact line

---

## How a Failed Diff Gets Corrected (Retry Flow)

When the harness fails:

```
IMPLEMENTING
    ↓
DeterministicGate.run(diffs, plan)
    ↓ (1+ ERROR violations)
HarnessResult.passed = False
    ↓
orchestrator: "Starting retry iteration N/3"
    ↓
HarnessResult.get_feedback_for_agent() → structured error message
    ↓
Implementation LLM receives:
  "Harness verification FAILED: 1 errors, 0 warnings

   ERROR [syntax] fx-service/src/services/conversionService.js
     Issue: tree-sitter found 6 parse error(s) in javascript
     Fix: Fix the syntax error to proceed
     Location: line 23"
    ↓
Implementation LLM generates corrected diff
    ↓
DeterministicGate.run() again
    ↓ (no ERROR violations)
HarnessResult.passed = True
    ↓
AWAITING_APPROVAL (diff surfaced to human)
```

Maximum 3 iterations (configurable). If all 3 fail, the pipeline surfaces
the best available diff with the harness errors still attached for human review.
