# Forge — AI Development Platform

**Tagline:** *Where AI forges code changes*

**Goal:** A platform that can analyze, modify, and verify **any codebase** — not tied to a specific language, framework, or project structure.

---

## Design Principles

1. **Plugin-based** — Languages, parsers, LLMs, verifiers are all plugins
2. **Adapter pattern** — Abstract interfaces with concrete implementations
3. **Config-driven** — Behavior controlled by configuration, not hardcoded
4. **Provider-agnostic** — Swap LLMs, databases, CI systems without code changes
5. **Schema-first** — Well-defined interfaces between components
6. **Event-driven** — Loose coupling via events for extensibility

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                            HARNESS CORE                                 │
│         (Orchestration, Events, Plugin Management, Config)              │
└─────────────────────────────────────────────────────────────────────────┘
        │                    │                    │                    │
        ▼                    ▼                    ▼                    ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   ADAPTERS   │    │   PLUGINS    │    │  PROVIDERS   │    │  INTERFACES  │
│              │    │              │    │              │    │              │
│ • Language   │    │ • Parsers    │    │ • LLM        │    │ • CLI        │
│ • SCM (Git)  │    │ • Analyzers  │    │ • Storage    │    │ • API        │
│ • CI/CD      │    │ • Verifiers  │    │ • Queue      │    │ • SDK        │
│ • Contract   │    │ • Rules      │    │ • Notify     │    │ • Events     │
└──────────────┘    └──────────────┘    └──────────────┘    └──────────────┘
```

---

## Folder Structure

```
harness/
│
├── core/                           # Core framework (language-agnostic)
│   ├── index.js                    # Main entry
│   ├── Harness.js                  # Main harness class
│   │
│   ├── config/                     # Configuration system
│   │   ├── ConfigLoader.js         # Load from yaml/json/env
│   │   ├── ConfigValidator.js      # Validate config schema
│   │   ├── ConfigResolver.js       # Resolve env vars, defaults
│   │   └── schemas/                # Config schemas
│   │       ├── harness.schema.json
│   │       ├── project.schema.json
│   │       └── plugins.schema.json
│   │
│   ├── plugin/                     # Plugin system
│   │   ├── PluginManager.js        # Load, register, manage plugins
│   │   ├── PluginLoader.js         # Dynamic plugin loading
│   │   ├── PluginRegistry.js       # Plugin registry
│   │   └── interfaces/             # Plugin interfaces (contracts)
│   │       ├── ILanguageAdapter.js
│   │       ├── IParser.js
│   │       ├── IAnalyzer.js
│   │       ├── IVerifier.js
│   │       ├── ILLMProvider.js
│   │       └── IStorageProvider.js
│   │
│   ├── event/                      # Event system
│   │   ├── EventBus.js             # Pub/sub event bus
│   │   ├── EventTypes.js           # Event type definitions
│   │   └── EventLogger.js          # Event logging
│   │
│   ├── pipeline/                   # Pipeline execution
│   │   ├── Pipeline.js             # Pipeline orchestrator
│   │   ├── Stage.js                # Pipeline stage
│   │   ├── StageRunner.js          # Execute stages
│   │   └── PipelineBuilder.js      # Fluent pipeline builder
│   │
│   ├── context/                    # Execution context
│   │   ├── Context.js              # Request context
│   │   ├── ProjectContext.js       # Project metadata
│   │   └── ExecutionContext.js     # Current execution state
│   │
│   ├── errors/                     # Error handling
│   │   ├── HarnessError.js
│   │   ├── PluginError.js
│   │   └── ErrorCodes.js
│   │
│   └── utils/                      # Core utilities
│       ├── logger.js
│       ├── async.js
│       └── hash.js
│
├── adapters/                       # External system adapters
│   │
│   ├── language/                   # Language adapters
│   │   ├── ILanguageAdapter.js     # Interface
│   │   ├── javascript/
│   │   │   ├── index.js
│   │   │   ├── JavaScriptAdapter.js
│   │   │   ├── ASTParser.js
│   │   │   ├── ImportResolver.js
│   │   │   └── ExpressRouteDetector.js
│   │   ├── typescript/
│   │   │   ├── index.js
│   │   │   └── TypeScriptAdapter.js
│   │   ├── python/
│   │   │   ├── index.js
│   │   │   └── PythonAdapter.js
│   │   ├── java/
│   │   │   ├── index.js
│   │   │   └── JavaAdapter.js
│   │   └── go/
│   │       ├── index.js
│   │       └── GoAdapter.js
│   │
│   ├── scm/                        # Source control adapters
│   │   ├── ISCMAdapter.js          # Interface
│   │   ├── git/
│   │   │   ├── index.js
│   │   │   ├── GitAdapter.js
│   │   │   ├── GitHubAdapter.js    # GitHub-specific (PRs, etc.)
│   │   │   ├── GitLabAdapter.js
│   │   │   └── BitbucketAdapter.js
│   │   └── svn/                    # Future
│   │       └── SVNAdapter.js
│   │
│   ├── contract/                   # API contract adapters
│   │   ├── IContractAdapter.js     # Interface
│   │   ├── openapi/
│   │   │   ├── index.js
│   │   │   ├── OpenAPIAdapter.js
│   │   │   └── OpenAPIDiffer.js
│   │   ├── asyncapi/
│   │   │   └── AsyncAPIAdapter.js
│   │   ├── graphql/
│   │   │   └── GraphQLAdapter.js
│   │   └── protobuf/
│   │       └── ProtobufAdapter.js
│   │
│   ├── ci/                         # CI/CD adapters
│   │   ├── ICIAdapter.js           # Interface
│   │   ├── github-actions/
│   │   │   └── GitHubActionsAdapter.js
│   │   ├── jenkins/
│   │   │   └── JenkinsAdapter.js
│   │   ├── gitlab-ci/
│   │   │   └── GitLabCIAdapter.js
│   │   └── azure-devops/
│   │       └── AzureDevOpsAdapter.js
│   │
│   └── database/                   # Database adapters (for harness storage)
│       ├── IStorageAdapter.js      # Interface
│       ├── sqlite/
│       │   └── SQLiteAdapter.js
│       ├── postgresql/
│       │   └── PostgreSQLAdapter.js
│       └── mongodb/
│           └── MongoDBAdapter.js
│
├── providers/                      # Service providers
│   │
│   ├── llm/                        # LLM providers
│   │   ├── ILLMProvider.js         # Interface
│   │   ├── BaseLLMProvider.js      # Base class
│   │   ├── anthropic/
│   │   │   ├── index.js
│   │   │   └── AnthropicProvider.js
│   │   ├── openai/
│   │   │   ├── index.js
│   │   │   └── OpenAIProvider.js
│   │   ├── azure-openai/
│   │   │   └── AzureOpenAIProvider.js
│   │   ├── bedrock/
│   │   │   └── BedrockProvider.js
│   │   ├── ollama/                 # Local LLMs
│   │   │   └── OllamaProvider.js
│   │   └── mock/                   # For testing
│   │       └── MockLLMProvider.js
│   │
│   ├── embedding/                  # Embedding providers
│   │   ├── IEmbeddingProvider.js
│   │   ├── openai/
│   │   └── local/
│   │
│   ├── storage/                    # Storage providers (for harness data)
│   │   ├── IStorageProvider.js
│   │   ├── local/
│   │   │   └── LocalStorageProvider.js
│   │   ├── s3/
│   │   │   └── S3StorageProvider.js
│   │   └── azure-blob/
│   │       └── AzureBlobProvider.js
│   │
│   └── notification/               # Notification providers
│       ├── INotificationProvider.js
│       ├── slack/
│       ├── email/
│       └── webhook/
│
├── modules/                        # Feature modules (the actual features)
│   │
│   ├── graph/                      # Code graph module
│   │   ├── index.js
│   │   ├── GraphModule.js          # Module entry
│   │   ├── builder/
│   │   │   ├── GraphBuilder.js
│   │   │   └── IncrementalBuilder.js
│   │   ├── model/
│   │   │   ├── Graph.js
│   │   │   ├── Node.js
│   │   │   └── Edge.js
│   │   ├── query/
│   │   │   ├── QueryEngine.js
│   │   │   └── ImpactAnalyzer.js
│   │   ├── storage/
│   │   │   └── GraphStore.js
│   │   └── visualizer/
│   │       └── GraphVisualizer.js
│   │
│   ├── analyzer/                   # Requirement analyzer module
│   │   ├── index.js
│   │   ├── AnalyzerModule.js
│   │   ├── parser/
│   │   │   └── RequirementParser.js
│   │   ├── mapper/
│   │   │   └── ServiceMapper.js
│   │   └── output/
│   │       └── ImpactReport.js
│   │
│   ├── agents/                     # Agent orchestration module
│   │   ├── index.js
│   │   ├── AgentsModule.js
│   │   ├── coordinator/
│   │   │   └── Coordinator.js
│   │   ├── specialists/
│   │   │   └── Specialist.js
│   │   ├── context/
│   │   │   └── ContextManager.js
│   │   └── execution/
│   │       └── AgentExecutor.js
│   │
│   ├── verifier/                   # Verification module
│   │   ├── index.js
│   │   ├── VerifierModule.js
│   │   ├── runners/
│   │   │   ├── RunnerRegistry.js
│   │   │   ├── LintRunner.js
│   │   │   ├── TestRunner.js
│   │   │   └── ContractRunner.js
│   │   ├── rules/
│   │   │   ├── RulesEngine.js
│   │   │   └── RuleRegistry.js
│   │   └── hallucination/
│   │       └── HallucinationDetector.js
│   │
│   ├── governance/                 # Governance module
│   │   ├── index.js
│   │   ├── GovernanceModule.js
│   │   ├── risk/
│   │   │   └── RiskClassifier.js
│   │   ├── audit/
│   │   │   └── AuditLogger.js
│   │   └── approval/
│   │       └── ApprovalEngine.js
│   │
│   └── [future-module]/            # Easy to add new modules
│       ├── index.js
│       └── FutureModule.js
│
├── interfaces/                     # External interfaces
│   │
│   ├── api/                        # REST API
│   │   ├── index.js
│   │   ├── server.js
│   │   ├── routes/
│   │   ├── middleware/
│   │   └── validators/
│   │
│   ├── cli/                        # Command-line interface
│   │   ├── index.js
│   │   ├── commands/
│   │   └── formatters/
│   │
│   ├── sdk/                        # SDK for programmatic use
│   │   ├── index.js
│   │   └── HarnessClient.js
│   │
│   └── webhook/                    # Webhook handlers
│       ├── index.js
│       └── handlers/
│
├── rules/                          # Built-in rules (extensible)
│   │
│   ├── architecture/               # Architecture rules
│   │   ├── no-circular-deps.js
│   │   ├── layer-violations.js
│   │   └── naming-conventions.js
│   │
│   ├── security/                   # Security rules
│   │   ├── no-hardcoded-secrets.js
│   │   ├── sql-injection.js
│   │   └── xss-prevention.js
│   │
│   ├── quality/                    # Code quality rules
│   │   ├── complexity.js
│   │   ├── duplication.js
│   │   └── documentation.js
│   │
│   └── custom/                     # Project-specific rules
│       └── .gitkeep
│
├── templates/                      # Templates for generation
│   │
│   ├── prompts/                    # LLM prompt templates
│   │   ├── analysis/
│   │   ├── generation/
│   │   └── verification/
│   │
│   ├── code/                       # Code templates (per language)
│   │   ├── javascript/
│   │   ├── typescript/
│   │   └── python/
│   │
│   └── reports/                    # Report templates
│       ├── impact.hbs
│       ├── verification.hbs
│       └── audit.hbs
│
├── config/                         # Configuration
│   │
│   ├── default.yaml                # Default config
│   ├── schema.json                 # Config schema
│   │
│   └── presets/                    # Config presets
│       ├── javascript-microservices.yaml
│       ├── python-monolith.yaml
│       ├── java-spring.yaml
│       └── minimal.yaml
│
├── tests/                          # Tests
│   ├── unit/
│   ├── integration/
│   ├── e2e/
│   └── fixtures/
│
├── docs/                           # Documentation
│   ├── getting-started.md
│   ├── configuration.md
│   ├── plugins.md
│   ├── api-reference.md
│   └── extending.md
│
├── examples/                       # Example projects
│   ├── javascript-payment/         # Our payment app
│   ├── python-flask/
│   └── java-spring/
│
├── package.json
├── harness.config.yaml             # Default harness config
└── README.md
```

---

## Plugin Interface Examples

### ILanguageAdapter

```javascript
// adapters/language/ILanguageAdapter.js

