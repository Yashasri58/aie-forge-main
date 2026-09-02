# AI Development Harness — Project Structure

**Date:** 2026-09-02  
**Purpose:** Modular folder structure for Steps 2-5 of the AI Code Modernization PoV

---

## Overview

This document defines the folder structure for the **AI Development Harness** — the tooling that will:
- **Step 2:** Build a code graph from the payment services
- **Step 3:** Map requirements to impacted services
- **Step 4:** Orchestrate AI agents for multi-service changes
- **Step 5:** Verify changes with deterministic harness + governance

---

## High-Level Structure

```
hsbc_rfp/
├── services/                    # Step 1 ✅ (COMPLETED)
│   ├── account-service/
│   ├── payment-processor/
│   ├── validation-service/
│   ├── ledger-service/
│   ├── fx-service/
│   ├── audit-service/
│   ├── gateway-service/
│   ├── payment-ui/
│   └── docker-compose.yaml
│
├── harness/                     # Steps 2-5 (NEW)
│   ├── core/                    # Shared infrastructure
│   ├── graph/                   # Step 2: Code Graph
│   ├── analyzer/                # Step 3: Requirement → Service Mapping
│   ├── agents/                  # Step 4: Agent Orchestration
│   ├── verifier/                # Step 5: Verification Harness
│   ├── governance/              # Step 5: Audit & Governance
│   ├── api/                     # REST API for harness
│   ├── cli/                     # Command-line interface
│   ├── ui/                      # Harness dashboard (optional)
│   └── tests/                   # Integration tests
│
├── docs/                        # Documentation
│   ├── PROJECT_PLAN.md
│   ├── STEP1_RESEARCH_AND_PLAN.md
│   ├── USER_GUIDE.md
│   └── HARNESS_ARCHITECTURE.md  # (NEW)
│
├── config/                      # Global configuration
│   ├── services.yaml            # Service registry
│   ├── agents.yaml              # Agent definitions
│   └── rules.yaml               # Verification rules
│
├── scripts/                     # Utility scripts
│   ├── setup.sh
│   └── demo.sh
│
├── start.bat
├── stop.bat
├── install.bat
└── README.md
```

---

## Detailed Structure: `/harness`

### `/harness/core` — Shared Infrastructure

Common utilities, database connections, logging, and configuration management.

```
harness/core/
├── index.js                     # Main exports
├── config/
│   ├── index.js                 # Configuration loader
│   ├── schema.js                # Config validation schema
│   └── defaults.js              # Default values
├── database/
│   ├── index.js                 # Database connection manager
│   ├── migrations/              # Schema migrations
│   │   ├── 001_initial.js
│   │   └── 002_graph_tables.js
│   └── models/                  # Shared data models
│       ├── Service.js
│       ├── Endpoint.js
│       └── Requirement.js
├── logging/
│   ├── index.js                 # Logger setup
│   ├── formatters.js            # Log formatters
│   └── transports.js            # Console, file, etc.
├── utils/
│   ├── http.js                  # HTTP client wrapper
│   ├── file.js                  # File system utilities
│   ├── hash.js                  # Hashing utilities
│   └── async.js                 # Async helpers
├── errors/
│   ├── index.js                 # Error classes
│   ├── HarnessError.js          # Base error
│   ├── GraphError.js
│   ├── AgentError.js
│   └── VerificationError.js
└── package.json
```

---

### `/harness/graph` — Step 2: Code Graph Construction

Builds a queryable semantic graph of the payment services.

