# Multi-Agent Code Generation Architectures - Research Summary

## Executive Summary

Based on deep research into academic papers and industry implementations, here are the **proven architectures** for multi-agent code generation with verification loops. This directly applies to Forge's next step: taking impact analysis → generating code changes → verifying → user approval.

---

## Recommended Architecture for Forge

Based on the research, I recommend a **3-Agent Loop with Tool-Augmented Verification**:

```
┌─────────────────────────────────────────────────────────────────────┐
│                         FORGE CODE AGENT SYSTEM                      │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│   ┌──────────────┐     ┌──────────────┐     ┌──────────────┐       │
│   │    PLANNER   │────▶│   CODER      │────▶│   REVIEWER   │       │
│   │    AGENT     │     │   AGENT      │     │    AGENT     │       │
│   └──────────────┘     └──────────────┘     └──────┬───────┘       │
│          │                    ▲                     │               │
│          │                    │                     │               │
│          │              ┌─────┴─────┐               │               │
│          │              │  FEEDBACK │◀──────────────┘               │
│          │              │   LOOP    │                               │
│          │              └───────────┘                               │
│          │                    │                                     │
│          │                    ▼                                     │
│          │             ┌─────────────┐                              │
│          │             │  TOOL EXEC  │ ← Run tests, lint, build     │
│          │             └─────────────┘                              │
│          │                    │                                     │
│          │                    ▼                                     │
│          │            PASS? ──┬── YES ──▶ Generate Diff             │
│          │                    │                                     │
│          │                    NO                                    │
│          │                    │                                     │
│          │                    ▼                                     │
│          │         Max iterations? ──▶ Return best attempt          │
│          └────────────────────────────────────────────────────────▶ │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Key Research Findings

### 1. RGD Framework (arXiv 2410.01242) - **Most Relevant**
**3-Agent Architecture: Guide → Debug → Feedback**

| Agent | Role |
|-------|------|
| **Guide Agent** | Generates implementation plan from requirements. Retrieves similar past solutions from memory pool. |
| **Debug Agent** | Writes actual code based on guide + task description. Incorporates feedback to fix code. |
| **Feedback Agent** | Analyzes failed tests, explains WHY code failed, suggests fixes. Also tracks PASSING tests to prevent regressions. |

**Key Innovation**: Memory pool stores successful (task, guide, keywords) tuples for retrieval. 9.8% improvement on HumanEval.

**Applicable to Forge**: 
- Guide Agent = uses our impact report as context
- Debug Agent = generates code changes
- Feedback Agent = reviews changes against conventions + tests

---

### 2. ReVeal Framework (arXiv 2506.11442) - **Best Verification Loop**
**Iterative Generation-Verification with Tool Feedback**

```
Turn 1: <generation-think> → <generation-answer> → <verification-think> → <verification-answer>
        ↓
        <tool-feedback> (actual execution results)
        ↓
Turn 2: <generation-think> (analyze failures) → <generation-answer> (fixed code) → ...
```

**Key Innovations**:
1. **Self-generated test cases** - Agent creates its own tests, not relying on pre-existing ones
2. **Tool-augmented verification** - Actual code execution, not LLM judgment
3. **Turn-level rewards** - Rewards improvement between iterations, not just final outcome
4. **Dense feedback** - Shows expected vs actual output, not just pass/fail

**Results**: 42.4% Pass@1 on LiveCodeBench (19 turns), up from 36.9% at turn 1.

**Applicable to Forge**:
- Generate code → Generate tests → Execute → Get structured feedback → Iterate

---

### 3. MAGen Framework (Springer 2026) - **5-Role Architecture**
**Coordinator → Planner → Generator → Tester → Synthesizer**

| Role | Responsibility |
|------|----------------|
| **Coordinator** | Orchestrates workflow, routes between agents |
| **Planner** | Breaks down requirements into implementation steps |
| **Generator** | Writes code based on plan |
| **Tester** | Generates test suite, runs tests, reports coverage |
| **Synthesizer** | Combines outputs, resolves conflicts, produces final artifact |

**Key Innovation**: Embeds verification INSIDE the generation loop, not after. Uses static analyzers (Slither, SmartCheck) for additional signals.

---

### 4. SEW Framework (arXiv 2505.18646) - **Self-Evolving Workflows**
**Dynamic Agent Configuration**

Instead of fixed agent topology, SEW:
1. Starts with a template workflow
2. Uses "workflow evolution" to modify structure
3. Uses "agent evolution" to improve each agent's prompts

**Two effective workflows discovered**:
- **Task Parsing Workflow**: Parse → Refine → Generate → Review → Refine
- **Code Rewriting Workflow**: Generate → Review (loop until pass) → Rewrite

**Key Insight**: Higher-order evolution (mutating the mutation prompts) yields more robust results.

---

### 5. MAGE (arXiv 2412.07822) - **High-Temperature Sampling + Checkpoints**
**RTL Code Generation with 95.7% success rate**

**Key Innovations**:
1. **High-temperature candidate sampling** - Generate multiple diverse candidates
2. **Checkpoint verification** - Check intermediate states, not just final output
3. **Targeted feedback** - Pinpoint exact location of errors

---

## Recommended Implementation for Forge

### Phase 1: Core 3-Agent System

```python
class CodeChangeOrchestrator:
    """Orchestrates multi-agent code generation from impact report."""
    
    def __init__(self):
        self.planner = PlannerAgent()      # Creates implementation plan
        self.coder = CoderAgent()          # Generates code changes
        self.reviewer = ReviewerAgent()    # Verifies changes
        self.max_iterations = 3
    
    async def generate_changes(self, impact_report: ImpactReport) -> CodeChanges:
        # Step 1: Plan
        plan = await self.planner.create_plan(impact_report)
        
        # Step 2: Generate + Verify Loop
        for iteration in range(self.max_iterations):
            # Generate code
            changes = await self.coder.generate(plan, feedback=feedback)
            
            # Verify with tools
            verification = await self.reviewer.verify(
                changes=changes,
                plan=plan,
                run_tests=True,
                run_lint=True,
                check_conventions=True
            )
            
            if verification.passed:
                return changes
            
            # Create feedback for next iteration
            feedback = self._create_feedback(verification)
        
        return changes  # Return best attempt