/**
 * Interface for language-specific adapters
 * Implement this to add support for a new language
 */
class ILanguageAdapter {
  /** Language identifier (e.g., 'javascript', 'python') */
  get language() { throw new Error('Not implemented'); }
  
  /** File extensions this adapter handles */
  get extensions() { throw new Error('Not implemented'); }
  
  /** Parse a file into AST */
  async parseFile(filePath) { throw new Error('Not implemented'); }
  
  /** Extract functions/methods from AST */
  extractFunctions(ast) { throw new Error('Not implemented'); }
  
  /** Extract imports/dependencies */
  extractImports(ast) { throw new Error('Not implemented'); }
  
  /** Find HTTP calls to other services */
  findHTTPCalls(ast) { throw new Error('Not implemented'); }
  
  /** Extract route definitions (for web frameworks) */
  extractRoutes(ast) { throw new Error('Not implemented'); }
}
```

### ILLMProvider

```javascript
// providers/llm/ILLMProvider.js

/**
 * Interface for LLM providers
 * Implement this to add support for a new LLM
 */
class ILLMProvider {
  /** Provider identifier */
  get name() { throw new Error('Not implemented'); }
  
  /** Available models */
  get models() { throw new Error('Not implemented'); }
  
  /** Send a completion request */
  async complete(prompt, options) { throw new Error('Not implemented'); }
  
