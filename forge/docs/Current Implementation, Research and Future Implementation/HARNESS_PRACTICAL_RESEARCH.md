# Harness Engineering — Practical Research
## GitHub Repos + Medium Articles + Blogs + All Sources

**Date:** September 2026  
**Scope:** All non-arXiv sources — GitHub, Medium, DataCamp, blogs, production case studies  
**Covers:** Validation, tool use, memory, state persistence, observability, evals, context management

---

## The Single Most Important Finding

**From "The Definitive Guide to Agent Harness Engineering" (Medium, April 2026):**

> "A basic scaffold achieves 23% on SWE-bench. An optimized 250-turn scaffold
> running the SAME model achieves 45%+. That is a 22-point swing."

> "LangChain moved from Top 30 to Top 5 (52.8% to 66.5%) on Terminal Bench
> WITHOUT CHANGING THE MODEL ONCE. Every point came from harness improvements."

> "Vercel collapsed 15+ tools to 1 bash tool:  
>   274 seconds → 77 seconds  
>   80% success → 100% success  
>   37% fewer tokens"

**The model is a commodity. The harness is the moat.**

---

## Part 1: GitHub Repos — Practically Implemented

### GROUP A — Minimal Complete Harness Implementations

---

#### 1. `anthony-maio/agent-harness-90m` — ⭐ GOLD — Minimal Reference Implementation

**What it is:** A complete minimal Python agent harness in 90 minutes. The clearest
reference implementation found.

**Structure:**
```
agent-harness-90m/
  agent.py              # CLI entry point
  harness.yaml          # Config: model, tools, policy, budget
  harness/
    runner.py           # Main agent ReAct loop
    task.py             # Task file parser
    tools.py            # Tool registry and execution
    policy.py           # Policy gate (THE ACTION BOUNDARY)
    budget.py           # Budget enforcement
    logger.py           # Structured JSONL logging
    memory.py           # File-based memory
    report.py           # Post-run report generation
  policies/
    default.yaml        # Policy rules
  logs/                 # JSONL logs
  reports/              # Run reports
```

**The full loop (directly applicable to Forge):**

```python
# From runner.py — the core pattern
task.md -> runner -> LLM -> tool calls -> policy gate -> executor -> log
                     ^                        |
                     |                        v
                  memory <--------------- evaluator
```

**Policy gate (the action boundary in code):**

```python
# policy.py — this is exactly what Forge needs for query_cypher
class PolicyGate:
    def __init__(self, policy_config):
        self.blocked_tools = policy_config.get("blocked_tools", [])
        self.workspace_boundary = policy_config.get("workspace_boundary")
        self.risk_levels = policy_config.get("risk_levels", {})
    
    def check(self, tool_name: str, tool_input: dict) -> tuple[bool, str]:
        """Returns (allowed, reason). Reason is model-readable on deny."""
        
        # Blocked tools — absolute deny
        if tool_name in self.blocked_tools:
            return False, f"Tool '{tool_name}' is blocked by policy."
        
        # Path escape check for file tools
        if tool_name in ("write_file", "read_file") and self.workspace_boundary:
            path = tool_input.get("path", "")
            if not path.startswith(self.workspace_boundary):
                return False, (
                    f"Path '{path}' escapes the workspace boundary '{self.workspace_boundary}'. "
                    f"Use a path inside {self.workspace_boundary}."
                )
        
        # Risk-based approval
        risk = self.risk_levels.get(tool_name, "low")
        if risk == "destructive":
            return False, f"Tool '{tool_name}' is classified destructive and requires human approval."
        
        return True, ""
```

**Budget enforcement:**

```python
# budget.py — kills the run if limits hit
class BudgetEnforcer:
    def __init__(self, max_llm_calls=50, max_tool_calls=100, max_seconds=300):
        self.max_llm_calls = max_llm_calls
        self.max_tool_calls = max_tool_calls
        self.max_seconds = max_seconds
        self.llm_calls = 0
        self.tool_calls = 0
        self.start_time = time.time()
    
    def check(self) -> tuple[bool, str]:
        if self.llm_calls >= self.max_llm_calls:
            return False, f"LLM call budget exhausted ({self.max_llm_calls} calls)"
        if self.tool_calls >= self.max_tool_calls:
            return False, f"Tool call budget exhausted ({self.max_tool_calls} calls)"
        elapsed = time.time() - self.start_time
        if elapsed >= self.max_seconds:
            return False, f"Time budget exhausted ({self.max_seconds}s)"
        return True, ""
```

**GitHub:** `github.com/anthony-maio/agent-harness-90m`

---

#### 2. `LanNguyenSi/harness` — ⭐ GOLD — Declarative Control Plane

**What it is:** A YAML-based declarative harness. One YAML manifest defines grounding,
tools, memory, hooks, policies, and workflows. Includes a CLI to describe, validate,
diff, apply, and audit.