```
harness/graph/
├── index.js                     # Main exports
├── builder/
│   ├── index.js                 # Graph builder orchestrator
│   ├── ServiceScanner.js        # Scan service directories
│   ├── OpenAPIParser.js         # Parse OpenAPI specs
│   ├── ASTParser.js             # Parse JavaScript AST
│   ├── DependencyDetector.js    # Find HTTP calls between services
│   └── SchemaExtractor.js       # Extract data schemas
├── model/
│   ├── Graph.js                 # Main graph class
│   ├── nodes/
│   │   ├── ServiceNode.js       # Microservice node
│   │   ├── EndpointNode.js      # API endpoint node
│   │   ├── FunctionNode.js      # Function/module node
│   │   ├── SchemaNode.js        # Data schema node
│   │   └── FileNode.js          # Source file node
│   └── edges/
│       ├── CallsEdge.js         # Service A calls Service B
│       ├── ContainsEdge.js      # Service contains function
│       ├── UsesSchemaEdge.js    # Endpoint uses schema
│       └── DependsOnEdge.js     # Code dependency
├── storage/
│   ├── index.js                 # Storage interface
│   ├── SQLiteStore.js           # SQLite-based storage
│   ├── MemoryStore.js           # In-memory (for testing)
│   └── Neo4jStore.js            # Neo4j (optional, for scale)
├── query/
│   ├── index.js                 # Query engine
│   ├── QueryBuilder.js          # Fluent query builder
│   ├── ImpactAnalyzer.js        # "What if I change X?"
│   ├── DependencyTracer.js      # Trace dependencies
│   └── PathFinder.js            # Find paths between nodes
├── visualizer/
│   ├── index.js                 # Visualization generator
│   ├── MermaidExporter.js       # Export to Mermaid diagrams
│   ├── D3Exporter.js            # Export for D3.js
│   └── DotExporter.js           # Export to Graphviz DOT
├── parsers/
│   ├── javascript/
│   │   ├── index.js             # JS parser entry
│   │   ├── FunctionExtractor.js # Extract functions
│   │   ├── ImportAnalyzer.js    # Analyze imports
│   │   ├── HTTPCallFinder.js    # Find axios/fetch calls
│   │   └── ExpressRouteParser.js# Parse Express routes
│   └── openapi/
│       ├── index.js             # OpenAPI parser entry
│       ├── EndpointExtractor.js # Extract endpoints
│       └── SchemaExtractor.js   # Extract schemas
└── package.json
```

**Key Classes:**
- `Graph` — Main graph data structure with nodes and edges
- `ServiceScanner` — Discovers services from directory structure
- `ASTParser` — Parses JavaScript code into AST using @babel/parser
- `ImpactAnalyzer` — Answers "What services are affected if I change X?"

---

### `/harness/analyzer` — Step 3: Requirement → Service Mapping

Maps natural language requirements to impacted services.

```
harness/analyzer/
├── index.js                     # Main exports
├── parser/
│   ├── index.js                 # Requirement parser entry
│   ├── RequirementParser.js     # Parse NL requirement
│   ├── EntityExtractor.js       # Extract domain entities
│   ├── IntentClassifier.js      # Classify intent (add/modify/remove)
│   └── ScopeDetector.js         # Detect scope (field/endpoint/service)
├── mapper/
│   ├── index.js                 # Mapping engine entry
│   ├── ServiceMapper.js         # Map entities to services
│   ├── GraphQueryGenerator.js   # Generate graph queries
│   └── ConfidenceScorer.js      # Score confidence of mapping
├── llm/
│   ├── index.js                 # LLM integration entry
│   ├── LLMClient.js             # Abstract LLM client
│   ├── ClaudeClient.js          # Claude API integration
│   ├── OpenAIClient.js          # OpenAI API integration
│   ├── prompts/
│   │   ├── entity_extraction.txt
│   │   ├── intent_classification.txt
│   │   └── impact_analysis.txt
│   └── PromptManager.js         # Manage prompt templates
├── domain/
│   ├── index.js                 # Domain knowledge
│   ├── PaymentGlossary.js       # Payment domain terms
│   ├── EntityTypes.js           # Entity type definitions
│   └── IntentTypes.js           # Intent type definitions
├── output/
│   ├── ImpactReport.js          # Impact analysis report
│   ├── ServiceTask.js           # Task for a specific service
│   └── ReportFormatter.js       # Format reports
└── package.json
```

**Key Classes:**
- `RequirementParser` — Parses NL text into structured intent
- `EntityExtractor` — Uses LLM to extract domain entities (e.g., "currency conversion", "posting")
- `ServiceMapper` — Maps extracted entities to graph nodes
- `ConfidenceScorer` — Calculates confidence based on match quality

---

### `/harness/agents` — Step 4: Agent Orchestration

Coordinates multiple AI agents for multi-service changes.