  /** Send a chat request */
  async chat(messages, options) { throw new Error('Not implemented'); }
  
  /** Count tokens in text */
  countTokens(text) { throw new Error('Not implemented'); }
  
  /** Get model limits */
  getModelLimits(model) { throw new Error('Not implemented'); }
}
```

### IVerifier

```javascript
// core/plugin/interfaces/IVerifier.js

/**
 * Interface for verification plugins
 * Implement this to add custom verification logic
 */
class IVerifier {
  /** Verifier identifier */
  get name() { throw new Error('Not implemented'); }
  
  /** Verifier category (lint, test, contract, architecture) */
  get category() { throw new Error('Not implemented'); }
  
  /** Languages this verifier supports (or '*' for all) */
  get supportedLanguages() { throw new Error('Not implemented'); }
  
  /** Run verification on a set of files */
  async verify(files, context) { throw new Error('Not implemented'); }
  
  /** Get verification results */
  getResults() { throw new Error('Not implemented'); }
}
```

---

## Configuration Example

```yaml
# harness.config.yaml

# Project being analyzed
project:
  name: payment-system
  path: ./services
  type: microservices
  
# Language configuration (auto-detected if not specified)
languages:
  - javascript
  
# Adapters to use
adapters:
  language: javascript          # or auto-detect
  scm: github
  contract: openapi
  ci: github-actions
  storage: sqlite

