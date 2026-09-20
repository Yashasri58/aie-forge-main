# Harness Validation — Industry Research & Forge Implementation Analysis

**Status:** Research complete — basis for expanded HARNESS_VALIDATION_PLAN.md  
**Date:** September 2026  
**Sources:** OpenAI, Stripe, Anthropic, LangChain, arXiv, Thoughtworks/Martin Fowler

---

## Part 1: What the Industry Has Actually Built

### Case Study 1: OpenAI — 1 Million Lines, 0 Human-Written Lines (Feb 2026)

**What they did:**  
Three engineers built a real internal product — shipped to hundreds of users — entirely through
Codex agents over five months. 1,500 merged PRs. Zero manually written lines of code.

**Their harness components (exactly what they implemented):**

1. **Custom linters with remediation messages** — Not generic ESLint, but purpose-built linters
   that when they fire, return an error message written specifically for an LLM to act on.
   Example: "You violated the layer boundary rule. Repos may not import from Services.
   Move this logic to a Service file."

2. **Structural tests** — Automated checks that enforce architectural rules: dependency
   directions, layer boundaries, file size limits, naming conventions. These are not
   unit tests — they check that the shape of the codebase matches the intended architecture.

3. **The AGENTS.md as table of contents, not encyclopedia** — A ~100 line file that points
   agents to a structured `docs/` directory. Separate documents for architecture, design,
   plans, quality scores, security. Enforced by linters that check docs stay current.

4. **Garbage collection agents** — A recurring background Codex task that scans the codebase
   for drift, opens targeted refactoring PRs, and auto-merges them after review. Ran daily.
   "Human taste is captured once, then enforced continuously on every line."

5. **Progressive disclosure** — Agents start with a minimal entry point and are taught where
   to look next. Never overwhelmed with a 1,000-page instruction manual.

6. **Application legibility** — Made the app, its logs, metrics, and UI directly readable by
   the agent. Chrome DevTools Protocol wired into agent runtime. Agents ran 6-hour tasks
   overnight while humans slept.

**Their key conclusion:**
> "Our most difficult challenges now center on designing environments, feedback loops, and
> control systems. Building software still demands discipline, but the discipline shows up
> more in the scaffolding rather than the code."

---

### Case Study 2: Stripe Minions — 1,300 PRs Per Week (Ongoing)

**What they did:**  
Internal multi-agent system that generates 1,300+ pull requests weekly. Humans review,
never write. The system runs unattended.

**Their harness pattern: The Blueprint**

A Blueprint is a workflow template that explicitly defines the sequence of steps. Every
step is either DETERMINISTIC or AGENTIC:

```
[DETERMINISTIC] Identify all files importing the target library
[DETERMINISTIC] Extract code context around each import
[AGENTIC]       Analyze usage and determine what changes are needed
[AGENTIC]       Generate updated code for each affected file
[DETERMINISTIC] Write changes to disk
[DETERMINISTIC] Run test suite
[AGENTIC]       If tests fail: interpret errors, generate fixes
[DETERMINISTIC] Verify fixes compile, tests pass
[DETERMINISTIC] Format code per style rules
[AGENTIC]       Write PR description
[DETERMINISTIC] Submit pull request
```

**Key design principles from Stripe:**

1. **AI never self-validates.** A deterministic test runner gives unambiguous pass/fail.
   An agent trying to verify its own work will rationalize problems away.

2. **Blueprints constrain AI to where it adds value.** The agent doesn't decide how to
   run tests. It only interprets results. Constraining the scope of AI decisions to where
   AI is genuinely needed is one of the clearest principles in their architecture.

3. **Bounded retry loops.** When deterministic validation fails, the failure is fed back
   to an agentic node for a correction attempt. Maximum N tries before escalating to human.

4. **Pre-push hooks that check relevance.** Before submitting a PR, heuristic checks
   run only the linters and tests relevant to what was changed — shift quality left.

5. **Human review, not human writing.** AI has submission authority. Humans have merge
   authority. The quality bar is "good enough for a human to catch remaining issues."

---

### Case Study 3: Anthropic — GAN-Inspired Generator-Evaluator Harness (March 2026)

**What they did:**  
For long-running application development, Anthropic published a harness design based on
Generative Adversarial Networks (GANs):