```yaml
# harness.yaml — what this looks like
agent:
  model: gemini-2.5-flash
  system_prompt: "..."

tools:
  - name: search_symbols
    risk: low        # auto-allow
  - name: query_cypher
    risk: medium     # log + validate
    validators:
      - type: pattern_block
        pattern: "^(CREATE|DELETE|MERGE|SET|DROP)"
        message: "Write operations not allowed. Use read-only Cypher."
  - name: analyze_impact
    risk: low

policy:
  approval_required_for: [high, destructive]
  blocked_tools: []
  audit_log: true

budget:
  max_llm_calls: 50
  max_tool_calls: 200
  max_seconds: 600

memory:
  file: ./memory.md
  max_lines: 500
```

**Key insight:** Harness as code — versioned, diffable, auditable. A YAML config that
declares what the agent is **allowed to do** not just what it can do.

**GitHub:** `github.com/LanNguyenSi/harness`

---

#### 3. `KRLabsOrg/LettuceDetect` — ⭐⭐ DIAMOND MINE — 609 Stars — Output Grounding

**What it is:** Production-ready span-level grounding verifier. Localizes exactly which
parts of an AI response are unsupported by the source evidence. 609 stars. June 2026.

**This is the tool that implements our ITEM 8 (epistemic classification) and ITEM 4
(report grounding check) in ~3 lines:**

```python
pip install lettucedetect

from lettucedetect.models.inference import HallucinationDetector

detector = HallucinationDetector(
    method="transformer",
    model_path="KRLabsOrg/lettucedect-base-modernbert-en-v1",
)

# For our impact report grounding check:
contexts = ["\n".join(all_kuzu_query_results)]  # actual graph data
question = "What services are affected by this change?"
answer = impact_report_text  # the report ImpactAgent produced

predictions = detector.predict(
    context=contexts,
    question=question,
    answer=answer,
    output_format="spans"
)
# Returns: [{'start': 45, 'end': 89, 'text': 'fraud-service', 'confidence': 0.94}]
# → "fraud-service" mentioned in report is NOT supported by graph data
```

**v2 (June 2026) adds TYPED spans for tool-grounded outputs:**

```python
# NEW: detects hallucination TYPE for agent tool output
detector = HallucinationDetector(
    method="transformer",
    model_path="KRLabsOrg/lettucedect-v2-mmbert-base",
    taxonomy_head="KRLabsOrg/lettucedect-v2-taxonomy-head",
)
predictions = detector.predict(...)
# Returns: [{'text': 'fraud-service', 'category': 'contradiction',
#             'subcategory': 'entity_fabrication'}]
```

**Performance:** 17 F1 points better than GPT-4.1-mini as a judge. <15ms overhead.

**Replaces our manually-written grounding check with a proven ML model.**

**GitHub:** `github.com/KRLabsOrg/LettuceDetect`

---

#### 4. `malina-florea/intake-agent` — ⭐ Gold — Sandwich Pattern

**What it is:** "Four stages: two LLM agents bracketed by two deterministic Python layers.
Safety-critical decisions — grounding validation and escalation — are non-stochastic
and auditable."

This is exactly the Coding Agent Sandwich (deterministic → LLM → deterministic) in a
working implementation. Can read the code to see how they implement the brackets.

**GitHub:** `github.com/malina-florea/intake-agent`

---

#### 5. `moortekweb-art/agentic-harness` — ⭐ Gold — Completion Gate

**What it is:** "Adds a completion gate to Codex, OpenCode, Aider, or any compatible
model. Keeps the objective, records the work, runs a check you control, and only then
reports Verified done."

This is a standalone completion gate — exactly what our VerifierAgent + DeterministicGate
combination does. Can be studied for the gate interface design.

**GitHub:** `github.com/moortekweb-art/agentic-harness`

---

#### 6. `maisieyang/build-my-own-harness` — ⭐ GOLD — 17 Phase Step-by-Step

**What it is:** Production-grade Python LLM agent harness built phase by phase over 23 days.
17 phases covering: tool loop, MCP, sandbox, sub-agents.

**The 17 phases (each is a Forge implementation item):**
```
Phase 1:  Bare tool loop (model call → parse tool → execute → feed back)
Phase 2:  Tool registry (named tools with schemas)
Phase 3:  Policy gate (allow/deny before execution)
Phase 4:  Budget enforcement (token/time/call limits)
Phase 5:  Structured logging (JSONL event log)
Phase 6:  File-based memory (AGENTS.md + append-only notes)
Phase 7:  Context compaction (summarize old turns)
Phase 8:  Post-run reports (Markdown summary)
Phase 9:  Hooks (pre/post tool execution)
Phase 10: Sandbox (workspace boundary enforcement)
Phase 11: Error evidence preservation
Phase 12: Loop detection
Phase 13: Self-verification gate
Phase 14: Time budget injection (turn countdown)
Phase 15: MCP connector
Phase 16: Sub-agent spawning
Phase 17: KV-cache optimization
```

**Direct mapping to Forge:**
- Phase 3 = ITEM 6 (action boundary on query_cypher)
- Phase 5 = ITEM (structured event log for activity_log)
- Phase 9 = ITEM 3 (tool receipt logging)
- Phase 12 = existing verification loop
- Phase 13 = DeterministicGate

**GitHub:** `github.com/maisieyang/build-my-own-harness`

---

#### 7. `tahasiddiquii/ai-harness` — ⭐ Gold — Production Harness with All Components