# LLM configuration
llm:
  default: anthropic
  providers:
    anthropic:
      model: claude-sonnet-4-20250514
      api_key: ${ANTHROPIC_API_KEY}
    openai:
      model: gpt-4
      api_key: ${OPENAI_API_KEY}
  routing:
    planning: anthropic/claude-sonnet-4-20250514
    code_generation: anthropic/claude-sonnet-4-20250514
    simple_tasks: anthropic/claude-haiku

# Modules to enable
modules:
  graph:
    enabled: true
    storage: sqlite
    incremental: true
  analyzer:
    enabled: true
    confidence_threshold: 0.7
  agents:
    enabled: true
    max_parallel: 3
  verifier:
    enabled: true
    runners:
      - lint
      - test
      - contract
  governance:
    enabled: true
    risk_classification: true
    audit_logging: true

# Verification rules
rules:
  architecture:
    - no-circular-deps
    - naming-conventions
  security:
    - no-hardcoded-secrets
  custom:
    - ./rules/payment-specific.js

# Plugins (external)
plugins:
  - @harness/plugin-sonarqube
  - @harness/plugin-jira
  - ./my-custom-plugin
```

---

## Adding New Capabilities

### Add Support for a New Language (e.g., Rust)

```bash
# 1. Create adapter folder
mkdir -p adapters/language/rust