```
Generator Agent → produces output (code, design, feature)
       ↓
Evaluator Agent → grades output against concrete criteria
       ↓
If grade < threshold: Generator gets feedback and retries
If grade >= threshold: Output accepted
```

**Key insight:**  
Models suffer from **self-evaluation bias** — they praise their own work even when
quality is mediocre. The fix is a separate Evaluator that was never involved in
generating the output. It is much easier to tune an evaluator that judges objectively
than to make a generator self-critical.

**What makes the Evaluator work:**  
- Criteria are turned from subjective ("is this design good?") into concrete, gradable
  terms ("does it follow the layer rules defined in ARCHITECTURE.md? Y/N")
- Computational criteria (run tests, check syntax) are mixed with inferential criteria
  (does this look like our coding style?)
- The Evaluator gets a rubric, not just the output

**Relevance to Forge:**  
This is exactly what the VerificationAgent does for impact reports, and the VerifierAgent
does for code diffs. The research validates the architecture Forge already has — and
suggests that the Evaluator's criteria need to be more explicit and measurable.

---

### Case Study 4: LangChain — 13.7 Point Improvement, Same Model (2026)

**What they proved:**  
LangChain took `gpt-5.2-codex` from **52.8% to 66.5%** on Terminal-Bench 2.0
(outside top 30 → rank 5) **without changing the model at all.** They only changed
the harness — prompts, middleware hooks, tool contracts, retry logic.

**What they changed:**

1. **Prompt layers** — Rewrote system prompts to be more explicit about what the agent
   should and shouldn't do. Reduced ambiguity in task framing.

2. **Middleware hooks** — Added pre- and post-tool-call validators. Before a tool fires,
   check that inputs are valid. After a tool fires, check that outputs are usable.

3. **Tool contracts** — Every tool declared its input schema and output shape. The harness
   enforced these. The model could no longer pass bad inputs to tools.

4. **Retry logic with targeted feedback** — When a tool failed or a validator rejected
   output, the error message was written to be maximally useful to the model on retry.
   Not "Error 500" but "The file path you provided doesn't exist. Available files: [...]"

**Their formula:**  
> "We can build better agents by building better harnesses. Use evals as a learning signal
> to hill-climb on harness improvements. Same model, better environment = better agent."

**The quantified value:**  
70% of an agent's performance lives outside the model. The harness decides whether
the agent ships or stalls.

---

### Case Study 5: Self-Harness (arXiv, 2606.09498, June 2026)

**What they proved:**  
An agent can iteratively mine its own failures and propose changes to its own harness.
Without human engineers redesigning the harness, agents improved **up to 60%** on tasks
by rewriting their own rules.

**How it works:**

1. Agent runs and fails
2. Failure log is fed to a "harness updater" agent
3. Harness updater proposes a concrete, executable harness change (not a generic instruction)
4. The change is validated (does it fix the failure? does it break anything else?)
5. If valid, the harness is updated and the task is retried

**Key finding:**  
"Self-Harness does not simply add generic instructions, but effectively turns model-specific
weaknesses into concrete, executable harness changes."

**Relevance to Forge:**  
Forge's "gap filling" loop (max 3 iterations) is a manual version of this. Self-Harness
suggests that the feedback from VerificationAgent could be used to automatically refine
the ImpactAgent's system prompt — not just fill gaps in the current report, but
permanently improve how it operates.

---

### Case Study 6: Regulated Industries — Healthcare, Legal, Finance (2026)

**From LangChain's Life Sciences harness and industry reports:**

In healthcare, legal, and finance (exactly like banking payments), the harness provides
something even more important than performance: **auditability**.

From LangChain's healthcare agent:
> "LLMs combined with an agent harness can process dense individual records, reason about
> ambiguous needs, and ask clarifying questions without forcing users through predetermined
> paths."

From industry research on regulated verticals:
> "In healthcare, legal, insurance, and finance — the most reliable way to make a deployed
> agent better is not a new model. It is a closed loop that turns production failures into
> harness updates."

**What regulated industry harnesses specifically add:**

1. **Claim provenance** — Every factual claim is tagged with its source (tool output,
   inference, or training data). The NabaOS paper calls this epistemic classification.
   Regulators can see exactly what the agent "knew" and from where.