"Production AI harness: the decision layer around an LLM — adaptive model routing,
PII + prompt-injection guardrails, hybrid RAG, a LangGraph agent loop, and end-to-end
Langfuse observability. Runs offline with zero API keys."

**Components (all built, not theoretical):**
- Adaptive model routing (route to flash vs pro based on complexity)
- PII guardrails (detect/redact before feeding to model)
- Prompt injection detection
- Hybrid RAG
- LangGraph orchestration
- Langfuse observability

**GitHub:** `github.com/tahasiddiquii/ai-harness`

---

#### 8. `strands-agents/harness-sdk` — ⭐ GOLD — Official SDK

"In one SDK you get lifecycle controls (turn limits, token budgets, cancellation, stop
reasons), tools and structured output, MCP, multi-agent patterns, memory and sessions,
model portability, streaming, guardrails, tracing, and evals."

This is an SDK specifically for building harnesses. Python + TypeScript.

**GitHub:** `github.com/strands-agents/harness-sdk`

---

#### 9. `smith-nathanh/rho-agent` — ⭐ Gold — CLI with Observability

"An agent harness and CLI written in Python with observability across agents."
Deploys AI agents with predefined permissions into real environments. Define a permission
profile, hand off a task, get back a result. Monitor live, review the full event trace.

**GitHub:** `github.com/smith-nathanh/rho-agent`

---

### GROUP B — State Persistence and Memory

---

#### 10. `roanbrasil/agents-integration-patterns` — ⭐ GOLD — Checkpoint-Resume Pattern

**The canonical checkpoint-resume pattern for agents:**

```python
# From checkpoint-resume.md
import json
import pickle
from pathlib import Path
from dataclasses import dataclass, asdict

@dataclass
class AgentCheckpoint:
    session_id: str
    stage: str           # current pipeline stage
    iteration: int
    task_context: dict   # the original task
    accumulated_results: dict  # what's been found so far
    activity_log: list
    timestamp: float

def save_checkpoint(checkpoint: AgentCheckpoint, path: str):
    """Serialize state after each significant step."""
    data = asdict(checkpoint)
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)
    print(f"[Checkpoint] Saved at stage={checkpoint.stage}, iteration={checkpoint.iteration}")

def load_checkpoint(path: str) -> AgentCheckpoint | None:
    """Load last checkpoint on resume."""
    p = Path(path)
    if not p.exists():
        return None
    with open(p) as f:
        data = json.load(f)
    return AgentCheckpoint(**data)

# Usage in pipeline:
def run_pipeline_with_checkpoints(task, checkpoint_path):
    cp = load_checkpoint(checkpoint_path)
    
    if cp:
        print(f"Resuming from stage={cp.stage}, iteration={cp.iteration}")
        state = restore_state_from_checkpoint(cp)
    else:
        state = initial_state(task)
    
    for stage in PIPELINE_STAGES:
        if cp and stage.name < cp.stage:
            continue  # Skip already-completed stages
        
        result = run_stage(stage, state)
        
        # Checkpoint AFTER each stage succeeds
        save_checkpoint(AgentCheckpoint(
            session_id=state.id,
            stage=stage.name,
            iteration=state.iteration,
            task_context=state.task,
            accumulated_results=state.results,
            activity_log=state.activity_log,
            timestamp=time.time()
        ), checkpoint_path)
        
        state = update_state(state, result)
    
    return state
```

**This is what Forge needs for pipeline state persistence.** Currently Forge loses
everything on server restart. This pattern adds SQLite or JSON persistence in ~50 lines.

**GitHub:** `github.com/roanbrasil/agents-integration-patterns`

---

#### 11. `lazynet/lazy-harness` — ⭐ Gold — SQLite-Backed Monitoring

"Persistent memory across sessions, isolated profiles, cross-platform hook engine,
SQLite-backed monitoring, knowledge directory, and a unified scheduler — all driven
by one TOML file."

**The SQLite monitoring schema (adaptable for Forge):**

```sql
-- From lazy-harness schema
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    started_at REAL,
    ended_at REAL,
    stage TEXT,
    task TEXT,
    status TEXT  -- running, completed, failed, interrupted
);

CREATE TABLE tool_calls (
    id TEXT PRIMARY KEY,
    session_id TEXT REFERENCES sessions(id),
    tool_name TEXT,
    inputs TEXT,  -- JSON
    result TEXT,  -- JSON
    error TEXT,
    duration_ms REAL,
    timestamp REAL
);

CREATE TABLE activity_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT REFERENCES sessions(id),
    message TEXT,
    level TEXT,  -- info, warning, error, success
    event_type TEXT,  -- tool_call, stage_change, harness_check
    metadata TEXT,  -- JSON
    timestamp REAL
);
```

**GitHub:** `github.com/lazynet/lazy-harness`

---

#### 12. `hacktivist123/agent-session-resume` — ⭐ Session Resume Skill

Cross-agent session resume skill for Claude Code, Codex, Antigravity, OpenCode.
Continues work from a prior session without losing context, duplicating completed
work, or overwriting unrelated changes.

The SKILL.md contains the exact prompts for how to write resumable state.

**GitHub:** `github.com/hacktivist123/agent-session-resume`

---

### GROUP C — Observability and Evals

---