```

### Phase 2: Agent Definitions

#### Planner Agent
```
Role: Transform impact report into actionable implementation steps

Input:
- Impact report (layers, services, functions to modify)
- Codebase context (file contents, conventions)

Output:
- Ordered list of changes to make
- For each change: file, function, what to modify, why
- Dependencies between changes
```

#### Coder Agent
```
Role: Generate actual code changes

Input:
- Implementation plan
- Original file contents
- Previous feedback (if any)

Output:
- Modified code for each file
- Explanation of changes made

Tools Available:
- Read file contents
- Search codebase for patterns
- Look up similar implementations
```

#### Reviewer Agent
```
Role: Verify code changes meet requirements and conventions

Input:
- Generated changes
- Original requirements
- Project conventions

Checks:
1. Syntax valid (parse/compile)
2. Tests pass (if available)
3. Lint passes
4. Follows project conventions
5. Matches original intent

Output:
- PASS/FAIL
- If FAIL: structured feedback with:
  - What failed
  - Why it failed
  - Suggested fix
  - Which passing checks to preserve
```

### Phase 3: Tool Integration

```python
class VerificationTools:
    """External tools for code verification."""
    
    async def run_syntax_check(self, code: str, language: str) -> Result:
        """Parse code to check syntax."""
        pass
    
    async def run_tests(self, test_files: List[str]) -> TestResult:
        """Execute test suite."""
        pass
    
    async def run_linter(self, files: List[str]) -> LintResult:
        """Run ESLint/Pylint/etc."""
        pass
    
    async def check_conventions(self, changes: CodeChanges) -> ConventionResult:
        """Check against project style guide."""
        pass
    
    async def generate_diff(self, original: str, modified: str) -> str:
        """Create unified diff for user review."""
        pass