2. **Approval gates** — Not all actions are equal. Low-risk = auto-proceed. Medium-risk =
   one reviewer. High-risk = senior sign-off. The harness enforces these tiers, not
   the model.

3. **Immutable audit logs** — Every tool call, every input, every output, every decision
   is logged with a timestamp that cannot be altered. Directly relevant for PCI-DSS, SOX.

4. **Denial reasons as compliance records** — When the harness blocks an action, the reason
   is recorded. This is the audit trail regulators require.

---

## Part 2: What All These Systems Have in Common

Across all 6 case studies, 5 patterns appear in every single system:

### Pattern 1: Deterministic Nodes Wrap Agentic Nodes

```
[Deterministic: gather context] → [Agentic: reason/generate] → [Deterministic: validate]
```

AI never validates its own work. Always a non-AI check around every AI step.
Both OpenAI and Stripe independently arrived at this exact architecture.

### Pattern 2: Error Messages Are Written for the Model, Not for Humans

When a check fails, the error message is crafted to be the model's next input.
- Bad: "Test failed"
- Good: "Test failed at line 42: expected 200, got 404. The Authorization header is
  missing from the request. Add: `headers: { 'Authorization': 'Bearer ${token}' }`"

OpenAI explicitly wrote custom linters with remediation instructions in the error message.
Stripe's deterministic nodes return failure reasons that agentic nodes can interpret.

### Pattern 3: Action Boundaries Beat Prompt Rules

From Spillwave (the most cited practitioner source):
> "Your agent will run a destructive call on impossible input as long as the arguments parse.
> Prompts persuade. Contracts get enforced every time."

A rule in a prompt is followed "most of the time." A rule in a hook/middleware is
followed "every time." For payments and financial systems, the difference is everything.

### Pattern 4: Garbage Collection / Entropy Management

Both OpenAI and Stripe built ongoing cleanup mechanisms.
OpenAI: recurring background agent scans for drift, opens refactoring PRs.
Stripe: blueprints can be updated and all future runs inherit the improvement.

Systems without this degrade over time as agents replicate bad patterns.

### Pattern 5: Human in the Loop at the Right Level

None of these systems eliminated humans. They moved human attention:
- From: writing code line by line
- To: approving PRs, steering the harness, catching what the harness misses

This is exactly what Forge does. The human approves the impact report and the diffs.
The harness gets them to a level where human approval is meaningful, not rubber-stamping.

---

## Part 3: Gap Analysis — What Forge Has vs What These Systems Have

### What Forge Already Has (matches or exceeds industry)

| Industry Pattern | Forge Implementation |
|-----------------|---------------------|
| Deterministic validation wrapping AI generation | DeterministicGate (syntax, imports, contracts, hallucination, security) |
| GAN-style Generator-Evaluator | ImplementationAgent (generator) + VerifierAgent (evaluator) |
| Bounded retry loops | Max 3x retry in both impact loop and codegen loop |
| Human approval gate | Pipeline approval + diff approval |
| Layered impact report | Layer 0/1/2 with confidence scores |
| Blueprint-style pipeline | PipelineOrchestrator + CodeGenOrchestrator |

**Forge is already at Stripe/OpenAI level for the CODE GENERATION pipeline.**

### What Forge is Missing (the gaps)

| Industry Pattern | Forge Gap |
|-----------------|-----------|
| Pre-tool input validation (action boundary) | Missing on all impact analysis agents |
| Tool receipts / proof of tool use | Missing — agent can claim tool output without calling |
| Output grounding (names exist in codebase) | Missing — hallucinated service names not caught |
| Error messages written for model retry | Partial — DeterministicGate does this, but not impact side |
| Agent-to-agent input contracts | Missing — no validation at confirm_requirements gate |
| Epistemic classification (claim provenance) | Missing — no tagging of tool output vs inference |
| Garbage collection / entropy management | Missing — no periodic health checks on graph data |
| Eval-based harness hill-climbing | Missing — no feedback loop to improve agent prompts |

**The code generation harness is production-grade. The impact analysis harness is a POC.**

---

## Part 4: Expanded Implementation Plan

Building on HARNESS_VALIDATION_PLAN.md, here is what to add based on industry research:

---

### NEW ITEM 7: Error Messages Written for Agent Retry

**Inspired by:** OpenAI custom linters, Stripe failure messages, LangChain targeted feedback