#### 13. `openlit/openlit` — ⭐⭐ DIAMOND — OpenTelemetry for Agents

"Trace, evaluate, debug, and optimize AI applications and coding agents with
OpenTelemetry."

**The most complete observability solution for AI agents.**

```python
pip install openlit

import openlit
openlit.init(otlp_endpoint="http://127.0.0.1:4318")

# Now every LLM call and tool call is automatically traced
# Every Gemini ADK call in Forge gets: token count, latency, cost, tool name, input/output
```

**What it instruments automatically:**
- LLM calls (model, tokens, latency, cost)
- Tool calls (name, inputs, outputs, errors)
- Agent sessions (start, end, stage transitions)
- Exceptions and errors

**GitHub:** `github.com/openlit/openlit`

---

#### 14. `JudgmentLabs/judgeval` — ⭐ GOLD — Continuous Eval

"Judges produce structured behaviors — scored, labeled outputs that describe how your
agent acted — which accumulate into a searchable record of agent behavior over time."

**The eval pattern (directly applicable to Forge):**

```python
from judgeval import Judge, Rubric

# Define what a good impact report looks like
impact_report_rubric = Rubric([
    "Does the report contain Layer 0, Layer 1, Layer 2 sections?",
    "Does every service mentioned exist in the code graph?",
    "Does every function mentioned exist in the code graph?",
    "Does the execution order follow dependency direction?",
    "Are confidence levels (HIGH/MEDIUM/LOW) justified?"
])

judge = Judge(model="gemini-2.5-flash", rubric=impact_report_rubric)

# Run after every pipeline completion
result = judge.evaluate(
    context=known_graph_data,
    response=impact_report_text
)
# Returns: {score: 0.85, passed: ['Layer sections', 'execution order'],
#           failed: ['service fraud-service not in graph']}
```

**GitHub:** `github.com/JudgmentLabs/judgeval`

---

#### 15. `disler/claude-code-hooks-multi-agent-observability` — ⭐ Multi-Agent Tracing

"Real-time monitoring for Claude Code agents through simple hook event tracking.
With Claude Opus 4.6 and multi-agent orchestration, you can trace every tool call,
task handoff, and agent lifecycle event across the entire swarm."

**The hook-based event model:**

```python
# From the observability hooks
def on_tool_call_start(agent_id: str, tool_name: str, inputs: dict):
    event = {
        "type": "tool_call_start",
        "agent_id": agent_id,
        "tool": tool_name,
        "inputs": inputs,
        "timestamp": time.time()
    }
    emit_event(event)

def on_tool_call_end(agent_id: str, tool_name: str, result: dict, error: str = None):
    event = {
        "type": "tool_call_end",
        "agent_id": agent_id,
        "tool": tool_name,
        "result_size": len(str(result)),
        "error": error,
        "timestamp": time.time()
    }
    emit_event(event)

def on_agent_handoff(from_agent: str, to_agent: str, context: dict):
    event = {
        "type": "agent_handoff",
        "from": from_agent,
        "to": to_agent,
        "context_size": len(str(context)),
        "timestamp": time.time()
    }
    emit_event(event)
```

**GitHub:** `github.com/disler/claude-code-hooks-multi-agent-observability`

---

#### 16. `SpillwaveSolutions/mastering-langgraph-agent-skill` — ⭐ LangGraph Memory

"Build stateful AI agents and agentic workflows with LangGraph in Python. Covers
tool-using agents, branching workflows, memory persistence, human-in-the-loop,
multi-agent systems, and production deployment."

**LangGraph checkpointing (the production-grade state persistence):**

```python
from langgraph.graph import StateGraph
from langgraph.checkpoint.sqlite import SqliteSaver

# SQLite persistence — survives server restarts
memory = SqliteSaver.from_conn_string("forge_sessions.db")

workflow = StateGraph(PipelineState)
workflow.add_node("gathering", gathering_node)
workflow.add_node("analyzing", analyzing_node)
workflow.add_node("verifying", verifying_node)

app = workflow.compile(checkpointer=memory)

# Every step is checkpointed automatically
# If server restarts, resume with:
config = {"configurable": {"thread_id": pipeline_id}}
app.invoke({"message": user_input}, config)
```

**GitHub:** `github.com/spillwavesolutions/mastering-langgraph-agent-skill`

---

## Part 2: Medium Articles — Production Implementation Patterns

### Article 1: "The Definitive Guide to Agent Harness Engineering" (Medium, April 2026)
**URL:** engineeratheart.medium.com

**The 4 Levers with production code:**

#### Lever 1: Context Design — LocalContextMiddleware

```python
class LocalContextMiddleware:
    SECRET_PATTERNS = re.compile(
        r'(api[_-]?key|secret|password|token|auth|credential)', re.IGNORECASE
    )
    
    def build_context(self, workspace_root: str, max_tokens: int = 2000) -> str:
        dir_tree = self._scan_directory(workspace_root, max_depth=3)
        available_tools = self._list_tool_names()
        env_vars = self._safe_env_scan()
        return f"## Environment Map\n\n### Workspace\n{dir_tree}\n\n### Tools\n{available_tools}\n\n### Environment\n{env_vars}"
    
    def _safe_env_scan(self) -> str:
        safe = {}
        for key, val in os.environ.items():
            if self.SECRET_PATTERNS.search(key):
                safe[key] = "[REDACTED]"
            else:
                safe[key] = val
        return "\n".join(f"{k}={v}" for k, v in safe.items())
```