```
harness/agents/
├── index.js                     # Main exports
├── coordinator/
│   ├── index.js                 # Coordinator entry
│   ├── Coordinator.js           # Main coordinator agent
│   ├── TaskDecomposer.js        # Break requirement into tasks
│   ├── TaskQueue.js             # Task queue management
│   ├── ContractManager.js       # Manage service contracts
│   └── MergeStrategy.js         # Strategy for merging changes
├── specialists/
│   ├── index.js                 # Specialist factory
│   ├── BaseSpecialist.js        # Base specialist agent
│   ├── ServiceSpecialist.js     # Per-service specialist
│   ├── CodeGenerator.js         # Generate code changes
│   └── PRCreator.js             # Create pull requests
├── verifier/
│   ├── index.js                 # Verifier agent entry
│   ├── VerifierAgent.js         # Cross-service verification
│   ├── ContractChecker.js       # Check contract compatibility
│   └── BreakingChangeDetector.js# Detect breaking changes
├── context/
│   ├── index.js                 # Context management
│   ├── ContextManager.js        # Manage agent context
│   ├── MemoryPointer.js         # Reference code by file:line
│   ├── ContextCompressor.js     # Compress context for tokens
│   └── ContractSummary.js       # Summarize contracts
├── llm/
│   ├── index.js                 # LLM integration for agents
│   ├── ModelRouter.js           # Route to appropriate model
│   ├── TokenCounter.js          # Count tokens
│   └── prompts/
│       ├── coordinator.txt
│       ├── specialist.txt
│       ├── code_generation.txt
│       └── verification.txt
├── execution/
│   ├── index.js                 # Execution engine
│   ├── AgentExecutor.js         # Execute agent tasks
│   ├── ParallelExecutor.js      # Run specialists in parallel
│   └── SequentialMerger.js      # Merge changes sequentially
├── output/
│   ├── CodeChange.js            # Represents a code change
│   ├── PullRequest.js           # Represents a PR
│   └── ExecutionReport.js       # Execution summary
└── package.json
```

**Key Classes:**
- `Coordinator` — Main orchestrator that decomposes tasks and manages workflow
- `ServiceSpecialist` — Agent with deep context on one service
- `VerifierAgent` — Validates changes across services
- `ContextManager` — Efficiently manages context window with memory pointers

---

### `/harness/verifier` — Step 5: Verification Harness

Deterministically verifies AI-generated changes.

```
harness/verifier/
├── index.js                     # Main exports
├── runners/
│   ├── index.js                 # Runner factory
│   ├── LintRunner.js            # Run ESLint
│   ├── TypeCheckRunner.js       # Type checking (if TS)
│   ├── TestRunner.js            # Run unit/integration tests
│   ├── ContractRunner.js        # Validate OpenAPI contracts
│   └── ArchRulesRunner.js       # Check architectural rules
├── contract/
│   ├── index.js                 # Contract validation entry
│   ├── OpenAPIDiff.js           # Diff OpenAPI specs
│   ├── BreakingChangeChecker.js # Identify breaking changes
│   ├── SchemaValidator.js       # Validate schemas
│   └── PactValidator.js         # Consumer contract tests
├── architecture/
│   ├── index.js                 # Architecture rules entry
│   ├── RulesEngine.js           # Execute architectural rules
│   ├── rules/
│   │   ├── NoCrossDBAccess.js   # No direct DB access across services
│   │   ├── NamingConvention.js  # Enforce naming conventions
│   │   ├── DependencyDirection.js# Enforce dependency direction
│   │   └── PIIEncryption.js     # PII fields must be encrypted
│   └── RuleRegistry.js          # Register and manage rules
├── hallucination/
│   ├── index.js                 # Hallucination detection
│   ├── HallucinationDetector.js # Main detector
│   ├── APIUsageChecker.js       # Check API calls exist
│   ├── ImportVerifier.js        # Verify imports exist
│   └── UndefinedIdentifierFinder.js # Find undefined vars
├── integration/
│   ├── index.js                 # Integration test runner
│   ├── PaymentFlowTest.js       # End-to-end payment test
│   ├── ContainerManager.js      # Manage test containers
│   └── fixtures/                # Test fixtures
│       ├── accounts.json
│       └── payments.json
├── reporters/
│   ├── index.js                 # Reporter factory
│   ├── ConsoleReporter.js       # Console output
│   ├── JSONReporter.js          # JSON output
│   ├── HTMLReporter.js          # HTML report
│   └── JUnitReporter.js         # JUnit XML for CI
├── hooks/
│   ├── index.js                 # Git hooks
│   ├── pre-commit.js            # Pre-commit hook script
│   └── pre-push.js              # Pre-push hook script
└── package.json
```