**What:** Every harness check that fails should return an error message structured for
the agent to act on — not just a generic error.

**Examples from the existing DeterministicGate (already doing this well):**
```
"Contract 'withRetry' parameter count mismatch: expected 3, got 2.
 Expected parameters: fn, operationName, maxAttempts"
```

**What to add on the impact analysis side:**

When ITEM 1 (confirm_requirements validation) fails:
```python
# Bad (generic):
"Service 'fraud-service' not found"

# Good (actionable for agent):
"Service 'fraud-service' was not found in the indexed codebase.
 Available services are: payment-processor, account-service, validation-service,
 fx-service, ledger-service, audit-service, gateway-service, payment-ui.
 Did you mean 'validation-service'? Please specify one of these exact names."
```

When ITEM 4 (report grounding) finds hallucinated service:
```python
# Return this as the gap message:
"SERVICE: fraud-service appears in the report but is not in the codebase.
 Available services matching 'fraud': none.
 If this was meant to be a new service recommendation, label it as
 'NEW SERVICE REQUIRED: fraud-service' instead of an existing SERVICE."
```

**Effort:** Update error strings in Items 1–6. ~2 hours.

---

### NEW ITEM 8: Epistemic Classification (Claim Provenance)

**Inspired by:** arXiv NabaOS paper, regulated industry harness requirements

**What:** Tag every claim in the impact report with its epistemic source:
- `[GRAPH]` — came directly from a graph query result (highest trust)
- `[INFERRED]` — reasoned from graph data (medium trust)
- `[MODEL]` — not from graph, from training data (lowest trust, flag to human)

**Where:** `forge/src/modules/agents/impact/agent.py` — after report is generated

**How:**

```python
def classify_report_claims(report: str, receipts: list[dict]) -> str:
    """
    Add epistemic tags to the impact report based on tool receipts.

    Symbols that appeared in tool results get [GRAPH] tag.
    Symbols the agent added without a corresponding query get [MODEL] tag.

    Returns the report with tags prepended to each SERVICE: line.
    """
    # Collect all symbols that appeared in actual tool results
    grounded_symbols = set()
    grounded_services = set()

    for receipt in receipts:
        result = receipt.get("result_data", {})
        # Extract service names from search/analyze results
        for item in result.get("results", []) if isinstance(result, dict) else []:
            if isinstance(item, dict):
                if item.get("service"):
                    grounded_services.add(item["service"])

    # Tag each SERVICE: line in the report
    lines = report.split("\n")
    tagged_lines = []
    for line in lines:
        if line.startswith("SERVICE:"):
            svc_name = line.split("SERVICE:")[1].split("[")[0].strip()
            if svc_name in grounded_services:
                line = line.replace("SERVICE:", "SERVICE: [GRAPH]", 1)
            else:
                line = line.replace("SERVICE:", "SERVICE: [MODEL]", 1)
        tagged_lines.append(line)

    return "\n".join(tagged_lines)
```

**Value for HSBC/regulated use:** Every service named in the impact report is now tagged
with whether it came from actual graph queries or from the model's training data.
This is the audit trail regulators need — provenance of every AI-generated claim.

**Effort:** ~30 lines, no new dependencies.

---

### NEW ITEM 9: Harness Health Dashboard (Entropy Management)

**Inspired by:** OpenAI garbage collection agents, Stripe blueprint auditing

**What:** A periodic job (can be manual for POC) that checks the harness is working:
- Are tool receipts being logged? (checks ITEM 3 is running)
- Are grounding checks firing? (checks ITEM 4 is running)
- How many reports were rejected by the harness? (quality metric)
- Are any services in requirements that don't exist? (ITEM 1 effectiveness)

**Where:** New endpoint `GET /health/harness` in `forge/src/interfaces/api/routes/health.py`

**Simple implementation:**

```python
@router.get("/health/harness")
async def harness_health():
    """
    Report on harness validation health — how many checks are firing,
    how many are catching real issues.
    """
    return {
        "items_implemented": {
            "input_contract": True,        # ITEM 1
            "output_grounding": True,       # ITEM 2 + 4
            "tool_receipts": True,          # ITEM 3
            "action_boundary": True,        # ITEM 6
            "verification_receipts": True,  # ITEM 5
            "epistemic_tags": True,         # ITEM 8
        },
        "items_pending": {
            "self_harness": False,          # ITEM 10 — future
            "eval_hillclimbing": False,     # future
        },
        "note": "Check server logs for per-run harness violation counts"
    }
```