**For Forge:** Before each agent run, inject: available services from graph, known
tool names, current pipeline stage. Zero orientation turns.

---

#### Lever 1: KV-Cache Optimization

```python
# BREAKS CACHE — never do this
system_prompt = f"Current time: {datetime.now().isoformat()}"

# CORRECT — date-level only
system_prompt = "You are Forge ImpactAgent."
user_message = f"[Session: {date.today().isoformat()}] {user_query}"

# Deterministic serialization — same bytes = cache hit
good = json.dumps(result, sort_keys=True, separators=(',', ':'))

# AppendOnlyContext — never rewrite, never reorder
class AppendOnlyContext:
    def __init__(self, system_prompt):
        self.system_prompt = system_prompt  # Never mutated
        self.turns = []
    
    def append(self, role, content):
        self.turns.append({"role": role, "content": content})
        # NEVER insert, delete, or reorder — only append
```

**For Forge ImpactAgent:** The system prompt (SYSTEM_INSTRUCTION in prompts.py) 
must never change mid-session. Remove any timestamp injection.

---

#### Lever 1: todo.md Pattern (Goal Drift Prevention)

```python
# Inject into ImpactAgent system prompt:
TODO_MD_PROTOCOL = """
## Task Management Protocol
Maintain a mental task list throughout this analysis:
1. At start: Note what services/functions you need to analyze
2. At each step: Check you are still working toward the analysis goal
3. Before finishing: Verify all services in requirements are covered

If you find yourself analyzing unrelated code, STOP and return to the main task.
"""
```

**For Forge:** The ImpactAgent runs 50+ tool calls. Without this, it drifts after
turn 20 and starts analyzing unrelated services.

---

#### Lever 1: Preserve Error Evidence

```python
# WRONG — clean slate retries
def retry_analysis(agent, requirements):
    agent.clear_context()  # Don't do this
    return agent.analyze(requirements)

# CORRECT — keep evidence, add failure context
def retry_with_evidence(agent, requirements, failed_result):
    error_context = json.dumps({
        "failed_at": failed_result.last_tool_call,
        "error": failed_result.error,
        "gaps_found": failed_result.gaps
    }, sort_keys=True)
    agent.append_to_context(f"\n## Previous Attempt Failed\n{error_context}")
    return agent.analyze(requirements)
```

**For Forge:** When VerificationAgent finds gaps and triggers a re-run, the gaps
ARE the error evidence. Currently they're passed correctly. ✅

---

#### Lever 2: Tool Cliff Effect and Consolidation

```
10 tools  → Perfect performance
30 tools  → Noticeable degradation
107 tools → Complete failure

Vercel: 15+ tools → 1 bash tool = 100% success, 37% fewer tokens
```

**Forge tool count:**
- ImpactAgent: 6 tools ✅ (well under cliff)
- DesignAgent: ~9 query types ✅ (fine)
- ContextGathererAgent: 5 tools ✅
- VerificationAgent: 7 tools ✅

**Forge is safe.** No tool count problem.

---

#### Lever 2: Embedding Router (for future when tools grow)

```python
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

class EmbeddingToolRouter:
    def __init__(self, core_tools, extended_tools):
        self.core_tools = core_tools  # Always included (≤10)
        self.extended_tools = extended_tools  # Dynamically added
        self.embedder = SentenceTransformer('all-MiniLM-L6-v2')
        self.tool_embeddings = self._embed_tools(extended_tools)
    
    def get_tools_for_task(self, task_description: str, top_k: int = 5):
        task_embedding = self.embedder.encode(task_description)
        similarities = cosine_similarity([task_embedding], self.tool_embeddings)[0]
        top_indices = similarities.argsort()[-top_k:][::-1]
        dynamic_tools = [self.extended_tools[i] for i in top_indices]
        return self.core_tools + dynamic_tools  # Never exceeds 15
```

---

#### Lever 3: Reasoning Sandwich

```python
# LangChain Terminal Bench 2.0 results:
# xhigh everywhere: 53.9%
# high everywhere:  63.6%
# SANDWICH:         66.5%  ← WINNER

class ReasoningSandwichScheduler:
    PHASE_REASONING = {
        "gathering":    "high",   # Simple Q&A
        "analyzing":    "xhigh",  # Complex multi-hop graph reasoning
        "verifying":    "xhigh",  # Checking completeness
        "filling_gaps": "high",   # Targeted gap filling
    }
    
    def get_budget_tokens(self, stage: str) -> int:
        level = self.PHASE_REASONING.get(stage, "high")
        return 10000 if level == "xhigh" else 5000
```

**For Forge:** ImpactAgent analyzing complex requirements should use xhigh.
ImpactAgent filling gaps (iteration 2, 3) should use high.

---

#### Lever 3: Loop Detection

