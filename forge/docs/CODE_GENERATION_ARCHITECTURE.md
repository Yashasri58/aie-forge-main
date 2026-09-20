# Forge Code Generation Architecture

> **The Definitive Guide** — All design decisions, research findings, flaws and fixes documented.
> This is the single source of truth for implementing code generation in Forge.

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Research Findings](#research-findings)
3. [Architecture Overview](#architecture-overview)
4. [LLM Router](#llm-router)
5. [Design Agent (The Brain)](#design-agent-the-brain)
6. [plan.json Schema (The Ultimatum)](#planjson-schema-the-ultimatum)
7. [Implementation Agents (The Hands)](#implementation-agents-the-hands)
8. [Verification System](#verification-system)
9. [User Approval UI](#user-approval-ui)
10. [Flaws and Fixes](#flaws-and-fixes)
11. [Implementation Priority](#implementation-priority)
12. [Appendix: Research Deep Dives](#appendix-research-deep-dives)

---

## Executive Summary

### What We're Building

A multi-agent code generation system that:
1. Takes an impact report (files, services, layers)
2. Creates a detailed execution plan with exact code changes
3. Runs parallel agents to implement changes
4. Verifies correctness
5. Presents diffs for user approval

### Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Architecture | Single Design Agent + Parallel Implementation Agents | Based on Claude Code, Codex, Cursor research |
| Coordination | plan.json as contract | No runtime coordination needed between agents |
| Parallelism | By phase, max 5 concurrent | Avoid rate limits, respect dependencies |
| Verification | Tool-based (lint, test) + LLM review | Tools for objective checks, LLM for semantic |

### What We Rejected

| Rejected Approach | Why |
|-------------------|-----|
| Pure single agent | Too slow for 15+ files |
| Dynamic sub-agent spawning | Coordination overhead, inconsistency |
| Pre-planned DAG orchestrators | Over-engineering, model should decide |
| Separate Planner/Coder agents | One agent with tools is simpler and more consistent |

---

## Research Findings

### How Production Systems Actually Work

We researched Claude Code, OpenAI Codex, Cursor, Aider, and Kiro. Key findings:

#### The Universal Pattern

Every successful system uses the same core loop:

```
while (not done):
    response = llm.call(prompt, tools)
    if response.is_final:
        break
    result = execute_tool(response.tool_call)
    prompt.append(result)
```

**No DAGs. No orchestrators. No separate planners.** Just a while loop with tools.

#### Claude Code Architecture

```
Core loop = while(tool_call)
- No DAGs, no classifiers, no RAG
- The model decides everything
- Sub-agents exist but are READ-ONLY (exploration)
- 4-tier compaction for context management
```

Key insight: **Context engineering > architecture complexity**

#### OpenAI Codex "Collab" System

```
Parent Agent (depth 0)
├── spawn_agent("explore codebase", role="explorer")
├── spawn_agent("implement feature", role="worker")
└── wait(ids=[explorer, worker])
```

Constraints:
- Max depth = 3 (prevents infinite nesting)
- Child agents cannot request user approval
- Children share parent's sandbox

Key insight: **Model decides when to spawn, not a pre-planned DAG**

#### Cursor Multi-Agent

```
Uses git worktrees for isolation:
- Each agent works in separate directory
- No file conflicts possible
- Merge branches at the end
```

Key insight: **Parallelism requires isolation**

#### Aider (Single Agent)

```
User → Aider → LLM → Edit Format → Apply → Git Commit
```

- Repository map (tree-sitter) for context
- Multiple edit formats (whole, diff, udiff)
- Single agent handles everything

Key insight: **One agent with good context beats multiple agents**

### The Consensus

| System | Multi-Agent? | How? |
|--------|--------------|------|
| Claude Code | Sub-agents for read-only exploration | Single main agent |
| Codex | Collab workers | Model decides when to spawn |
| Cursor | Parallel with git worktrees | Filesystem isolation |
| Aider | No | Single agent, good context |
| Kiro | No | Spec-driven single agent |

**Conclusion:** Multi-agent works IF:
1. Each agent has isolated scope (no overlapping files)
2. Shared contracts are defined upfront
3. Coordination is minimal (no runtime negotiation)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              USER REQUEST                                    │
│                     "Add retry logic to all HTTP calls"                     │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           IMPACT AGENT                                       │
│                         (Already Built)                                      │
│                                                                             │
│  Input: Change request + Code Graph                                         │
│  Output: impact_report.json                                                 │
│          ├── Affected files (15 files)                                      │
│          ├── Affected services (5 services)                                 │
│          ├── Dependency layers (Layer 0, 1, 2)                              │
│          └── Change descriptions                                            │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           DESIGN AGENT                                       │
│                          (The Brain)                                         │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ TOOLS AVAILABLE                                                      │   │
│  │ ├── query_code_graph() — symbols, calls, HTTP connections           │   │
│  │ ├── read_file() — read any file                                     │   │
│  │ ├── grep() — search patterns                                        │   │
│  │ └── find_symbol() — locate definitions                              │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  Process:                                                                   │
│  1. Read impact report                                                      │
│  2. Explore codebase (grep for patterns, read key files)                    │
│  3. Design solution (reuse or create, define contracts)                     │
│  4. Create detailed plan                                                    │
│                                                                             │
│  Output: plan.json (THE ULTIMATUM)                                          │
│          ├── Analysis & reasoning                                           │
│          ├── Design decisions                                               │
│          ├── Interface contracts (exact signatures)                         │
│          ├── Execution phases                                               │
│          └── Per-file tasks (exact code changes)                            │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           COORDINATOR                                        │
│                    (Simple Code, Not LLM)                                   │
│                                                                             │
│  1. Validate plan.json                                                      │
│  2. Group tasks by phase                                                    │
│  3. Create task_file.json for each task                                     │
│  4. Manage execution order                                                  │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                       IMPLEMENTATION AGENTS                                  │
│                          (The Hands)                                         │
│                                                                             │
│  Phase 1: Create new files (sequential if dependencies)                     │
│  ┌─────────┐                                                                │
│  │ Agent 1 │ → Creates payment-processor/src/utils/retry.js                 │
│  └─────────┘                                                                │
│       │                                                                     │
│       ▼ WAIT                                                                │
│                                                                             │
│  Phase 2: Modify existing files (parallel, max 5 concurrent)                │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐          │
│  │ Agent 2 │  │ Agent 3 │  │ Agent 4 │  │ Agent 5 │  │ Agent 6 │          │
│  │ gateway │  │ account │  │ ledger  │  │ validat │  │ notific │          │
│  └─────────┘  └─────────┘  └─────────┘  └─────────┘  └─────────┘          │
│       │            │            │            │            │                 │
│       └────────────┴────────────┴────────────┴────────────┘                 │
│                                    │                                        │
│                                    ▼                                        │
│                             All Diffs[]                                     │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           VERIFICATION                                       │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ TOOL-BASED (Objective)                                               │   │
│  │ ├── Apply diffs to temp directory                                    │   │
│  │ ├── Run linter → collect errors                                      │   │
│  │ └── Run tests → collect failures                                     │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ LLM-BASED (Semantic)                                                 │   │
│  │ └── Verification Agent checks contract compliance                    │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  If FAIL → Feedback to specific agent → Retry (max 3x)                      │
│  If PASS → Proceed to approval                                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          USER APPROVAL                                       │
│                                                                             │
│  Display:                                                                   │
│  ├── Plan summary (what and why)                                            │
│  ├── All diffs (expandable per file)                                        │
│  └── Verification results                                                   │
│                                                                             │
│  Actions: [Approve All] [Reject All] [Edit Plan] [Edit Diff]                │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## LLM Router

**Automatic model selection at runtime using LiteLLM's Complexity Router.**

Unlike manual model selection, LiteLLM analyzes each request and automatically picks the right model based on:
- Token count and message length
- Code presence and technical terms
- Reasoning markers ("step by step", "analyze", etc.)
- Custom keyword rules

### Model Tiers

| Tier | Model | Triggers |
|------|-------|----------|
| **SIMPLE** | `gemini-2.5-flash-lite` | Greetings, short questions, simple tasks |
| **MEDIUM** | `gemini-2.5-flash` | Standard implementation, code changes |
| **COMPLEX** | `gemini-2.5-flash` | Debugging, multi-file, integration |
| **REASONING** | `gemini-2.5-pro` | Architecture, design, planning, analysis |

### How It Works

```python
from modules.codegen import ForgeRouter

router = ForgeRouter.get_instance()

# LiteLLM automatically picks the model!
response = await router.complete(messages=[
    {"role": "user", "content": "Design an authentication system with OAuth2"}
])
# → Detects "design" + "authentication" + "OAuth2" → REASONING → gemini-2.5-pro

response = await router.complete(messages=[
    {"role": "user", "content": "Fix this typo in the config"}  
])
# → Short message, simple task → SIMPLE → gemini-2.5-flash-lite
```

### LiteLLM Classification Signals

| Signal | What it detects | Weight |
|--------|-----------------|--------|
| `tokenCount` | Short (<15) or long (>400) prompts | 0.10 |
| `codePresence` | "function", "class", "api", "database" | 0.30 |
| `reasoningMarkers` | "step by step", "think through", "analyze" | 0.25 |
| `technicalTerms` | "architecture", "distributed", "encryption" | 0.25 |
| `simpleIndicators` | "what is", "define", greetings | 0.05 |
| `multiStepPatterns` | "first...then", numbered steps | 0.03 |
| `questionComplexity` | Multiple question marks | 0.02 |

### Keyword Escalation Rules

```yaml
keyword_tier_rules:
  # Simple tasks
  - keywords: ["hi", "hello", "thanks", "ok"]
    tier: SIMPLE
    
  # Reasoning tasks (highest priority)
  - keywords: ["architecture", "design", "plan", "strategy", "analyze"]
    tier: REASONING
    
  # Complex tasks
  - keywords: ["debug", "fix", "error", "multiple files", "integration"]
    tier: COMPLEX
```

When multiple rules match, LiteLLM escalates to the **highest tier** (SIMPLE < MEDIUM < COMPLEX < REASONING).

### For ADK Agents (Static Model Selection)

ADK agents need a model string at creation time. Use these helpers:

```python
from modules.codegen import select_model, get_model_for_agent

# By agent type
model = get_model_for_agent("design")  # → "gemini-2.5-pro"
model = get_model_for_agent("implementation")  # → "gemini-2.5-flash"

# By task type  
model = select_model(task_type="architecture")  # → "gemini-2.5-pro"
model = select_model(tier=ModelTier.SIMPLE)  # → "gemini-2.5-flash-lite"
```

### Session Affinity

Enabled by default. Once a conversation starts with a model, subsequent turns stay on that model to:
1. Preserve provider-side prompt caches
2. Avoid issues when replaying conversation history across different models

```python
# Turn 1: "Design an auth system" → gemini-2.5-pro
# Turn 2: "Thanks!" → Still gemini-2.5-pro (pinned)
```

### Installation

LiteLLM is optional. Without it, the router falls back to simple heuristic matching.

```bash
pip install "litellm>=1.94"  # For auto routing
```

---

## Design Agent (The Brain)

The Design Agent is the most critical component. It has full access to the codebase and produces the complete execution plan.

### Tools Available

```typescript
interface DesignAgentTools {
  /**
   * Query the code graph for symbols, calls, and connections
   */
  query_code_graph(query: {
    type: "symbols" | "calls" | "callers" | "http_connections" | "dependents";
    filter?: {
      service?: string;
      file?: string;
      symbol?: string;
    };
  }): GraphQueryResult;
  
  /**
   * Read any file in the codebase
   */
  read_file(path: string): string;
  
  /**
   * Search for patterns across the codebase
   */
  grep(pattern: string, options?: {
    file_glob?: string;
    max_results?: number;
    include_context?: boolean;
  }): GrepResult[];
  
  /**
   * Find where a symbol is defined
   */
  find_symbol(name: string): {
    file: string;
    line: number;
    definition: string;
  }[];
  
  /**
   * Get the impact report (already generated)
   */
  get_impact_report(): ImpactReport;
}
```

### Design Agent System Prompt

```markdown
You are the Design Agent for Forge Code Generation.

## YOUR MISSION
Create a complete, unambiguous plan.json that implementation agents can follow 
WITHOUT any additional context or decision-making.

## AVAILABLE TOOLS
- query_code_graph: Query the code graph for symbols, calls, HTTP connections
- read_file: Read any file in the codebase
- grep: Search for patterns across the codebase
- find_symbol: Find where a symbol is defined
- get_impact_report: Get the impact analysis

## PROCESS

### Step 1: UNDERSTAND
- Read the change request carefully
- Review the impact report (files, services, layers)
- Identify what type of change this is (add feature, refactor, fix bug)

### Step 2: EXPLORE
- Use query_code_graph to understand relationships between affected files
- Use grep to find existing patterns (e.g., existing retry logic, error handling)
- Read key files to understand coding conventions and style
- Check if similar functionality already exists

### Step 3: DESIGN
- Decide: reuse existing patterns or create new?
- Define ALL interfaces/contracts that will be shared between files
- For NEW code: provide COMPLETE implementation
- For MODIFIED code: specify exact locations and changes
- Determine execution order (what must happen first?)

### Step 4: PLAN
- Create detailed plan.json with:
  - EXACT code for every change
  - EXACT location (file, function, line range)
  - EXACT signatures for all shared interfaces
  - CLEAR execution phases and dependencies

## OUTPUT REQUIREMENTS

The plan must be so detailed that:
1. A junior developer with NO context could execute it perfectly
2. An AI agent with NO codebase access could implement it correctly
3. Every interface is defined once and used consistently
4. Nothing is left to interpretation

Return valid JSON matching the Plan schema.
```

### Design Agent Process Flow

```
                     ┌─────────────────────────────┐
                     │     DESIGN AGENT LOOP       │
                     └─────────────────────────────┘
                                  │
                                  ▼
                     ┌─────────────────────────────┐
                     │  1. Get Impact Report       │
                     │     get_impact_report()     │
                     └─────────────────────────────┘
                                  │
                                  ▼
                     ┌─────────────────────────────┐
                     │  2. Explore Existing Code   │
                     │     grep("retry|backoff")   │
                     │     grep("error.*handling") │
                     │     read_file(layer_0_files)│
                     └─────────────────────────────┘
                                  │
                                  ▼
                     ┌─────────────────────────────┐
                     │  3. Query Code Graph        │
                     │     query_code_graph({      │
                     │       type: "calls",        │
                     │       filter: {service: x}  │
                     │     })                      │
                     └─────────────────────────────┘
                                  │
                                  ▼
                     ┌─────────────────────────────┐
                     │  4. Design Contracts        │
                     │     - Function signatures   │
                     │     - Type definitions      │
                     │     - Full implementations  │
                     └─────────────────────────────┘
                                  │
                                  ▼
                     ┌─────────────────────────────┐
                     │  5. Create Execution Plan   │
                     │     - Group by phase        │
                     │     - Define dependencies   │
                     │     - Specify exact changes │
                     └─────────────────────────────┘
                                  │
                                  ▼
                     ┌─────────────────────────────┐
                     │  6. Output plan.json        │
                     └─────────────────────────────┘
```

---

## plan.json Schema (The Ultimatum)

This is the complete contract that all agents follow.

```typescript
/**
 * The complete execution plan for code generation.
 * Contains everything: what, where, why, how, when.
 */
interface Plan {
  // ═══════════════════════════════════════════════════════════════════════════
  // METADATA
  // ═══════════════════════════════════════════════════════════════════════════
  
  /** Unique plan identifier */
  id: string;
  
  /** When the plan was created */
  created_at: string;
  
  /** Original user request */
  change_request: string;
  
  /** Plan format version */
  version: "1.0";
  
  // ═══════════════════════════════════════════════════════════════════════════
  // WHY — Analysis & Reasoning
  // ═══════════════════════════════════════════════════════════════════════════
  
  analysis: {
    /** One-line summary of the change */
    summary: string;
    
    /** Detailed reasoning for the chosen approach */
    reasoning: string;
    
    /** Existing patterns found in the codebase */
    existing_patterns: {
      /** Description of the pattern */
      pattern: string;
      /** Where it was found */
      location: string;
      /** Whether to reuse it */
      reuse: boolean;
      /** Why reuse or not */
      rationale: string;
    }[];
    
    /** Potential risks identified */
    risks: string[];
    
    /** Assumptions made */
    assumptions: string[];
  };
  
  // ═══════════════════════════════════════════════════════════════════════════
  // WHAT — Design Decisions (Global Rules)
  // ═══════════════════════════════════════════════════════════════════════════
  
  design: {
    /** Key design decisions that apply to all files */
    decisions: {
      /** The decision */
      decision: string;
      /** Why this decision was made */
      rationale: string;
    }[];
    
    /** Coding conventions to follow */
    conventions: {
      /** Naming convention */
      naming: string;
      /** Error handling approach */
      error_handling: string;
      /** Logging approach */
      logging: string;
      /** Any other conventions */
      other?: string[];
    };
  };
  
  // ═══════════════════════════════════════════════════════════════════════════
  // HOW — Interface Contracts (The Shared Truth)
  // ═══════════════════════════════════════════════════════════════════════════
  
  contracts: {
    [contract_name: string]: {
      /** Contract identifier (matches key) */
      name: string;
      
      /** Type of contract */
      type: "function" | "class" | "type" | "interface" | "constant";
      
      /** File where this is defined */
      defined_in: string;
      
      /** Whether this is new or existing */
      is_new: boolean;
      
      /** Full TypeScript/JSDoc signature */
      signature: string;
      
      /** For new contracts: complete implementation */
      implementation?: string;
      
      /** Working usage example */
      usage_example: string;
      
      /** Files that use this contract */
      used_by: string[];
      
      /** Additional notes for implementers */
      notes?: string;
    };
  };
  
  // ═══════════════════════════════════════════════════════════════════════════
  // WHEN — Execution Order
  // ═══════════════════════════════════════════════════════════════════════════
  
  execution: {
    /** Execution phases in order */
    phases: {
      /** Phase number (0-indexed) */
      phase: number;
      
      /** Human-readable description */
      description: string;
      
      /** Task IDs in this phase */
      tasks: string[];
      
      /** Can tasks in this phase run in parallel? */
      parallel: boolean;
      
      /** Must this phase complete before next phase starts? */
      wait_for_completion: boolean;
    }[];
  };
  
  // ═══════════════════════════════════════════════════════════════════════════
  // WHAT (Detailed) — Per-File Tasks
  // ═══════════════════════════════════════════════════════════════════════════
  
  tasks: {
    [task_id: string]: {
      /** Task identifier (matches key) */
      id: string;
      
      /** Which phase this task belongs to */
      phase: number;
      
      // ─────────────────────────────────────────────────────────────────────
      // WHERE
      // ─────────────────────────────────────────────────────────────────────
      
      /** File to modify */
      file: string;
      
      /** Service this file belongs to */
      service: string;
      
      /** Programming language */
      language: "javascript" | "typescript" | "python" | "java" | "go" | "rust";
      
      /** Action to perform */
      action: "create" | "modify" | "delete";
      
      // ─────────────────────────────────────────────────────────────────────
      // WHAT (Exact Changes)
      // ─────────────────────────────────────────────────────────────────────
      
      /** Human-readable description */
      description: string;
      
      /** Detailed changes */
      changes: {
        /** Location in the file */
        location: {
          /** Type of location */
          type: "function" | "class" | "method" | "line_range" | "import_section" | "file_start" | "file_end";
          /** Target (function name, class name, or line numbers) */
          target: string;
        };
        
        /** Type of change */
        change_type: "add" | "modify" | "delete" | "wrap" | "replace";
        
        /** What this change does */
        description: string;
        
        /** Current code (for modify/delete/wrap) */
        before?: string;
        
        /** New code (for add/modify/wrap/replace) */
        after: string;
      }[];
      
      // ─────────────────────────────────────────────────────────────────────
      // DEPENDENCIES
      // ─────────────────────────────────────────────────────────────────────
      
      /** Tasks that must complete before this one */
      depends_on: string[];
      
      /** Contracts this task uses */
      uses_contracts: string[];
      
      /** Contracts this task defines */
      defines_contracts: string[];
      
      // ─────────────────────────────────────────────────────────────────────
      // CONTEXT
      // ─────────────────────────────────────────────────────────────────────
      
      context: {
        /** Files to read for context (not modify) */
        read_files: string[];
        
        /** Relevant symbols from code graph */
        relevant_symbols: string[];
        
        /** Additional notes for the implementation agent */
        notes?: string;
      };
      
      // ─────────────────────────────────────────────────────────────────────
      // VALIDATION
      // ─────────────────────────────────────────────────────────────────────
      
      validation: {
        /** Must the result compile/parse without errors? */
        must_compile: boolean;
        
        /** Must the result pass linting? */
        must_pass_lint: boolean;
        
        /** Specific test files to run */
        test_files?: string[];
      };
    };
  };
}
```

### Example plan.json

```json
{
  "id": "plan-retry-logic-20260910",
  "created_at": "2026-09-10T11:00:00Z",
  "change_request": "Add retry logic with exponential backoff to all HTTP calls",
  "version": "1.0",
  
  "analysis": {
    "summary": "Adding retry logic to handle transient HTTP failures across 5 services",
    "reasoning": "The codebase currently has no retry logic. HTTP calls fail immediately on network errors or 5xx responses. We will create a shared utility in payment-processor (Layer 0) and use it in all other services.",
    "existing_patterns": [
      {
        "pattern": "async/await for HTTP calls",
        "location": "All services use async/await with fetch or axios",
        "reuse": true,
        "rationale": "Wrap existing pattern, don't replace"
      }
    ],
    "risks": [
      "Retry loops could cause thundering herd if many services retry simultaneously",
      "Need to ensure idempotency of retried operations"
    ],
    "assumptions": [
      "All HTTP calls are safe to retry (GET) or idempotent (POST with idempotency keys)",
      "Services can tolerate additional latency from retries"
    ]
  },
  
  "design": {
    "decisions": [
      {
        "decision": "Use exponential backoff with jitter",
        "rationale": "Industry standard, prevents thundering herd"
      },
      {
        "decision": "Max 3 retries with base delay of 1000ms",
        "rationale": "Balances reliability with latency"
      },
      {
        "decision": "Retry only on 5xx errors and network failures",
        "rationale": "4xx errors are client errors, should not retry"
      }
    ],
    "conventions": {
      "naming": "camelCase for functions, PascalCase for types",
      "error_handling": "Throw original error after max retries exhausted",
      "logging": "Use existing logger.warn() for retry attempts"
    }
  },
  
  "contracts": {
    "retryWithBackoff": {
      "name": "retryWithBackoff",
      "type": "function",
      "defined_in": "payment-processor/src/utils/retry.js",
      "is_new": true,
      "signature": "async function retryWithBackoff<T>(fn: () => Promise<T>, options?: RetryOptions): Promise<T>",
      "implementation": "const DEFAULT_OPTIONS = {\n  maxRetries: 3,\n  baseDelay: 1000,\n  maxDelay: 10000,\n  shouldRetry: (error) => {\n    if (error.response) {\n      return error.response.status >= 500;\n    }\n    return error.code === 'ECONNRESET' || error.code === 'ETIMEDOUT';\n  }\n};\n\nasync function retryWithBackoff(fn, options = {}) {\n  const opts = { ...DEFAULT_OPTIONS, ...options };\n  let lastError;\n  \n  for (let attempt = 0; attempt <= opts.maxRetries; attempt++) {\n    try {\n      return await fn();\n    } catch (error) {\n      lastError = error;\n      \n      if (attempt === opts.maxRetries || !opts.shouldRetry(error)) {\n        throw error;\n      }\n      \n      const delay = Math.min(\n        opts.baseDelay * Math.pow(2, attempt) + Math.random() * 1000,\n        opts.maxDelay\n      );\n      \n      logger.warn(`Retry attempt ${attempt + 1}/${opts.maxRetries} after ${delay}ms`, { error: error.message });\n      await new Promise(resolve => setTimeout(resolve, delay));\n    }\n  }\n  \n  throw lastError;\n}\n\nmodule.exports = { retryWithBackoff };",
      "usage_example": "const { retryWithBackoff } = require('payment-processor/utils/retry');\n\nconst result = await retryWithBackoff(\n  () => fetch('https://api.example.com/data'),\n  { maxRetries: 3, baseDelay: 1000 }\n);",
      "used_by": [
        "gateway-service/src/client.js",
        "account-service/src/api.js",
        "ledger-service/src/writer.js",
        "validation-service/src/checker.js"
      ]
    },
    "RetryOptions": {
      "name": "RetryOptions",
      "type": "type",
      "defined_in": "payment-processor/src/utils/retry.js",
      "is_new": true,
      "signature": "interface RetryOptions {\n  maxRetries?: number;\n  baseDelay?: number;\n  maxDelay?: number;\n  shouldRetry?: (error: Error) => boolean;\n}",
      "usage_example": "// Options are optional, defaults are provided",
      "used_by": []
    }
  },
  
  "execution": {
    "phases": [
      {
        "phase": 0,
        "description": "Create retry utility",
        "tasks": ["task-create-retry-util"],
        "parallel": false,
        "wait_for_completion": true
      },
      {
        "phase": 1,
        "description": "Add retry logic to all services",
        "tasks": [
          "task-gateway-client",
          "task-account-api",
          "task-ledger-writer",
          "task-validation-checker"
        ],
        "parallel": true,
        "wait_for_completion": true
      }
    ]
  },
  
  "tasks": {
    "task-create-retry-util": {
      "id": "task-create-retry-util",
      "phase": 0,
      "file": "payment-processor/src/utils/retry.js",
      "service": "payment-processor",
      "language": "javascript",
      "action": "create",
      "description": "Create the retry utility with exponential backoff",
      "changes": [
        {
          "location": {
            "type": "file_start",
            "target": "entire file"
          },
          "change_type": "add",
          "description": "Create new retry utility file",
          "after": "// See contracts.retryWithBackoff.implementation"
        }
      ],
      "depends_on": [],
      "uses_contracts": [],
      "defines_contracts": ["retryWithBackoff", "RetryOptions"],
      "context": {
        "read_files": ["payment-processor/src/utils/logger.js"],
        "relevant_symbols": ["logger"]
      },
      "validation": {
        "must_compile": true,
        "must_pass_lint": true
      }
    },
    "task-gateway-client": {
      "id": "task-gateway-client",
      "phase": 1,
      "file": "gateway-service/src/client.js",
      "service": "gateway-service",
      "language": "javascript",
      "action": "modify",
      "description": "Add retry logic to payment gateway HTTP calls",
      "changes": [
        {
          "location": {
            "type": "import_section",
            "target": "top of file"
          },
          "change_type": "add",
          "description": "Add import for retry utility",
          "after": "const { retryWithBackoff } = require('payment-processor/utils/retry');"
        },
        {
          "location": {
            "type": "function",
            "target": "fetchPaymentStatus"
          },
          "change_type": "wrap",
          "description": "Wrap fetch call with retry logic",
          "before": "const response = await fetch(`${API_URL}/payments/${paymentId}`);",
          "after": "const response = await retryWithBackoff(\n  () => fetch(`${API_URL}/payments/${paymentId}`),\n  { maxRetries: 3 }\n);"
        }
      ],
      "depends_on": ["task-create-retry-util"],
      "uses_contracts": ["retryWithBackoff"],
      "defines_contracts": [],
      "context": {
        "read_files": [],
        "relevant_symbols": ["fetchPaymentStatus", "API_URL"]
      },
      "validation": {
        "must_compile": true,
        "must_pass_lint": true,
        "test_files": ["gateway-service/tests/client.test.js"]
      }
    }
  }
}
```

---

## Implementation Agents (The Hands)

Implementation agents are simple: they receive a task and produce a diff.

### Task File (Per-Agent Input)

```typescript
/**
 * Input for a single implementation agent.
 * Derived from plan.json by the Coordinator.
 */
interface TaskFile {
  /** Task identifier */
  task_id: string;
  
  /** File to modify */
  file: string;
  
  /** Programming language */
  language: string;
  
  /** Action: create, modify, delete */
  action: "create" | "modify" | "delete";
  
  /** Current file content (for modify/delete) */
  current_content?: string;
  
  /** What to change */
  changes: TaskChange[];
  
  /** ALL interface contracts (same for all agents) */
  contracts: {
    [name: string]: {
      signature: string;
      implementation?: string;
      usage_example: string;
    };
  };
  
  /** Read-only context files */
  context_files?: {
    [path: string]: string;
  };
  
  /** Design decisions to follow */
  design_decisions: string[];
  
  /** Coding conventions */
  conventions: {
    naming: string;
    error_handling: string;
    logging: string;
  };
  
  /** Output format */
  output_format: "unified_diff";
}
```

### Implementation Agent System Prompt

```markdown
You are an Implementation Agent for Forge Code Generation.

## YOUR MISSION
Implement the code changes specified in your task file and output a unified diff.

## RULES
1. Follow the contracts EXACTLY — use the exact signatures and patterns provided
2. Make ONLY the changes specified in the task
3. Follow the design decisions and conventions
4. Preserve existing code style and formatting
5. Do not add anything not specified in the task

## INPUT
You will receive:
- task_id: Identifier for this task
- file: The file to modify
- current_content: Current file content (if modifying)
- changes: Exact changes to make
- contracts: Interface contracts to use (FOLLOW EXACTLY)
- design_decisions: Rules to follow
- conventions: Coding style to match

## OUTPUT FORMAT
Return a unified diff:

```diff
--- a/{file}
+++ b/{file}
@@ -start,count +start,count @@
 context line
-removed line
+added line
 context line
```

## IMPORTANT
- The contracts contain exact signatures — use them verbatim
- The changes specify exact code — implement it exactly
- Do not improvise or add "improvements"
- If something is unclear, implement the simplest interpretation
```

### Agent Output

```typescript
interface AgentOutput {
  /** Task identifier */
  task_id: string;
  
  /** File that was modified */
  file: string;
  
  /** Unified diff */
  diff: string;
  
  /** Status */
  status: "success" | "error";
  
  /** Error message if failed */
  error_message?: string;
  
  /** Token usage for cost tracking */
  usage?: {
    input_tokens: number;
    output_tokens: number;
  };
}
```

---

## Verification System

Verification happens in two stages: tool-based (objective) and LLM-based (semantic).

### Tool-Based Verification

```typescript
interface ToolVerification {
  /**
   * Apply all diffs to a temporary directory
   */
  applyDiffs(diffs: Diff[], baseDir: string): Promise<{
    success: boolean;
    tempDir: string;
    errors?: string[];
  }>;
  
  /**
   * Run linter on modified files
   */
  runLinter(tempDir: string, files: string[]): Promise<{
    passed: boolean;
    errors: LintError[];
  }>;
  
  /**
   * Run tests
   */
  runTests(tempDir: string, testFiles?: string[]): Promise<{
    passed: boolean;
    failures: TestFailure[];
  }>;
}
```

### LLM-Based Verification (Verification Agent)

```markdown
You are a Verification Agent for Forge Code Generation.

## YOUR MISSION
Review the generated diffs and verify they correctly implement the plan.

## INPUT
- plan.json: The original plan with contracts and requirements
- diffs: All generated diffs

## CHECKS
1. CONTRACT COMPLIANCE
   - Do all files use the contracts with correct signatures?
   - Are imports correct?
   
2. CONSISTENCY
   - Are design decisions followed in all files?
   - Is error handling consistent?
   - Is naming consistent?

3. COMPLETENESS
   - Are all specified changes implemented?
   - Is anything missing?

4. CORRECTNESS
   - Any obvious bugs?
   - Any syntax errors?
   - Any logic errors?

## OUTPUT
Return JSON:
{
  "passed": boolean,
  "issues": [
    {
      "file": "path/to/file",
      "severity": "error" | "warning",
      "issue": "Description of the problem",
      "suggestion": "How to fix it"
    }
  ]
}
```

### Retry Flow

```
Verification Failed
        │
        ▼
┌───────────────────────────────────────┐
│ For each failed task:                 │
│                                       │
│ 1. Get the specific error/issue       │
│ 2. Create feedback for that agent     │
│ 3. Re-run ONLY that agent with:       │
│    - Original task                    │
│    - Previous diff attempt            │
│    - Error feedback                   │
│                                       │
│ Max 3 retries per task                │
└───────────────────────────────────────┘
        │
        ▼
Still failing after 3 retries?
        │
        ├── YES → Mark as "needs human review"
        │         Include in approval UI with warning
        │
        └── NO → Continue to approval
```

---

## User Approval UI

### Approval Page Layout

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  FORGE — Code Changes Ready for Review                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ SUMMARY                                                              │   │
│  │                                                                      │   │
│  │ Request: "Add retry logic with exponential backoff to all HTTP calls"│   │
│  │                                                                      │   │
│  │ Changes: 5 files across 5 services                                   │   │
│  │ Additions: +127 lines                                                │   │
│  │ Deletions: -12 lines                                                 │   │
│  │                                                                      │   │
│  │ ✅ Verification: All checks passed                                   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ DESIGN DECISIONS                                                     │   │
│  │                                                                      │   │
│  │ • Use exponential backoff with jitter                                │   │
│  │ • Max 3 retries with base delay of 1000ms                            │   │
│  │ • Retry only on 5xx errors and network failures                      │   │
│  │                                                                      │   │
│  │ [View Full Plan]                                                     │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ FILES CHANGED                                                        │   │
│  │                                                                      │   │
│  │ ▼ payment-processor/src/utils/retry.js [NEW] (+45)                   │   │
│  │   ┌─────────────────────────────────────────────────────────────┐   │   │
│  │   │ + const DEFAULT_OPTIONS = {                                  │   │   │
│  │   │ +   maxRetries: 3,                                           │   │   │
│  │   │ +   baseDelay: 1000,                                         │   │   │
│  │   │ +   ...                                                      │   │   │
│  │   └─────────────────────────────────────────────────────────────┘   │   │
│  │                                                                      │   │
│  │ ▶ gateway-service/src/client.js (+15, -3)                            │   │
│  │ ▶ account-service/src/api.js (+18, -2)                               │   │
│  │ ▶ ledger-service/src/writer.js (+12, -4)                             │   │
│  │ ▶ validation-service/src/checker.js (+10, -3)                        │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                                                                      │   │
│  │  [✅ Approve All]    [❌ Reject All]    [✏️ Edit Plan]              │   │
│  │                                                                      │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Actions

| Action | Behavior |
|--------|----------|
| **Approve All** | Apply all diffs to the codebase |
| **Reject All** | Discard all changes, return to chat |
| **Edit Plan** | Go back to plan.json, allow modifications, re-run |
| **Edit Diff** | Manually edit individual diffs before applying |

---

## Flaws and Fixes

During architecture design, we identified potential flaws and their fixes:

### Flaw 1: Design Agent Can't Design What It Hasn't Seen

**Problem:** Design Agent receives impact report but hasn't read the actual code.

**Fix:** Give Design Agent tools to read code:
- `read_file()` — read any file
- `grep()` — search for patterns
- `query_code_graph()` — understand relationships

**Status:** ✅ Addressed in architecture

### Flaw 2: Interface Contract Location Problem (Race Condition)

**Problem:** Agent 1 creates `retry.js`, Agents 2-5 import from it. But they run in parallel.

**Fix:** Execution phases with dependencies:
- Phase 0: Create new files (wait for completion)
- Phase 1+: Modify existing files (can parallelize)

**Status:** ✅ Addressed in `execution.phases` schema

### Flaw 3: Context Files May Be Stale

**Problem:** Agent 3 has old version of file that Agent 1 modified.

**Fix:** 
- Interface contracts are the source of truth, not context files
- Don't include files being modified by other agents in context_files
- Context files are only for understanding existing patterns

**Status:** ✅ Addressed in task distribution logic

### Flaw 4: Verification Agent Can't Run Tests

**Problem:** LLM cannot execute code.

**Fix:** Two-stage verification:
1. Tool-based: Apply diffs, run linter, run tests (actual execution)
2. LLM-based: Semantic review for contract compliance (only if tools pass)

**Status:** ✅ Addressed in Verification System section

### Flaw 5: Circular Dependencies Between Files

**Problem:** File A defines function, File B adds parameter, File A needs to accept it.

**Fix:** 
- Impact report should detect circular dependencies
- If detected, fall back to sequential single-agent approach
- For typical "add feature X" tasks, this won't occur

**Status:** ✅ Added detection in Coordinator

### Flaw 6: Diff Merge Conflicts

**Problem:** Two agents accidentally modify the same file.

**Fix:** Validation in task distribution:
```python
def validate_plan(plan):
    files = [task.file for task in plan.tasks]
    if len(files) != len(set(files)):
        raise Error("Duplicate file assignment!")
```

**Status:** ✅ One file = one agent, enforced by Coordinator

### Flaw 7: LLM Output Inconsistency

**Problem:** Design Agent specifies TypeScript, Implementation Agent outputs JavaScript.

**Fix:**
- Explicit `language` field in every task
- Verification checks language consistency
- Contracts include full signatures with types

**Status:** ✅ Addressed in TaskFile schema

### Flaw 8: Cost and Rate Limits

**Problem:** 15 parallel agents = 15 simultaneous LLM calls, may hit rate limits.

**Fix:** Concurrency pool:
```python
MAX_CONCURRENT_AGENTS = 5

async def run_agents(tasks):
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_AGENTS)
    async def run_with_limit(task):
        async with semaphore:
            return await run_agent(task)
    return await asyncio.gather(*[run_with_limit(t) for t in tasks])
```

**Status:** ✅ Configurable concurrency limit

---

## Implementation Priority

### Phase 1: Core (Week 1)

| Order | Component | Effort | Description |
|-------|-----------|--------|-------------|
| 1.1 | plan.json Schema | 2h | TypeScript interfaces, JSON schema validation |
| 1.2 | Design Agent | 8h | Agent with tools, prompt engineering |
| 1.3 | Coordinator | 4h | Plan validation, task distribution |
| 1.4 | Implementation Agent | 4h | Single agent that produces diffs |

**Deliverable:** Can generate plan.json and diffs (no UI, CLI only)

### Phase 2: Execution (Week 2)

| Order | Component | Effort | Description |
|-------|-----------|--------|-------------|
| 2.1 | Parallel Execution | 4h | Phase-based execution with concurrency |
| 2.2 | Tool Verification | 4h | Apply diffs, run linter |
| 2.3 | LLM Verification | 4h | Verification Agent |
| 2.4 | Retry Logic | 4h | Per-task retry with feedback |

**Deliverable:** End-to-end generation with verification

### Phase 3: UI (Week 3)

| Order | Component | Effort | Description |
|-------|-----------|--------|-------------|
| 3.1 | Approval Page | 8h | Diff viewer, summary, actions |
| 3.2 | Plan Viewer | 4h | View/edit plan.json |
| 3.3 | Integration | 4h | Connect to existing Forge UI flow |

**Deliverable:** Full user-facing feature

### Total Estimate

| Phase | Effort |
|-------|--------|
| Phase 1: Core | 18 hours |
| Phase 2: Execution | 16 hours |
| Phase 3: UI | 16 hours |
| **Total** | **50 hours (~2 weeks)** |

---

## Appendix: Research Deep Dives

### A. Claude Code Architecture

Source: [GitHub Gist Analysis](https://gist.github.com/yanchuk/0c47dd351c2805236e44ec3935e9095d)

Key findings:
- Simple while loop: `while(tool_call) { execute(); }`
- No DAGs, no classifiers, no RAG
- Model decides everything
- 4-tier compaction for context management
- Sub-agents exist but are primarily read-only

### B. OpenAI Codex "Collab" System

Source: [OpenAI Blog](https://openai.com/index/unrolling-the-codex-agent-loop/), [GitHub Gist](https://gist.github.com/serialx/f842f7b41d0f74ff5f64845e4afbc260)

Key findings:
- 5 tools: spawn_agent, send_input, wait, resume_agent, close_agent
- Max depth = 3
- Built-in roles: default, explorer, worker, awaiter
- Children cannot request user approval
- Completion notifications via injected messages

### C. Cursor Architecture

Source: [Medium Article](https://medium.com/@khayyam.h/designing-high-performance-agentic-systems-an-architectural-case-study-of-the-cursor-agent-ab624e4a0a64)

Key findings:
- ReAct loop: observe → reason → act → verify
- Git worktrees for parallel agent isolation
- Merkle trees for instant codebase sync
- AST-based chunking (tree-sitter)
- 250 tokens/second via custom kernels

### D. Aider Architecture

Source: [Substack Analysis](https://juli1.substack.com/p/anatomy-of-a-coding-agent-aider)

Key findings:
- Single agent, no multi-agent
- Repository map via tree-sitter
- Multiple edit formats: whole, diff, udiff
- Git integration for atomic commits
- LiteLLM for provider-agnostic LLM access

---

## Document History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-09-10 | Initial architecture |

---

## Authors

- Design: Architecture discussion session
- Research: Claude Code, Codex, Cursor, Aider, Kiro analysis
- Review: Pending

---

*This document is the single source of truth for Forge Code Generation. All implementation should follow this architecture.*