# 2. Implement the interface
# adapters/language/rust/RustAdapter.js
class RustAdapter extends ILanguageAdapter {
  get language() { return 'rust'; }
  get extensions() { return ['.rs']; }
  async parseFile(filePath) { /* use tree-sitter-rust */ }
  // ... implement other methods
}

# 3. Register in plugin config or auto-discovery
```

### Add Support for a New LLM (e.g., Gemini)

```bash
# 1. Create provider folder
mkdir -p providers/llm/gemini

# 2. Implement the interface
# providers/llm/gemini/GeminiProvider.js
class GeminiProvider extends ILLMProvider {
  get name() { return 'gemini'; }
  async complete(prompt, options) { /* call Gemini API */ }
  // ... implement other methods
}

# 3. Add to config
```

### Add a New Verification Rule

```javascript
// rules/custom/payment-amount-limit.js
module.exports = {
  name: 'payment-amount-limit',
  category: 'business',
  supportedLanguages: ['*'],
  
  async verify(files, context) {
    const violations = [];
    // Check for hardcoded amount limits > 1M
    // ...
    return { passed: violations.length === 0, violations };
  }
};
```

### Add a New Module (e.g., Documentation Generator)

```bash
# 1. Create module folder
mkdir -p modules/docs-generator

# 2. Create module entry
# modules/docs-generator/index.js
# modules/docs-generator/DocsGeneratorModule.js

# 3. Register module in config
modules:
  docs-generator:
    enabled: true
    output: ./docs/generated
```

---

## Event System

The harness emits events that plugins can listen to:

```javascript
// Event types
const EventTypes = {
  // Lifecycle
  HARNESS_INIT: 'harness:init',
  HARNESS_READY: 'harness:ready',
  
  // Graph
  GRAPH_BUILD_START: 'graph:build:start',
  GRAPH_BUILD_COMPLETE: 'graph:build:complete',
  GRAPH_NODE_ADDED: 'graph:node:added',
  
  // Analysis
  ANALYSIS_START: 'analysis:start',
  ANALYSIS_COMPLETE: 'analysis:complete',
  
  // Agents
  AGENT_TASK_START: 'agent:task:start',
  AGENT_TASK_COMPLETE: 'agent:task:complete',
  AGENT_ERROR: 'agent:error',
  
  // Verification
  VERIFY_START: 'verify:start',
  VERIFY_COMPLETE: 'verify:complete',
  VERIFY_FAILURE: 'verify:failure',
  
  // Governance
  AUDIT_LOG: 'audit:log',
  RISK_CLASSIFIED: 'risk:classified'
};

// Plugins can subscribe
harness.on(EventTypes.VERIFY_FAILURE, (event) => {
  // Send Slack notification, etc.
});
```

---

## Summary: Why This is Future-Agnostic

| Concern | How It's Handled |
|---------|------------------|
| New language | Add adapter in `adapters/language/` |
| New LLM provider | Add provider in `providers/llm/` |
| New contract format | Add adapter in `adapters/contract/` |
| New CI system | Add adapter in `adapters/ci/` |
| New verification rule | Add rule in `rules/` |
| New feature module | Add module in `modules/` |
| New storage backend | Add provider in `providers/storage/` |
| Project-specific logic | Custom plugins, rules, templates |
| Different project types | Config presets in `config/presets/` |

The harness doesn't know or care what it's analyzing — it just uses the configured adapters and plugins.