```python
class LoopDetectionMiddleware:
    def __init__(self, window=5, threshold=3):
        self.window = window
        self.threshold = threshold
        self.action_history = []
    
    def check_and_intervene(self, current_action: dict) -> tuple[bool, str]:
        self.action_history.append(current_action)
        recent = self.action_history[-self.window:]
        
        # Detect same tool call with same inputs repeating
        tool_calls = [(a.get("tool"), json.dumps(a.get("inputs", {}), sort_keys=True))
                      for a in recent]
        
        for call in set(tool_calls):
            if tool_calls.count(call) >= self.threshold:
                return True, (
                    f"You have called {call[0]} with the same inputs "
                    f"{tool_calls.count(call)} times without progress. "
                    f"Try a different approach or tool."
                )
        return False, ""
```

**For Forge ImpactAgent:** Without this, the agent can get stuck calling
`analyze_impact("processPayment")` repeatedly when it gets the same result.

---

#### Lever 3: Self-Verification Gate

```python
PRE_COMPLETION_CHECKLIST = """
Before marking this analysis complete, verify:

## Completeness
- [ ] Every service in the requirements has been analyzed
- [ ] Layer 0 contains at least one direct change
- [ ] Execution order follows dependency graph
- [ ] Every service named exists in the code graph

## Confidence
- [ ] Every HIGH confidence claim has graph evidence
- [ ] INFERRED claims are clearly labeled
- [ ] GAPs are listed for items that cannot be determined

Only after verifying ALL items above should you produce the final report.
"""
```

**For Forge:** Add this to ImpactAgent's `analyze_for_pipeline` prompt as
a mandatory pre-completion step.

---

#### Lever 3: Time Budget Injection

```python
class BudgetAwareContextInjector:
    def get_budget_message(self, remaining_turns: int) -> str | None:
        if remaining_turns == 2:
            return """
# CRITICAL: 2 turns remaining.
Wrap up immediately. Output what you have. Do not start new analysis."""
        elif remaining_turns == 5:
            return f"""
Note: {remaining_turns} turns remaining. 
Prioritize: complete current service analysis, do not start new ones."""
        elif remaining_turns == 10:
            return f"Budget notice: {remaining_turns} turns remaining."
        return None
```

**For Forge:** The max_iterations=3 loop already has a cap. Add budget messages at
each iteration to prevent the agent from starting large analyses it can't finish.

---

#### Lever 4: Observability — What to Instrument

```python
@dataclass
class HarnessMetrics:
    tool_calls: int = 0
    tool_errors: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    loop_detections: int = 0
    compactions: int = 0
    
    @property
    def cache_hit_rate(self): return self.cache_hits / (self.cache_hits + self.cache_misses)
    
    @property
    def error_rate(self): return self.tool_errors / self.tool_calls

def instrument_tool(metrics: HarnessMetrics):
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                result = fn(*args, **kwargs)
                metrics.tool_calls += 1
                return result
            except Exception:
                metrics.tool_calls += 1
                metrics.tool_errors += 1
                raise
            finally:
                elapsed_ms = (time.perf_counter() - start) * 1000
                metrics.tool_latencies.setdefault(fn.__name__, []).append(elapsed_ms)
        return wrapper
    return decorator

# Target metrics:
# cache_hit_rate > 80% (below 50% = prefix breaking somewhere)
# error_rate < 10% per tool (above 30% = redesign or remove)
# loop_detections per run → target 0 in steady state
```

---

### Article 2: "Build Your First Agent Harness in 90 Minutes" (DataCamp, Sep 2026)
**URL:** datacamp.com/tutorial/agent-harness-engineering

**The ratchet principle (most important concept for ongoing Forge maintenance):**

> "When an agent makes a mistake, engineer a fix so it never repeats that mistake.
> A good harness is just compressed trial and error."

**The full production harness code is in the article (AGENTS.md + hooks + compaction
+ loop in one file). Key patterns extracted:**

**Hook pattern — deprecated import blocker:**

```python
def deprecated_import_hook(tool_name: str, tool_input: dict) -> str:
    """Add to Forge: block any attempt to write code that imports deprecated services."""
    if tool_name != "write_file":
        return ""
    content = tool_input.get("content", "")
    # Add Forge-specific checks here
    if "require('../../../services/" in content:
        return (
            "\n\n[HOOK] Cross-service imports are not allowed in generated code. "
            "Use HTTP calls via the appropriate client file instead."
        )
    return ""
```

**Compaction — safe boundary detection:**

```python
def compact_messages(messages, threshold=20, keep_recent=6):
    if len(messages) <= threshold:
        return messages
    
    # NEVER split a tool_use/tool_result pair
    cut = len(messages) - keep_recent
    while cut < len(messages) and is_tool_result(messages[cut]):
        cut += 1  # Slide cut forward to safe boundary
    
    old, recent = messages[1:cut], messages[cut:]
    # Summarize old turns with a cheap fast model
    summary = summarize_with_cheap_model(old)
    
    return [
        messages[0],  # Keep original task verbatim
        {"role": "user", "content": f"[Earlier progress]\n{summary}"},
        *recent
    ]
```

---

### Article 3: "Agentic Architectures: Harness Engineering and the Agent Runtime Layer" (Xero DevBlog, Medium)
**URL:** topuzas.medium.com

**Production failure patterns (what breaks in real deployments):**