**Key Classes:**
- `ContractRunner` — Validates OpenAPI specs haven't broken
- `RulesEngine` — Executes architectural rules
- `HallucinationDetector` — Detects AI-generated code that references non-existent APIs

---

### `/harness/governance` — Step 5: Audit & Governance

Risk classification, approval workflows, and audit trails.

```
harness/governance/
├── index.js                     # Main exports
├── risk/
│   ├── index.js                 # Risk assessment entry
│   ├── RiskClassifier.js        # Classify change risk
│   ├── PathClassifier.js        # Risk by file path
│   ├── ContentClassifier.js     # Risk by content analysis
│   └── RiskLevels.js            # Risk level definitions
├── approval/
│   ├── index.js                 # Approval workflow entry
│   ├── ApprovalEngine.js        # Determine required approvals
│   ├── ReviewerAssigner.js      # Assign reviewers
│   └── SignoffTracker.js        # Track sign-offs
├── audit/
│   ├── index.js                 # Audit trail entry
│   ├── AuditLogger.js           # Log audit events
│   ├── TraceabilityManager.js   # Link requirement → code
│   ├── AuthorshipTracker.js     # Track AI vs human authorship
│   └── AuditStore.js            # Store audit records
├── git/
│   ├── index.js                 # Git integration
│   ├── GitTrailers.js           # Add/read git trailers
│   ├── PRAnnotator.js           # Annotate PRs
│   └── CommitLinker.js          # Link commits to requirements
├── reports/
│   ├── index.js                 # Report generation
│   ├── ComplianceReport.js      # Compliance summary
│   ├── AuditReport.js           # Full audit trail
│   └── GovernanceDashboard.js   # Dashboard data
└── package.json
```

**Key Classes:**
- `RiskClassifier` — Classifies changes as Low/Medium/High/Critical
- `AuditLogger` — Creates tamper-evident audit logs
- `TraceabilityManager` — Links requirements to code changes

---

### `/harness/api` — REST API

Exposes harness functionality via REST API.

```
harness/api/
├── index.js                     # Express app entry
├── routes/
│   ├── index.js                 # Route aggregator
│   ├── graph.js                 # /api/graph/*
│   ├── analyze.js               # /api/analyze/*
│   ├── agents.js                # /api/agents/*
│   ├── verify.js                # /api/verify/*
│   └── governance.js            # /api/governance/*
├── controllers/
│   ├── GraphController.js       # Graph operations
│   ├── AnalyzeController.js     # Requirement analysis
│   ├── AgentController.js       # Agent orchestration
│   ├── VerifyController.js      # Verification
│   └── GovernanceController.js  # Governance
├── middleware/
│   ├── auth.js                  # Authentication
│   ├── validation.js            # Request validation
│   ├── rateLimit.js             # Rate limiting
│   └── errorHandler.js          # Error handling
├── validators/
│   ├── graphValidators.js
│   ├── analyzeValidators.js
│   └── agentValidators.js
└── package.json
```

**API Endpoints:**

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /api/graph/build | Build/rebuild the code graph |
| GET | /api/graph/services | List all services in graph |
| GET | /api/graph/impact | Query impact of a change |
| POST | /api/analyze/requirement | Analyze a requirement |
| GET | /api/analyze/tasks/:id | Get task breakdown |
| POST | /api/agents/execute | Execute agent workflow |
| GET | /api/agents/status/:id | Get execution status |
| POST | /api/verify/run | Run verification suite |
| GET | /api/verify/report/:id | Get verification report |
| GET | /api/governance/audit | Get audit trail |

---

### `/harness/cli` — Command-Line Interface

CLI for common operations.

```
harness/cli/
├── index.js                     # CLI entry (commander.js)
├── commands/
│   ├── graph.js                 # harness graph build/query
│   ├── analyze.js               # harness analyze "requirement"
│   ├── agent.js                 # harness agent run
│   ├── verify.js                # harness verify
│   └── governance.js            # harness audit
├── output/
│   ├── TableFormatter.js        # Format as table
│   ├── JSONFormatter.js         # Format as JSON
│   └── ProgressBar.js           # Show progress
└── package.json
```