```

---

## Feedback Loop Design

Based on RGD and ReVeal research, the feedback should be **structured and actionable**:

```json
{
  "iteration": 2,
  "status": "NEEDS_CHANGES",
  "passed_checks": [
    {"check": "syntax", "result": "PASS"},
    {"check": "lint", "result": "PASS", "details": "No errors"}
  ],
  "failed_checks": [
    {
      "check": "test",
      "result": "FAIL",
      "test_name": "test_payment_retry",
      "expected": "should retry 3 times",
      "actual": "retried only once",
      "likely_cause": "retry loop exits after first attempt",
      "suggested_fix": "Check loop condition in processPayment line 42"
    }
  ],
  "regression_warning": [
    "test_payment_success was passing in iteration 1, ensure it still passes"
  ]
}
```

---

## Key Takeaways for Forge Implementation

1. **Don't just use one agent** - Single-agent approaches hit a ceiling. Multi-agent with specialized roles consistently outperforms.

2. **Tool-augmented verification is essential** - LLM self-judgment is unreliable. Actually run the code, tests, linters.

3. **Track what was working** - The Feedback Agent should note which tests PASSED to prevent regressions.

4. **Dense feedback > sparse feedback** - "Test failed" is useless. "Test X failed because Y, expected A got B, fix by doing C" is actionable.

5. **Limit iterations** - 3 iterations is the sweet spot. More iterations have diminishing returns and risk infinite loops.

6. **Memory/retrieval helps** - Storing successful (requirement, plan, solution) tuples helps future similar tasks.

7. **Structured output formats** - Use XML/JSON tags to separate thinking, code, and verification. Makes parsing reliable.

---

## Next Steps for Forge

1. **Design the agent prompts** based on RGD's Guide/Debug/Feedback pattern
2. **Implement verification tools** - syntax check, test runner, linter integration
3. **Build the feedback loop** with structured JSON feedback
4. **Create the diff generation** for user approval UI
5. **Add memory pool** (optional) for learning from successful changes

---

## References

- RGD: Multi-LLM Based Agent Debugger (arXiv 2410.01242)
- ReVeal: Self-Evolving Code Agents via Iterative Generation-Verification (arXiv 2506.11442)  
- MAGen: Multi-agent smart contract generation (Springer 2026)
- SEW: Self-Evolving Agentic Workflows (arXiv 2505.18646)
- MAGE: Multi-Agent Engine for RTL Code Generation (arXiv 2412.07822)
- SWE-agent: Agent-Computer Interfaces (arXiv 2405.15793)

---

## Open Source Implementations to Study

Based on the [awesome-cli-coding-agents](https://github.com/bradAGI/awesome-cli-coding-agents) list (120+ tools), here are the most relevant open-source projects for Forge's code generation system:

### Top Coding Agent Architectures

| Project | Stars | Key Features | GitHub |
|---------|-------|--------------|--------|
| **OpenHands** | 86.4k | Full agentic dev environment, CLI + web | [All-Hands-AI/OpenHands](https://github.com/All-Hands-AI/OpenHands) |
| **Aider** | 48.8k | Pair-programming, git-aware diffs, multi-file | [Aider-AI/aider](https://github.com/Aider-AI/aider) |
| **SWE-agent** | 20.3k | Resolves real GitHub issues, SWE-bench workflows | [SWE-agent/SWE-agent](https://github.com/SWE-agent/SWE-agent) |
| **Plandex** | 15.6k | Plan-first, multi-file, 2M token context | [plandex-ai/plandex](https://github.com/plandex-ai/plandex) |
| **Goose** | 54k | Local, extensible, MCP integration | [aaif-goose/goose](https://github.com/aaif-goose/goose) |
| **Devon** | 3.5k | TUI, autonomous planning/execution/debugging | [entropy-research/Devon](https://github.com/entropy-research/Devon) |
| **AutoCodeRover** | 3.1k | Patches real GitHub issues via code search | [AutoCodeRoverSG/auto-code-rover](https://github.com/AutoCodeRoverSG/auto-code-rover) |
| **RA.Aid** | 2.2k | Research/plan/implement pipeline on LangGraph | [ai-christianson/RA.Aid](https://github.com/ai-christianson/RA.Aid) |

### Multi-Agent Orchestration Tools

| Project | Stars | Key Features |
|---------|-------|--------------|
| **claude-flow** | 71.2k | Multi-agent swarms with coordinated workflows |
| **Orca** | 63.3k | Fleet of parallel agents in git worktrees |
| **DeerFlow** | 81.7k | Long-horizon super-agent with sub-agents, skills, memory |
| **gastown** | 18k | Multi-agent orchestration with persistent work tracking |
| **Claude Squad** | 8.4k | tmux-based harness for multiple Claude sessions |
| **zeroshot** | 1.8k | Planner + implementer + validators in isolated envs |

### Key Patterns from Open Source

1. **Git Worktree Isolation** - Most orchestrators run each agent in its own git worktree
2. **Plan-First Architecture** - Plandex, RA.Aid, Devon all use explicit planning before coding
3. **Verification Loops** - zeroshot, h5i run validators that test/review agent output
4. **Memory/Context Persistence** - Beads, Vestige, pi-mem for cross-session memory
5. **Diff-Based Output** - Aider's patch/diff approach is widely adopted

### Recommended Projects to Study for Forge

1. **Aider** - Best example of diff-based code editing with git integration
   ```bash
   pip install aider-chat
   # Study: aider/coders/*.py for diff generation patterns
   ```

2. **SWE-agent** - Best for understanding issue→code workflows
   ```bash
   # Study: sweagent/agent/ for agent loop design
   ```

3. **RA.Aid** - Clean LangGraph implementation of research→plan→implement
   ```bash
   # Study: ra_aid/agents/ for multi-agent coordination
   ```

4. **zeroshot** - Isolated verification with retry loops
   ```bash
   # Study: How it runs validators independently
   ```