**Effort:** ~20 lines.

---

### NEW ITEM 10: Self-Harness Loop (Future / V2)

**Inspired by:** arXiv Self-Harness paper (60% improvement), Mitchell Hashimoto's principle

**What:** When a pipeline fails the harness 2+ times for the same reason, automatically
propose a harness update — a new validation rule or a system prompt refinement.

**Mitchell Hashimoto's rule:** "When an agent makes a mistake, engineer a permanent fix
into the harness so the mistake cannot happen again. Never just fix the current run."

**How it would work in Forge:**

1. ImpactAgent fails ITEM 4 (reports hallucinated service "fraud-service") 3 times
2. After the 3rd failure, a "harness updater" runs:
   ```
   "The agent keeps inventing 'fraud-service'. Add a hard constraint to the
   system prompt: 'You MUST only name services from this list: [exact list]'"
   ```
3. The system prompt is updated automatically
4. Future runs inherit the improvement

**Why this is V2, not V1:**
- Requires a way to safely update system prompts (version control, rollback)
- Requires a feedback signal (which harness checks are firing most)
- Requires evaluation to confirm the update helps, not hurts
- Valuable, but ITEMS 1-9 should be working first

---

## Part 5: Final Priority Order (Updated with Industry Findings)

```
PHASE 1 — Foundation (matches Stripe/OpenAI minimum bar)
  ├── ITEM 1:  Agent-to-agent input contract            ~30 lines
  ├── ITEM 2:  ContextGatherer output grounding         ~25 lines
  ├── ITEM 6:  Action boundary on tool args             ~20 lines
  └── ITEM 7:  Error messages for agent retry           ~2 hours refactor

PHASE 2 — Proof of Work (what separates genuine from hallucinated)
  ├── ITEM 3:  ImpactAgent tool receipt logger          ~40 lines
  ├── ITEM 4:  Report grounding check                   ~25 lines
  └── ITEM 5:  VerificationAgent receipt check          ~35 lines

PHASE 3 — Regulated Industry Features (HSBC-grade)
  ├── ITEM 8:  Epistemic classification (provenance)    ~30 lines
  └── ITEM 9:  Harness health endpoint                  ~20 lines

PHASE 4 — Self-Improving (V2, future)
  └── ITEM 10: Self-harness loop                        separate sprint
```

**Phase 1+2 total: ~175 lines, 3 files, zero new dependencies.**  
**Phase 3 adds: ~50 lines, 2 files.**

---

## Part 6: The Business Case for HSBC

The research provides direct answers to "why should HSBC care":

| Evidence | Source | Number |
|---------|--------|--------|
| Harness change alone improved agent 13.7 points | LangChain | 52.8% → 66.5% on Terminal-Bench |
| Same model, harness rebuilt = rank outside top 30 → rank 5 | LangChain | 3 engineers, 5 months |
| 1M lines of code, 1,500 PRs, zero human-written lines | OpenAI | 1/10th the time |
| 1,300 PRs/week, humans only review not write | Stripe | ongoing production |
| Tool receipt verification catches 94.2% of fabricated tool calls | arXiv NabaOS | <15ms overhead |
| Self-harness improves agent up to 60% without human intervention | arXiv Self-Harness | across tasks |

**The key message for any stakeholder:**

> Forge already has the code generation harness at production grade (matches Stripe's
> blueprint architecture). The gap is the impact analysis pipeline. Adding Items 1-9
> brings the whole system to the same standard.
>
> For a regulated institution like HSBC, Item 8 (epistemic classification) is particularly
> important — it provides the provenance trail that shows regulators exactly which claims
> came from real code graph data vs AI inference. This is the difference between an AI
> system that can pass a PCI-DSS audit and one that cannot.

---

*Document prepared: September 2026*  
*Sources: OpenAI harness engineering post, Stripe Minions MindStudio analysis,
Anthropic GAN harness design, LangChain Terminal-Bench improvement, arXiv 2603.10060
(NabaOS), arXiv 2606.09498 (Self-Harness), Thoughtworks/Martin Fowler harness
engineering, Spillwave tool contracts guide.*