**CLI Commands:**

```bash
# Graph commands
harness graph build              # Build the code graph
harness graph query "PaymentRequest"  # Query the graph
harness graph impact --change "amount field"  # Impact analysis
harness graph visualize --output graph.svg  # Visualize

# Analyze commands
harness analyze "Add currency validation before posting"
harness analyze --file requirement.txt

# Agent commands
harness agent run --requirement "..." --dry-run
harness agent status <execution-id>

# Verify commands
harness verify --all
harness verify --contracts
harness verify --architecture
harness verify --tests

# Governance commands
harness audit --payment-id PAY-123
harness audit --since 2026-09-01
```

---

### `/harness/ui` — Dashboard (Optional)

Web dashboard for the harness.

```
harness/ui/
├── public/
│   ├── index.html
│   └── favicon.ico
├── src/
│   ├── index.js                 # React entry
│   ├── App.js                   # Main app
│   ├── components/
│   │   ├── GraphViewer.js       # Interactive graph
│   │   ├── RequirementForm.js   # Requirement input
│   │   ├── ImpactPanel.js       # Impact analysis display
│   │   ├── AgentStatus.js       # Agent execution status
│   │   └── VerificationReport.js # Verification results
│   ├── pages/
│   │   ├── Dashboard.js         # Overview
│   │   ├── GraphPage.js         # Graph explorer
│   │   ├── AnalyzePage.js       # Requirement analysis
│   │   ├── AgentsPage.js        # Agent management
│   │   └── GovernancePage.js    # Audit & governance
│   └── api/
│       └── client.js            # API client
├── package.json
└── vite.config.js
```

---

### `/harness/tests` — Integration Tests

Tests for the harness itself.

```
harness/tests/
├── graph/
│   ├── builder.test.js
│   ├── query.test.js
│   └── impact.test.js
├── analyzer/
│   ├── parser.test.js
│   ├── mapper.test.js
│   └── confidence.test.js
├── agents/
│   ├── coordinator.test.js
│   ├── specialist.test.js
│   └── execution.test.js
├── verifier/
│   ├── contract.test.js
│   ├── architecture.test.js
│   └── hallucination.test.js
├── e2e/
│   ├── full-workflow.test.js    # End-to-end demo scenario
│   └── fixtures/
├── setup.js                     # Test setup
└── jest.config.js
```

---

## Configuration Files

### `/config/services.yaml`

Service registry for the harness.

```yaml
services:
  - name: gateway-service
    port: 3000
    path: ./services/gateway-service
    type: gateway
    
  - name: account-service
    port: 3001
    path: ./services/account-service
    type: core
    database: sqlite
    
  - name: payment-processor
    port: 3002
    path: ./services/payment-processor
    type: core
    database: sqlite
    mocks:
      - hub
      - wolf
      
  # ... etc for all services
```

### `/config/agents.yaml`

Agent configuration.

```yaml
coordinator:
  model: claude-opus
  max_tokens: 8000
  temperature: 0.3
  
specialists:
  default:
    model: claude-sonnet
    max_tokens: 4000
    temperature: 0.2
    
verifier:
  model: none  # Deterministic, no LLM
  
model_routing:
  planning: claude-opus
  code_generation: claude-sonnet
  simple_edits: claude-haiku
```

### `/config/rules.yaml`

Verification and governance rules.

```yaml
architecture_rules:
  - name: no_cross_db_access
    enabled: true
    severity: error
    
  - name: naming_conventions
    enabled: true
    severity: warning
    patterns:
      services: "^[a-z]+-service$"
      functions: "^[a-z][a-zA-Z]*$"
      
risk_classification:
  low:
    paths:
      - "**/*.md"
      - "**/README*"
      - "**/*.log"
    auto_merge: true
    
  medium:
    paths:
      - "**/services/**"
      - "!**/payment*"
    reviewers: 1
    
  high:
    paths:
      - "**/payment*"
      - "**/transaction*"
    reviewers: 2
    senior_required: true
    
  critical:
    paths:
      - "**/compliance/**"
      - "**/audit/**"
    board_approval: true
```