> "Your evals look clean. You demo it to your team and it works beautifully.
> Then you push it to production and watch it slowly destroy itself — calling
> the same tool eleven times, confidently returning a result it never actually
> verified, or hanging indefinitely because a downstream API returned a 401
> and nobody taught it what to do next."

**The four production failures Forge should guard against:**

1. **Same tool called 11 times** → Loop detection (Article 1, ITEM in plan)
2. **Returns result it never verified** → Tool receipt logging (ITEM 3)
3. **Hangs on 401** → Budget/timeout enforcement (Article 2)
4. **Confidently wrong output** → Output grounding (LettuceDetect)

---

## Part 3: Mostly-Programmatic Implementations (No AI)

### P1: The Policy Gate — Pure Python, Zero Dependencies

```python
# The minimal action boundary — no libraries, no AI
class PolicyGate:
    WRITE_OPS = frozenset(["CREATE ", "DELETE ", "MERGE ", "SET ", "DROP ", "REMOVE "])
    
    def check_cypher(self, query: str) -> tuple[bool, str]:
        upper = query.strip().upper()
        for op in self.WRITE_OPS:
            if upper.startswith(op) or f"\n{op}" in upper:
                return False, (
                    f"Write operation '{op.strip()}' blocked. "
                    f"Only read queries allowed. Use MATCH/RETURN."
                )
        return True, ""
    
    def check_symbol_name(self, name: str) -> tuple[bool, str]:
        if not name or not name.strip():
            return False, "symbol_name cannot be empty"
        if len(name) > 200:
            return False, "symbol_name exceeds 200 chars — likely malformed input"
        if any(c in name for c in [';', '--', '/*', '\n']):
            return False, f"symbol_name contains invalid characters: {name[:50]}"
        return True, ""
    
    def check_service_names(self, names: list, known: list) -> tuple[list, list]:
        valid = [n for n in names if n in known]
        invalid = [n for n in names if n not in known]
        return valid, invalid
```

**30 lines. Zero dependencies. Catches 100% of write operation attacks on Kuzu.**

---

### P2: Tool Receipt Logger — Pure Python

```python
# The simplest possible tool receipt system
import time
from threading import local

_receipts = local()  # Thread-local so parallel agents don't conflict

def init_receipts():
    _receipts.log = []

def log_receipt(tool_name: str, inputs: dict, result_count: int):
    if not hasattr(_receipts, 'log'):
        _receipts.log = []
    _receipts.log.append({
        "tool": tool_name,
        "inputs": {k: str(v)[:100] for k, v in inputs.items()},
        "result_count": result_count,
        "timestamp": time.time()
    })

def get_receipts() -> list:
    return getattr(_receipts, 'log', [])

def assert_tools_were_used(min_calls: int = 1):
    receipts = get_receipts()
    if len(receipts) < min_calls:
        raise ValueError(
            f"Agent produced output without calling graph tools "
            f"(expected ≥{min_calls} calls, got {len(receipts)}). "
            f"This indicates training data was used instead of the code graph."
        )
    return receipts
```

**20 lines. Thread-safe. Direct drop-in for ITEM 3.**

---

### P3: State Persistence — SQLite in 40 Lines

```python
import sqlite3, json, time

DB_PATH = "forge_sessions.db"

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                stage TEXT,
                created_at REAL,
                updated_at REAL,
                state_json TEXT
            );
            CREATE TABLE IF NOT EXISTS tool_calls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                tool TEXT,
                inputs TEXT,
                result_count INTEGER,
                error TEXT,
                ts REAL
            );
        """)

def save_session(pipeline_id: str, stage: str, state_dict: dict):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            INSERT OR REPLACE INTO sessions (id, stage, created_at, updated_at, state_json)
            VALUES (?, ?, COALESCE((SELECT created_at FROM sessions WHERE id=?), ?), ?, ?)
        """, (pipeline_id, stage, pipeline_id, time.time(), time.time(),
              json.dumps(state_dict)))

def load_session(pipeline_id: str) -> dict | None:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT state_json FROM sessions WHERE id=?", (pipeline_id,)
        ).fetchone()
    return json.loads(row[0]) if row else None
```

**40 lines. Survives server restarts. No new dependencies (sqlite3 is stdlib).**

---

## Part 4: Complete Gap Analysis — What Forge Has vs What's Available

| What's Available | Forge Has | Add With |
|-----------------|-----------|---------|
| **Validation** | | |
| Policy gate (write-op blocking) | ❌ ITEM 6 planned | P1 above — 30 lines |
| Input contract validation | ❌ ITEM 1 planned | Built-in — 20 lines |
| LettuceDetect output grounding | ❌ Not planned yet | `pip install lettucedetect` |
| Tool receipt logging | ❌ ITEM 3 planned | P2 above — 20 lines |
| **State & Persistence** | | |
| SQLite session persistence | ❌ In-memory only | P3 above — 40 lines |
| Checkpoint-resume pattern | ❌ None | roanbrasil pattern — 50 lines |
| LangGraph checkpointing | ❌ Not using LangGraph | SpillwaveSolutions skill |
| **Observability** | | |
| Structured event types | ⚠️ Basic activity_log | 10-line enhancement |
| OpenTelemetry tracing | ❌ None | `pip install openlit` |
| Tool call latency tracking | ❌ None | instrument_tool decorator |
| Cache hit rate tracking | ❌ None | AppendOnlyContext wrapper |
| **Context Management** | | |
| LocalContextMiddleware (orientation) | ❌ None | 40-line class |
| KV-cache optimization | ❌ Timestamps may break cache | Fix: remove timestamps from prompts |
| todo.md goal drift prevention | ❌ None | System prompt addition |
| Message compaction | ❌ None | compact_messages — 30 lines |
| Error evidence preservation | ✅ Gap filling loop | Good |
| **Tool Management** | | |
| Tool count audit | ✅ Forge has ≤9 tools per agent | Already safe |
| Budget enforcement | ⚠️ max_iterations=3 only | Add wall-clock + token budget |
| Loop detection | ❌ None | LoopDetectionMiddleware — 30 lines |
| Self-verification gate | ✅ VerifierAgent + DeterministicGate | Good |
| Reasoning sandwich | ❌ Flat model config | ReasoningSandwichScheduler |
| **Evals** | | |
| Fixed test cases | ❌ None | judgeval — 3 test cases |
| Regression detection | ❌ None | Replay eval pattern |

---

## Part 5: Priority Implementation Order (Research-Backed)

Based on what practitioners say gives the highest return:

### Phase 1 — Free wins (under 50 lines each, zero new deps)

1. **KV-cache fix** — Remove any `datetime.now()` from system prompts.
   Search `prompts.py` for timestamps. Delete them. **10 minutes, huge cost saving.**

2. **Tool receipt logger** — P2 above. Thread-safe, 20 lines, directly enables ITEM 3.

3. **Policy gate for query_cypher** — P1 above. 30 lines, prevents Kuzu corruption.

4. **SQLite session persistence** — P3 above. 40 lines, prevents pipeline loss on restart.

5. **todo.md goal drift protocol** — Add to ImpactAgent system prompt. 5 lines.

### Phase 2 — Medium effort (under 100 lines, minimal deps)

6. **LettuceDetect grounding** — `pip install lettucedetect`. 3 lines of usage.
   Replaces manually-written grounding check with an ML model (609 stars, proven).

7. **Loop detection middleware** — LoopDetectionMiddleware above. 30 lines.

8. **Reasoning sandwich** — ReasoningSandwichScheduler above. 20 lines + config.

9. **Structured event types** — Add `event_type` to `activity_log`. 10 lines.

10. **Budget injection** — BudgetAwareContextInjector. 20 lines + wired into loop.

### Phase 3 — Production hardening

11. **OpenLit observability** — `pip install openlit` + `openlit.init()`. Full OTel tracing.

12. **JudgeVal evals** — 3 fixed test cases for retry logic scenario.

13. **Checkpoint-resume pattern** — Full LangGraph or custom SQLite-based resume.

---

## The Harness Engineering Checklist (from Definitive Guide)

From the most comprehensive checklist found — adapted for Forge:

**Context Design:**
- [ ] System prompts have NO second-precision timestamps
- [ ] Messages are append-only (never rewrite/reorder)
- [ ] JSON serialized with `sort_keys=True` for cache stability
- [ ] Environment map (services + tools) injected at session start
- [ ] AGENTS.md / system prompts under 60 lines, human-written
- [ ] Error evidence preserved on retries (not scrubbed)
- [ ] todo.md protocol in ImpactAgent prompt

**Tool Management:**
- [ ] All agents have <15 tools (Forge: ✅)
- [ ] query_cypher has write-op policy gate
- [ ] Tool calls have receipt logging
- [ ] Budget enforcement (calls + time)
- [ ] Loop detection active

**Constraint Management:**
- [ ] Reasoning sandwich configured (xhigh for analysis, high for execution)
- [ ] Self-verification gate (VerifierAgent + DeterministicGate ✅)
- [ ] Turn budget warnings injected (at 2 and 5 remaining)
- [ ] Pre-completion checklist in ImpactAgent prompt

**State & Observability:**
- [ ] SQLite session persistence (survives restarts)
- [ ] Structured event log with event_type field
- [ ] Tool call latency tracked
- [ ] Cache hit rate tracked
- [ ] Harness versioned in git

---

*Research completed: September 2026*  
*Sources: GitHub (agent-harness-90m, LanNguyenSi/harness, KRLabsOrg/LettuceDetect,*  
*maisieyang/build-my-own-harness, tahasiddiquii/ai-harness, strands-agents/harness-sdk,*  
*smith-nathanh/rho-agent, roanbrasil/agents-integration-patterns, lazynet/lazy-harness,*  
*openlit/openlit, JudgmentLabs/judgeval, disler/claude-code-hooks-multi-agent-observability,*  
*SpillwaveSolutions/mastering-langgraph-agent-skill, ai-boost/awesome-harness-engineering)*  
*Medium (The Definitive Guide to Agent Harness Engineering — engineeratheart,*  
*AI Agent Best Practices 2026 — tort_mario, Agentic Architectures — topuzas)*  
*DataCamp (Agent Harness Engineering Tutorial — Tim Lu)*