---

## Dependency Graph

```
                    ┌─────────────────────┐
                    │     harness/core    │
                    │  (shared utilities) │
                    └──────────┬──────────┘
                               │
        ┌──────────────────────┼──────────────────────┐
        │                      │                      │
        ▼                      ▼                      ▼
┌───────────────┐    ┌─────────────────┐    ┌─────────────────┐
│ harness/graph │    │harness/analyzer │    │harness/verifier │
│   (Step 2)    │    │    (Step 3)     │    │    (Step 5)     │
└───────┬───────┘    └────────┬────────┘    └────────┬────────┘
        │                     │                      │
        └──────────┬──────────┘                      │
                   │                                 │
                   ▼                                 │
        ┌─────────────────┐                         │
        │ harness/agents  │◄────────────────────────┘
        │    (Step 4)     │
        └────────┬────────┘
                 │
        ┌────────┴────────┐
        ▼                 ▼
┌───────────────┐  ┌─────────────────┐
│  harness/api  │  │  harness/cli    │
└───────────────┘  └─────────────────┘
        │
        ▼
┌───────────────┐
│  harness/ui   │
│  (optional)   │
└───────────────┘
```

---

## Package.json Structure

### Root `/harness/package.json`

```json
{
  "name": "ai-dev-harness",
  "version": "1.0.0",
  "private": true,
  "workspaces": [
    "core",
    "graph",
    "analyzer",
    "agents",
    "verifier",
    "governance",
    "api",
    "cli"
  ],
  "scripts": {
    "build": "npm run build --workspaces",
    "test": "npm test --workspaces",
    "start:api": "npm start --workspace=api",
    "cli": "node cli/index.js"
  }
}
```

### Individual Package Example `/harness/graph/package.json`

```json
{
  "name": "@harness/graph",
  "version": "1.0.0",
  "main": "index.js",
  "dependencies": {
    "@harness/core": "workspace:*",
    "@babel/parser": "^7.23.0",
    "@babel/traverse": "^7.23.0",
    "yaml": "^2.3.0",
    "better-sqlite3": "^9.2.0"
  }
}
```

---

## Technology Choices

| Component | Technology | Rationale |
|-----------|------------|-----------|
| Language | Node.js (JavaScript) | Consistent with payment services |
| Graph Storage | SQLite (default), Neo4j (optional) | Simple to start, can scale |
| AST Parsing | @babel/parser | Standard for JavaScript |
| OpenAPI Parsing | yaml + ajv | Standard tools |
| LLM Integration | Anthropic SDK, OpenAI SDK | Support multiple providers |
| CLI | Commander.js | Standard Node.js CLI library |
| API | Express.js | Consistent with payment services |
| UI (optional) | React + Vite | Modern, fast |
| Testing | Jest | Standard for Node.js |

---

## Implementation Priority

| Order | Module | Why First |
|-------|--------|-----------|
| 1 | `/harness/core` | Foundation for everything |
| 2 | `/harness/graph` | Must have graph before analysis |
| 3 | `/harness/analyzer` | Depends on graph |
| 4 | `/harness/verifier` | Can build independently |
| 5 | `/harness/agents` | Depends on graph + analyzer + verifier |
| 6 | `/harness/governance` | Integrates with everything |
| 7 | `/harness/api` | Exposes all modules |
| 8 | `/harness/cli` | Alternative interface |
| 9 | `/harness/ui` | Optional, for demo polish |

---

## File Naming Conventions

| Type | Convention | Example |
|------|------------|---------|
| Classes | PascalCase | `GraphBuilder.js` |
| Utilities | camelCase | `hashUtils.js` |
| Constants | UPPER_SNAKE | `ERROR_CODES.js` |
| Tests | `*.test.js` | `GraphBuilder.test.js` |
| Config | lowercase | `services.yaml` |

---

## Next Steps

1. **Create folder structure** — Scaffold all directories
2. **Implement `/harness/core`** — Config, logging, utilities
3. **Implement `/harness/graph`** — Start with OpenAPI parsing
4. **Test with payment services** — Validate graph construction
5. **Continue with analyzer, verifier, agents**

---

*Document created for AI Development Harness project structure planning.*
