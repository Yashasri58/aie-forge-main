# Forge Codebase Documentation

A comprehensive end-to-end guide covering all components, flows, and architecture of the Forge application.

---

## Table of Contents

1. [Overview](#overview)
2. [Project Structure](#project-structure)
3. [Architecture](#architecture)
4. [Backend Components](#backend-components)
   - [Main Entry Point](#main-entry-point)
   - [CodeGraph Module](#codegraph-module)
   - [CodeGraph Enrichment Module](#codegraph-enrichment-module)
   - [Impact Analysis Agent](#impact-analysis-agent)
   - [Pipeline Orchestrator](#pipeline-orchestrator)
   - [Code Generation Module](#code-generation-module)
   - [Verification Harness](#verification-harness)
5. [API Endpoints](#api-endpoints)
6. [Frontend](#frontend)
7. [Target Services](#target-services)
8. [End-to-End Flows](#end-to-end-flows)
9. [Data Models](#data-models)
10. [Configuration](#configuration)
11. [All Agents Summary](#all-agents-summary)
12. [Future Plans](#future-plans)

---

## All Agents Summary

Forge uses 6 agents across 2 pipelines. Each agent has a distinct role.

### Agent Overview Table

| Agent | Pipeline | File | Mission |
|-------|----------|------|---------|
| **Context Gatherer** | Impact Analysis | `agents/context_gatherer.py` | Clarify vague requirements via conversation |
| **Impact Agent** | Impact Analysis | `agents/impact/agent.py` | Answer "what breaks if I change X?" using code graph |
| **Verification Agent** | Impact Analysis | `agents/verification_agent.py` | Check impact analysis completeness, identify gaps |
| **Design Agent** | Code Generation | `codegen/design_agent.py` | Create detailed plan.json from impact report |
| **Coordinator Agent** | Code Generation | `codegen/coordinator_agent.py` | Validate plan before execution |
| **Implementation Agent** | Code Generation | `codegen/implementation_agent.py` | Generate unified diffs for each task |
| **Verifier Agent** | Code Generation | `codegen/verifier_agent.py` | Verify diffs match plan exactly |

### Pipeline 1: Impact Analysis

```
User Requirement
       │
       ▼
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│ Context Gatherer │────▶│   Impact Agent   │────▶│Verification Agent│
│ (clarify scope)  │     │ (trace impacts)  │     │ (check complete) │
└──────────────────┘     └──────────────────┘     └──────────────────┘
                                                          │
                                                          ▼
                                              Gaps found? Loop back (max 3x)
                                                          │
                                                          ▼
                                                   Human Approval
```

### Pipeline 2: Code Generation

```
Impact Report (approved)
       │
       ▼
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│   Design Agent   │────▶│Coordinator Agent │────▶│Implementation    │
│ (create plan)    │     │ (validate plan)  │     │Agent(s) (diffs)  │
└──────────────────┘     └──────────────────┘     └──────────────────┘
                                                          │
                                                          ▼
                                                 ┌──────────────────┐
                                                 │  Verifier Agent  │
                                                 │ (quality gate)   │
                                                 └──────────────────┘
                                                          │
                                                          ▼
                                              Issues? Retry with feedback (max 3x)
                                                          │
                                                          ▼
                                                   Human Approval
```

### Agent Tools Summary

| Agent | Key Tools |
|-------|-----------|
| **Context Gatherer** | `get_available_services()`, `search_functions()`, `get_function_impact_summary()`, `get_service_overview()`, `get_service_enrichment()` |
| **Impact Agent** | `analyze_impact()`, `trace_call_path()`, `query_cypher()`, `get_service_topology()`, `search_symbols()`, `get_schema()` |
| **Verification Agent** | `trace_callers()`, `trace_callees()`, `search_symbol()`, `get_symbol_context()`, `get_service_http_calls()`, `get_shared_table_owners()`, `get_service_env_vars()` |
| **Design Agent** | `query_code_graph()` (query_types: symbols/calls/callers/callees/http_connections/**packages/db_tables/api_endpoints/env_vars**), `read_file()`, `grep()`, `find_symbol()`, `list_services()`, `list_directory()`, `get_similar_patterns()`, `get_http_topology()`, `find_tests()` |
| **Coordinator Agent** | `check_file_exists()`, `validate_js_syntax()`, `detect_circular_deps()`, `parse_imports()`, `read_file_content()`, `resolve_import_path()`, `analyze_phase_parallelism()` |
| **Implementation Agent** | `read_current_file()` — reads live file to guard against stale task specs |
| **Verifier Agent** | `parse_diff()`, `check_js_syntax()`, `compare_signature()`, `check_imports_resolve()`, `find_undefined_references()`, `check_error_handling()` |

**New tools added Sep 2026:**
- `get_service_enrichment(service_name)` — ContextGatherer: returns packages, DB tables, endpoints, env vars for a service with auto-generated warnings
- `get_shared_table_owners(table_name)` — VerificationAgent: finds services owning tables with matching name (catches schema-level gaps)
- `get_service_env_vars(service_name)` — VerificationAgent: gets env vars a service reads (catches config change gaps)
- `query_code_graph(query_type="packages"|"db_tables"|"api_endpoints"|"env_vars")` — DesignAgent: 4 new enrichment query types

**Updated schema in ImpactAgent prompts (Sep 2026):**

The `query_cypher` docstring and `GRAPH_SCHEMA` constant in `impact/prompts.py`
now list all 8 node types and 8 edge types including the 4 enrichment additions,
so the agent knows to query enrichment data when relevant.

### Prompts Location

All system prompts are in:
- **Impact Analysis**: `src/modules/agents/impact/prompts.py`
- **Code Generation**: `src/modules/codegen/prompts.py`

---

## Future Plans

Improvements deferred from the POC — not needed to demonstrate the core pipeline.

### 1. Verifier Agent — Live Test Execution

**What:** Add `run_tests(service, test_file)` tool to the Verifier Agent so it can execute real tests after verifying diffs.

**Why deferred:** Services have no test framework, no test files, and no `node_modules`. The tool would always fail in the current state.

**What unlocks it:**
1. Add jest to each service: `npm install --save-dev jest`
2. Add test script to each `package.json`: `"test": "jest --testPathPattern=<file>"`
3. Write at least one test file per service
4. Add `run_tests()` to `VerifierTools` — one `subprocess.run` call:

```python
def run_tests(self, service: str, test_file: str = None) -> dict:
    service_path = self._services_path / service
    cmd = ["npm", "test"]
    if test_file:
        cmd += ["--", "--testPathPattern", test_file]
    result = subprocess.run(cmd, cwd=service_path, capture_output=True, text=True, timeout=60)
    return {
        "passed": result.returncode == 0,
        "stdout": result.stdout[-3000:],  # last 3000 chars
        "stderr": result.stderr[-1000:],
        "exit_code": result.returncode,
    }
```

**Impact:** Catches runtime failures that syntax/contract checks miss. Moves Verifier Agent from 95% → 100% potential.

---

### 2. SERVICE_VAR_MAP — Auto-Discovery

**What:** Currently `http_linker.py` uses a hardcoded `SERVICE_VAR_MAP` to map variable names like `PAYMENT_SERVICE` to service names.

**Why deferred:** Hardcoded map works for the demo codebase. Auto-discovery adds complexity for minimal gain in POC.

**What unlocks it:** Parse `.env` files and `config.js` files across services to auto-build the map at index time.

---

### 3. Multi-Language Support

**What:** codegraph-tools currently indexes JS/TS. Python, Java, Go services would not be indexed.

**Why deferred:** Demo codebase is all Node.js.

**What unlocks it:** codegraph-tools supports additional languages via tree-sitter grammars. Register Python/Java parsers.

---

### 4. Test Scaffolding for New Code

**What:** When the Design Agent creates a new file, automatically include a task to scaffold a basic test file.

**Why deferred:** No test framework in place (see item 1).

**What unlocks it:** Item 1 above — once jest is set up, the Design Agent's `find_tests()` tool can inform test scaffolding tasks.

---

## Overview

Forge is an AI-powered code generation and impact analysis platform. It:

1. **Indexes microservices** into a code knowledge graph using codegraph-tools (tree-sitter AST parsing)
2. **Stores the graph** in Kuzu (embedded graph database) for persistent, queryable access
3. **Analyzes impact** of code changes using an LLM agent that queries the graph via Cypher
4. **Generates code** through a multi-agent pipeline (Design → Implement → Verify)
5. **Validates generated code** with a deterministic harness (syntax, security, contracts)

The system is built with:
- **Backend**: Python FastAPI
- **LLM**: Google Gemini (via ADK - Agent Development Kit)
- **Code Extraction**: codegraph-tools (PyPI package)
- **Graph DB**: Kuzu (embedded graph database with Cypher support)
- **Frontend**: React + TypeScript + Vite

---

## Project Structure

```
forge/
├── main.py                         # FastAPI entry point
├── requirements.txt                # Python dependencies
├── start.bat / stop.bat            # Windows startup scripts
│
├── src/
│   ├── interfaces/api/             # FastAPI routes
│   │   ├── codegen_routes.py       # /codegen endpoints
│   │   └── routes/
│   │       ├── health.py           # /health
│   │       ├── impact.py           # /impact endpoints
│   │       ├── graph_explorer.py   # /graph endpoints
│   │       └── pipeline.py         # /pipeline endpoints
│   │
│   └── modules/
│       ├── codegraph/              # Code graph (codegraph-tools + Kuzu)
│       │   ├── __init__.py         # Exports: KuzuCodeGraphStore, CodeGraphTools, CodeGraphEnricher
│       │   ├── kuzu_store.py       # Kuzu graph database wrapper
│       │   ├── tools.py            # CodeGraphTools for agents
│       │   ├── indexer.py          # Multi-repo indexer using codegraph.extract
│       │   ├── http_linker.py      # HTTP route/call detection
│       │   ├── enricher.py         # NEW: Package deps, DB schemas, OpenAPI, env vars
│       │   └── adapter.py          # UnifiedGraphAdapter (NetworkX fallback)
│       │
│       ├── agents/
│       │   ├── base.py             # Base agent classes
│       │   ├── orchestrator.py     # PipelineOrchestrator
│       │   ├── context_gatherer.py # Requirement clarification
│       │   ├── verification_agent.py # Report verification
│       │   └── impact/
│       │       ├── agent.py        # ImpactAgent (ADK) - uses CodeGraphTools + Cypher
│       │       └── prompts.py      # Agent system prompt
│       │
│       └── codegen/                # Code generation module
│           ├── orchestrator.py     # CodeGenOrchestrator
│           ├── coordinator_agent.py # Plan validation & distribution
│           ├── design_agent.py     # Plan creation (ADK)
│           ├── implementation_agent.py # Code writing
│           ├── verifier_agent.py   # Result verification
│           ├── verification.py     # Verification logic
│           ├── schemas.py          # Pydantic/dataclass schemas
│           ├── prompts.py          # Agent prompts
│           ├── llm_router.py       # LLM model routing
│           ├── logging_config.py   # Structured logging
│           └── harness/            # Deterministic verification
│               ├── gate.py         # DeterministicGate orchestrator
│               └── ...             # Checker modules
│
├── frontend/                       # React UI
│   ├── src/
│   │   ├── App.tsx                 # Router setup
│   │   ├── api.ts                  # API client (includes enrichment fetch functions)
│   │   ├── types.ts                # TypeScript types
│   │   ├── pages/                  # Page components
│   │   │   ├── Graph.tsx           # Graph Explorer (updated: Dependencies button)
│   │   │   └── ...                 # Other pages unchanged
│   │   └── components/
│   │       ├── EnrichmentPanel.tsx # NEW: 4-tab panel (packages/DB/API/env vars)
│   │       └── ...                 # Other components unchanged
│   └── analyst.html                # Standalone analyst UI
│
├── services/                       # Target microservices
│   ├── account-service/
│   ├── audit-service/
│   ├── fx-service/
│   ├── gateway-service/
│   ├── ledger-service/
│   ├── payment-processor/
│   ├── payment-ui/
│   ├── validation-service/
│   └── codegraph-out/              # Extraction output
│       ├── combined_extraction.json # Source JSON from codegraph-tools
│       └── code_graph.kuzu/        # Kuzu database directory
│
└── docs/                           # Documentation
    ├── CODE_GENERATION_ARCHITECTURE.md
    ├── MULTI_AGENT_CODE_GEN_RESEARCH.md
    └── CODEGRAPH_INTEGRATION.md
```

---

## Architecture

### High-Level Flow

```
┌─────────────┐    ┌──────────────┐    ┌───────────────┐    ┌──────────────┐
│   User      │───▶│  Frontend    │───▶│  FastAPI      │───▶│  LLM Agents  │
│   (Browser) │    │  (React)     │    │  (Backend)    │    │  (Gemini)    │
└─────────────┘    └──────────────┘    └───────────────┘    └──────────────┘
                                              │
                                              ▼
                   ┌──────────────────────────────────────────┐
                   │         Code Graph Infrastructure        │
                   │                                          │
                   │  codegraph-tools ──▶ JSON ──▶ Kuzu DB   │
                   │  (extraction)        (nodes/  (Cypher   │
                   │                       edges)   queries) │
                   └──────────────────────────────────────────┘
```

### Code Graph Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        CODE GRAPH PIPELINE                               │
│                                                                          │
│  ┌───────────────┐     ┌──────────────────┐     ┌───────────────────┐  │
│  │ codegraph-    │     │  JSON Extraction │     │  Kuzu Database    │  │
│  │ tools         │────▶│                  │────▶│                   │  │
│  │ (tree-sitter) │     │  nodes: [{id,    │     │  Service nodes    │  │
│  │               │     │   name, kind,    │     │  Symbol nodes     │  │
│  │ Parses:       │     │   file, repo}]   │     │  CALLS edges      │  │
│  │ - JS/TS       │     │                  │     │  CONTAINS edges   │  │
│  │ - Functions   │     │  edges: [{source,│     │                   │  │
│  │ - Classes     │     │   target,        │     │  Cypher queries   │  │
│  │ - Calls       │     │   relation}]     │     │  for agents       │  │
│  └───────────────┘     └──────────────────┘     └───────────────────┘  │
│                                                                          │
│  Storage: services/codegraph-out/                                       │
│    - combined_extraction.json (source)                                  │
│    - code_graph.kuzu/ (database)                                        │
└─────────────────────────────────────────────────────────────────────────┘
```

### Agent Architecture

```
                          ┌─────────────────────────────────────────────┐
                          │              Pipeline Orchestrator           │
                          │  (orchestrator.py)                          │
                          │  - Manages overall pipeline state           │
                          │  - Coordinates agents                        │
                          │  - Verification loop (max 3 iterations)     │
                          └─────────────────────────────────────────────┘
                                          │
            ┌─────────────────────────────┼─────────────────────────────┐
            │                             │                             │
            ▼                             ▼                             ▼
┌───────────────────┐        ┌───────────────────┐        ┌───────────────────┐
│ Context Gatherer  │        │   Impact Agent    │        │ Verification Agent│
│ - Asks questions  │───────▶│ - Queries Kuzu    │───────▶│ - Checks report   │
│ - Clarifies reqs  │        │ - Traces calls    │        │ - Identifies gaps │
│ - Confirms scope  │        │ - Produces report │        │ - Triggers loop   │
│                   │        │                   │        │                   │
│ Tools:            │        │ Tools:            │        │ Tools:            │
│ - services list   │        │ - search_symbols  │        │ - trace_callers   │
│ - search_symbols  │        │ - analyze_impact  │        │ - trace_callees   │
│                   │        │ - trace_call_path │        │ - search_symbol   │
│                   │        │ - get_topology    │        │                   │
│                   │        │ - query_cypher    │        │                   │
└───────────────────┘        └───────────────────┘        └───────────────────┘
            │                             │                             │
            └─────────────────────────────┴─────────────────────────────┘
                                          │
                                          ▼
                               ┌───────────────────┐
                               │  CodeGraphTools   │
                               │  (shared by all)  │
                               │                   │
                               │  Wraps Kuzu with  │
                               │  high-level API   │
                               └───────────────────┘
                                          │
                                          ▼
                               ┌───────────────────┐
                               │ KuzuCodeGraphStore│
                               │                   │
                               │ - Cypher queries  │
                               │ - Persistent DB   │
                               │ - ACID compliance │
                               └───────────────────┘
```

---

## Backend Components

### Main Entry Point

**File**: `main.py`

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # STARTUP:
    # 1. Find extraction JSON: services/codegraph-out/combined_extraction.json
    # 2. Initialize Kuzu: services/codegraph-out/code_graph.kuzu
    # 3. Load extraction into Kuzu (if empty)
    # 4. Run HttpLinker to detect service-to-service HTTP calls
    # 5. Run CodeGraphEnricher (packages, DB schemas, OpenAPI, env vars)
    # 6. Create CodeGraphTools(kuzu_store)
    # 7. Create ImpactAgent(store, tools)
    # 8. Create PipelineOrchestrator(agent)
    # 9. Create CodeGenOrchestrator(store, services_path)
    
    from modules.codegraph.kuzu_store import KuzuCodeGraphStore
    from modules.codegraph.tools import CodeGraphTools
    from modules.codegraph.enricher import CodeGraphEnricher
    
    _store = KuzuCodeGraphStore(kuzu_db_path)
    _store.init_schema()
    
    if _store.get_symbol_count() == 0:
        _store.load_extraction(extraction_path)
    
    # Always re-run enrichment so enrichment tables stay current
    enricher = CodeGraphEnricher(str(services_path))
    enrichment = enricher.extract_all()
    _store.load_enrichment(enrichment)
    
    _tools = CodeGraphTools(kuzu_store=_store)
    _agent = ImpactAgent(_store, _tools)
    
    yield
    # SHUTDOWN: cleanup
```

---

### CodeGraph Module

**Directory**: `src/modules/codegraph/`

The new code graph infrastructure using codegraph-tools for extraction and Kuzu for storage.

#### Components

| File | Purpose |
|------|---------|
| `kuzu_store.py` | `KuzuCodeGraphStore` - Kuzu database wrapper with Cypher |
| `tools.py` | `CodeGraphTools` - High-level tool interface for agents |
| `indexer.py` | `CodeGraphIndexer` - Multi-repo indexer using codegraph.extract |
| `http_linker.py` | `HttpLinker` - HTTP route/call detection |
| `adapter.py` | `UnifiedGraphAdapter` - NetworkX fallback (optional) |

#### Kuzu Schema

**Core Nodes** (from codegraph-tools AST extraction):
```
Service(name STRING, path STRING) PRIMARY KEY(name)
Symbol(id STRING, name STRING, kind STRING, file STRING,
       start_line INT64, end_line INT64, service STRING) PRIMARY KEY(id)
HttpRoute(id STRING, service STRING, method STRING, path STRING, handler STRING)
```

**Enrichment Nodes** (from CodeGraphEnricher — added Sep 2026):
```
Package(name STRING)                                          -- npm packages
DbTable(id STRING, service STRING, table_name STRING)         -- SQLite tables
ApiEndpoint(id STRING, service STRING, method STRING,
            path STRING, operation_id STRING)                 -- OpenAPI endpoints
EnvVar(name STRING)                                           -- env vars read by services
```

**Core Relationships**:
```
CONTAINS:    Service   → Symbol      (service owns function/class)
CALLS:       Symbol    → Symbol      (function A calls function B)
EXPOSES:     Service   → HttpRoute   (Express route definition)
HTTP_CALLS:  Service   → Service     (cross-service HTTP dependency, method + path props)
```

**Enrichment Relationships** (added Sep 2026):
```
DEPENDS_ON:        Service → Package      (npm dependency, version + dep_type props)
OWNS_TABLE:        Service → DbTable      (service owns this SQLite table)
EXPOSES_ENDPOINT:  Service → ApiEndpoint  (OpenAPI contract endpoint)
READS_ENV:         Service → EnvVar       (service reads this env var)
```

#### KuzuCodeGraphStore (`kuzu_store.py`)

```python
class KuzuCodeGraphStore:
    def __init__(self, db_path: str):
        self.db = kuzu.Database(db_path)
        self.conn = kuzu.Connection(self.db)
    
    def init_schema(self):
        # Creates node and relationship tables
    
    def load_extraction(self, extraction_path: str):
        # Loads codegraph-tools JSON into Kuzu
        # Parses nodes, edges, creates Services, Symbols, CALLS edges
    
    def query(self, cypher: str, params: dict) -> list[dict]:
        # Execute Cypher query
    
    def search_symbols(self, query: str, service: str = None) -> list[dict]:
        # Case-insensitive symbol search
    
    def get_callers(self, symbol_id: str) -> list[dict]:
        # MATCH (caller)-[:CALLS]->(target {id: $id})
    
    def get_callees(self, symbol_id: str) -> list[dict]:
        # MATCH (source {id: $id})-[:CALLS]->(callee)
    
    def get_call_chain(self, symbol_id: str, direction: str, max_depth: int):
        # Recursive BFS traversal through CALLS edges
```

#### CodeGraphTools (`tools.py`)

```python
class CodeGraphTools:
    """High-level tool interface used by all agents."""
    
    def __init__(self, kuzu_store):
        self._store = kuzu_store
        self._build_indices()  # Cache services, symbols
    
    @property
    def services(self) -> list[str]:
        return self._store.get_services()
    
    @property
    def all_symbols(self) -> list[dict]:
        return self._all_symbols
    
    def get_schema(self) -> dict:
        """Graph schema for LLM context."""
    
    def search_symbols(self, query, kind=None, service=None) -> dict:
        """Find symbols by name pattern."""
    
    def analyze_impact(self, symbol_name) -> dict:
        """THE key tool - comprehensive impact analysis."""
        # Returns: symbol info, direct callers, outgoing calls,
        #          affected services, risk level, testing recommendation
    
    def trace_call_path(self, symbol, direction, max_depth) -> dict:
        """Follow call chains in/out."""
    
    def get_service_topology(self, service=None) -> dict:
        """HTTP service dependencies."""
    
    def query_graph(self, cypher, params=None) -> dict:
        """Raw Cypher query access."""
```

#### CodeGraphIndexer (`indexer.py`)

```python
class CodeGraphIndexer:
    """Index multiple repos using codegraph-tools."""
    
    def __init__(self, services_path: str):
        self.services_path = Path(services_path)
    
    def index_all(self) -> dict:
        """
        Index all services, returns combined extraction.
        
        Uses:
        - codegraph.extract.collect_files() - find code files
        - codegraph.extract.extract() - parse AST
        - codegraph.build.build() - create NetworkX graph
        """
        all_nodes, all_edges = [], []
        
        for repo_path in self._find_repos():
            files = collect_files(repo_path)
            extraction = extract(files)
            # Tag with repo name
            for node in extraction['nodes']:
                node['repo'] = repo_path.name
            all_nodes.extend(extraction['nodes'])
            all_edges.extend(extraction['edges'])
        
        return {'nodes': all_nodes, 'edges': all_edges}
    
    def save_extraction(self, output_path: str):
        """Save combined extraction to JSON."""
```

---

### CodeGraph Enrichment Module

**File**: `src/modules/codegraph/enricher.py`
**Added**: September 2026

Extracts 4 additional enrichment layers from service source files that
codegraph-tools does not cover. Runs automatically on startup after
`load_extraction()` completes.

#### Why it exists

codegraph-tools only extracts 3 relation types: `contains`, `method`, `calls`.
It cannot see npm package dependencies, SQL schemas, OpenAPI contracts, or
environment variable usage. The enricher fills these gaps using stdlib + pyyaml.

#### Components

| Extractor | Source | What it extracts |
|-----------|--------|-----------------|
| `extract_package_deps()` | `package.json` per service | npm runtime + dev dependencies |
| `extract_db_schemas()` | `db/database.js` per service | SQLite `CREATE TABLE` definitions |
| `extract_openapi_contracts()` | `contracts/openapi.yaml` per service | HTTP endpoints, request/response schemas |
| `extract_env_vars()` | All `*.js` files | `process.env.VAR_NAME` usages |

#### Usage

```python
from modules.codegraph.enricher import CodeGraphEnricher
from modules.codegraph.kuzu_store import KuzuCodeGraphStore

enricher = CodeGraphEnricher(services_path)
enrichment = enricher.extract_all()
# Returns: {packages: [...], db_tables: [...], endpoints: [...], env_vars: [...]}

store.load_enrichment(enrichment)
# Upserts all 4 enrichment types into Kuzu
```

#### What it enables agents to answer

```cypher
-- Which services use axios? (CVE blast radius)
MATCH (s:Service)-[:DEPENDS_ON]->(p:Package {name: 'axios'}) RETURN s.name

-- What tables does payment-processor own?
MATCH (s:Service)-[:OWNS_TABLE]->(t:DbTable) WHERE s.name = 'payment-processor'
RETURN t.table_name

-- Which services expose the /payments endpoint?
MATCH (s:Service)-[:EXPOSES_ENDPOINT]->(e:ApiEndpoint)
WHERE e.path CONTAINS 'payments' RETURN s.name, e.method, e.path

-- What env vars does gateway-service read?
MATCH (s:Service)-[:READS_ENV]->(e:EnvVar) WHERE s.name = 'gateway-service'
RETURN e.name
```

#### Current enrichment data (8 services)

| Layer | Count |
|-------|-------|
| Package dependencies | 30 entries (26 runtime, 4 dev) |
| DB tables | 8 tables across 6 services |
| API endpoints | 57 endpoints across 7 services |
| Env var usages | 24 unique service/var pairs |

---

### Impact Analysis Agent

**Directory**: `src/modules/agents/impact/`

ADK-based agent that answers "what breaks if I change X?" using CodeGraphTools + Kuzu.

#### Tools Available to Agent

| Tool | Type | Description |
|------|------|-------------|
| `get_schema()` | CodeGraph | Graph schema, services, symbol count |
| `search_symbols(query, kind, service)` | CodeGraph | Find functions by name |
| `analyze_impact(symbol_name)` | CodeGraph | Full impact analysis |
| `trace_call_path(symbol, direction, depth)` | CodeGraph | Call chain traversal |
| `get_service_topology(service)` | CodeGraph | HTTP dependencies |
| `query_cypher(cypher)` | Kuzu | **Raw Cypher queries** |

#### Agent Implementation (`agent.py`)

```python
# Module-level tool instances (required by ADK)
_tools: CodeGraphTools = None
_store: KuzuCodeGraphStore = None

# High-level CodeGraph tools
def get_schema() -> dict:
    return _tools.get_schema()

def search_symbols(query, kind=None, service=None) -> dict:
    return _tools.search_symbols(query, kind, service)

def analyze_impact(symbol_name: str) -> dict:
    return _tools.analyze_impact(symbol_name)

def trace_call_path(start_symbol, direction="outgoing", max_depth=4) -> dict:
    return _tools.trace_call_path(start_symbol, direction, max_depth)

def get_service_topology(service_name=None) -> dict:
    return _tools.get_service_topology(service_name)

# Low-level Kuzu access
def query_cypher(cypher_query: str) -> dict:
    """Raw Cypher query against Kuzu database."""
    try:
        results = _store.query(cypher_query)
        return {"query": cypher_query, "results": results[:100]}
    except Exception as e:
        return {"error": str(e), "query": cypher_query}

class ImpactAgent:
    def __init__(self, graph_store, tools=None):
        global _tools, _store
        _store = graph_store
        _tools = tools or CodeGraphTools(kuzu_store=graph_store)
        
        self.agent = Agent(
            model="gemini-2.5-flash",
            tools=[get_schema, search_symbols, analyze_impact,
                   trace_call_path, get_service_topology, query_cypher]
        )
    
    def get_tools(self) -> CodeGraphTools:
        return _tools
    
    def get_graph_tools(self) -> CodeGraphTools:
        """Alias for backward compatibility."""
        return _tools
```

#### Example Cypher Queries

```cypher
-- Find all functions that call validatePayment
MATCH (a:Symbol)-[:CALLS]->(b:Symbol {name: 'validatePayment'})
RETURN a.name AS caller, a.service AS service

-- Count symbols per service
MATCH (s:Symbol) 
RETURN s.service AS service, count(*) AS cnt 
ORDER BY cnt DESC

-- Find call chains (2 hops)
MATCH (a:Symbol)-[:CALLS]->(b:Symbol)-[:CALLS]->(c:Symbol)
WHERE a.name = 'processPayment'
RETURN a.name, b.name, c.name

-- Cross-service calls
MATCH (a:Symbol)-[:CALLS]->(b:Symbol)
WHERE a.service <> b.service
RETURN a.service, a.name, b.service, b.name
```

---

### Other Agents Using CodeGraphTools

#### ContextGathererAgent (`context_gatherer.py`)

Clarifies vague requirements through conversation and proactively warns about high-impact changes.

```python
_graph_tools = None  # Set to CodeGraphTools instance

def get_available_services() -> dict:
    """List all indexed microservices."""
    return {"services": _graph_tools.services}

def search_functions(query: str, service: str = None) -> dict:
    """Find functions by name pattern."""
    return _graph_tools.search_symbols(query, kind="function", service=service)

def get_function_impact_summary(function_name: str) -> dict:
    """
    Get quick impact summary - caller count, affected services, risk level.
    Used to warn user about high-impact changes.
    """
    impact = _graph_tools.analyze_impact(function_name)
    return {
        "function": function_name,
        "service": impact.get("symbol", {}).get("service"),
        "caller_count": len(impact.get("direct_callers", [])),
        "affected_services": impact.get("affected_services", []),
        "risk_level": impact.get("risk_level", "UNKNOWN"),
    }

def get_service_overview(service_name: str) -> dict:
    """
    Get service overview - function count, HTTP dependencies, criticality.
    Helps user understand what they're working with.
    """
    symbols = _graph_tools.search_symbols("", service=service_name)
    topology = _graph_tools.get_service_topology(service_name)
    return {
        "service": service_name,
        "function_count": symbols.get("count", 0),
        "calls_services": [...],      # Services this one calls
        "called_by_services": [...],  # Services that call this one
        "is_critical": len(called_by) > 2,
    }

class ContextGathererAgent:
    def __init__(self, graph_tools):
        global _graph_tools
        _graph_tools = graph_tools  # CodeGraphTools instance
    
    def _get_tools(self) -> list:
        return [
            get_available_services,
            search_functions,
            get_function_impact_summary,
            get_service_overview,
        ]
```

#### VerificationAgent (`verification_agent.py`)

```python
_graph_tools = None  # Set to CodeGraphTools instance

def trace_callers(symbol: str, max_depth: int = 2) -> dict:
    return _graph_tools.trace_call_path(symbol, direction="incoming", max_depth=max_depth)

def trace_callees(symbol: str, max_depth: int = 2) -> dict:
    return _graph_tools.trace_call_path(symbol, direction="outgoing", max_depth=max_depth)

def search_symbol(name: str) -> dict:
    return _graph_tools.search_symbols(name)

class VerificationAgent:
    def __init__(self, graph_tools):
        global _graph_tools
        _graph_tools = graph_tools  # CodeGraphTools instance
```

#### PipelineOrchestrator (`orchestrator.py`)

```python
class PipelineOrchestrator:
    def __init__(self, impact_agent):
        self.impact_agent = impact_agent
        self.tools = impact_agent.get_graph_tools()  # CodeGraphTools
        
        # Pass tools to other agents
        self.context_gatherer = ContextGathererAgent(self.tools)
        self.verification_agent = VerificationAgent(self.tools)
```

---

### Pipeline Orchestrator

**File**: `src/modules/agents/orchestrator.py`

Manages the 3-agent impact analysis pipeline.

#### Pipeline Stages

```python
class PipelineStage(Enum):
    GATHERING = "gathering"           # ContextGatherer asking questions
    REQUIREMENTS_READY = "req_ready"  # Awaiting user confirmation
    ANALYZING = "analyzing"           # ImpactAgent producing report
    VERIFYING = "verifying"           # VerificationAgent checking
    FILLING_GAPS = "filling_gaps"     # ImpactAgent filling gaps
    AWAITING_APPROVAL = "awaiting"    # Report ready for approval
    APPROVED = "approved"
    REJECTED = "rejected"
    FAILED = "failed"
```

#### Flow

```
User Input → ContextGatherer (Q&A loop)
                    ↓
            Requirements Ready
                    ↓
            User Confirms "proceed"
                    ↓
            ImpactAgent (queries Kuzu, produces report)
                    ↓
            VerificationAgent (checks completeness via CodeGraphTools)
                    ↓
            Gaps found? ──YES──→ ImpactAgent fills gaps (max 3x)
                    │
                    NO
                    ↓
            User Approves/Rejects
```

---

### Code Generation Module

**Directory**: `src/modules/codegen/`

Multi-agent code generation pipeline with deterministic verification.

#### Code Generation Pipeline Flow

```
Impact Report
      │
      ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         DESIGN AGENT                                     │
│  File: design_agent.py                                                  │
│                                                                          │
│  Mission: Create complete, unambiguous plan.json                        │
│                                                                          │
│  Tools:                                                                  │
│  - query_code_graph(query_type, service, file, symbol)                  │
│  - read_file(file_path)                                                 │
│  - grep(pattern, file_glob, max_results)                                │
│  - find_symbol(name)                                                    │
│  - list_services()                                                      │
│  - list_directory(path, recursive)                                      │
│                                                                          │
│  Process:                                                                │
│  1. Understand change request + impact report                           │
│  2. Explore codebase structure (CRITICAL - verify files exist)          │
│  3. Design with exact interfaces/contracts                              │
│  4. Output detailed plan.json with exact code for every change          │
└─────────────────────────────────────────────────────────────────────────┘
      │
      ▼ plan.json
┌─────────────────────────────────────────────────────────────────────────┐
│                       COORDINATOR AGENT                                  │
│  File: coordinator_agent.py                                             │
│                                                                          │
│  Mission: Validate plan before implementation begins                    │
│                                                                          │
│  Tools:                                                                  │
│  - check_file_exists(path)                                              │
│  - check_directory_exists(path)                                         │
│  - read_file_content(file_path)                                         │
│  - parse_imports(file_path)                                             │
│  - find_symbol_in_file(file_path, symbol)                               │
│  - get_file_exports(file_path)                                          │
│  - resolve_import_path(from_file, import_path)                          │
│  - validate_json_syntax(content)                                        │
│  - validate_js_syntax(content)                                          │
│  - detect_circular_deps(tasks)                                          │
│  - analyze_phase_parallelism(tasks, phase_tasks)                        │
│                                                                          │
│  Validates:                                                              │
│  1. File targets - MODIFY files exist, CREATE parent dirs exist         │
│  2. Dependencies - No circular deps, valid depends_on references        │
│  3. Contracts - All used contracts defined, signatures valid            │
│  4. Phase safety - Parallel tasks don't conflict                        │
│  5. Import resolution - Relative imports will resolve correctly         │
│                                                                          │
│  Output: {valid: bool, errors: [], warnings: [], summary: str}          │
└─────────────────────────────────────────────────────────────────────────┘
      │
      ▼ validated plan
┌─────────────────────────────────────────────────────────────────────────┐
│                     IMPLEMENTATION AGENT(S)                              │
│  File: implementation_agent.py                                          │
│                                                                          │
│  Mission: Execute tasks from plan, generate unified diffs               │
│                                                                          │
│  Input per task:                                                         │
│  - task_id, file, action (create/modify/delete)                         │
│  - current_content (if modifying)                                       │
│  - changes (exact changes to make)                                      │
│  - contracts (interface contracts - FOLLOW EXACTLY)                     │
│  - design_decisions, conventions                                        │
│                                                                          │
│  Rules:                                                                  │
│  - Follow contracts EXACTLY (use exact signatures)                      │
│  - Make ONLY specified changes                                          │
│  - Do NOT add anything not specified                                    │
│  - Do NOT "improve" unless explicitly asked                             │
│  - Match existing code style exactly                                    │
│                                                                          │
│  Output: Unified diff for each file                                     │
│                                                                          │
│  Parallelism: Up to 5 concurrent agents per phase                       │
└─────────────────────────────────────────────────────────────────────────┘
      │
      ▼ diffs
┌─────────────────────────────────────────────────────────────────────────┐
│                         VERIFIER AGENT                                   │
│  File: verifier_agent.py                                                │
│                                                                          │
│  Mission: Quality gate - verify diffs EXACTLY match plan                │
│                                                                          │
│  Tools:                                                                  │
│  - get_task_from_plan(plan_json, task_id)                               │
│  - get_contract_from_plan(plan_json, contract_name)                     │
│  - compare_signature(code, contract)                                    │
│  - parse_diff(diff_text)                                                │
│  - validate_diff_syntax(diff_text)                                      │
│  - apply_diff_to_content(original, diff)                                │
│  - count_diff_changes(diff_text)                                        │
│  - check_js_syntax(code)                                                │
│  - find_undefined_references(code)                                      │
│  - check_imports_resolve(code, base_file)                               │
│  - extract_functions(code)                                              │
│  - check_error_handling(code)                                           │
│  - read_file_content(file_path)                                         │
│                                                                          │
│  Checks (priority order):                                                │
│  1. Task compliance - correct file, service, action, all changes made   │
│  2. Contract compliance - signatures match exactly                      │
│  3. Design compliance - follows plan.design decisions                   │
│  4. Code quality - syntax, imports, error handling                      │
│                                                                          │
│  Output: {passed: bool, issues: [...], summary: str}                    │
│                                                                          │
│  On failure: Returns actionable feedback, Implementation Agent retries  │
└─────────────────────────────────────────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      DETERMINISTIC HARNESS                               │
│  Directory: codegen/harness/                                            │
│                                                                          │
│  Non-LLM verification layer (syntax, security, contracts)               │
│  See: Verification Harness section                                      │
└─────────────────────────────────────────────────────────────────────────┘
      │
      ▼
   User Approval (diffs presented for review)
```

#### CodeGenOrchestrator (`orchestrator.py`)

```python
class CodeGenOrchestrator:
    def __init__(self, graph_store, services_path):
        self._store = graph_store
        self._services_path = services_path
        
        # Initialize all codegen agents
        self._design_agent = DesignAgent(services_path)
        self._coordinator = CoordinatorAgent(services_path)
        self._verifier = VerifierAgent(services_path)
    
    async def run(self, impact_report: dict) -> CodeGenResult:
        # 1. Design Agent creates plan
        plan = await self._design_agent.create_plan(impact_report)
        
        # 2. Coordinator validates plan
        validation = await self._coordinator.validate(plan)
        if not validation.valid:
            return CodeGenResult(status="failed", errors=validation.errors)
        
        # 3. Implementation Agents execute tasks (parallel by phase)
        diffs = await self._run_implementation(plan)
        
        # 4. Verifier Agent checks diffs
        verification = await self._verifier.verify(plan, diffs)
        if not verification.passed:
            # Retry loop (max 3 attempts)
            diffs = await self._retry_with_feedback(plan, diffs, verification)
        
        # 5. Deterministic harness (syntax, security)
        harness_result = await self._run_harness(diffs)
        
        return CodeGenResult(
            status="ready_for_approval",
            plan=plan,
            diffs=diffs,
            verification=verification
        )
```

#### Agent Prompts (`prompts.py`)

All agent system prompts are centralized in `src/modules/codegen/prompts.py`:

| Constant | Agent | Purpose |
|----------|-------|---------|
| `COORDINATOR_AGENT_SYSTEM_PROMPT` | Coordinator | Plan validation rules and tools |
| `DESIGN_AGENT_SYSTEM_PROMPT` | Design | Plan creation process and tools |
| `IMPLEMENTATION_AGENT_SYSTEM_PROMPT` | Implementation | Diff generation rules |
| `VERIFIER_AGENT_SYSTEM_PROMPT` | Verifier | Verification checks and feedback format |
| `VERIFICATION_AGENT_SYSTEM_PROMPT` | Verification (legacy) | Final review checks |
| `PLAN_REFINEMENT_PROMPT` | Design | Plan update based on feedback |
| `DIFF_FIX_PROMPT` | Implementation | Fix issues in diff |

---

## API Endpoints

### Health Check

```
GET /health
Response: {"status": "ok", "graph_ready": true, "symbol_count": 253}
```

### Pipeline (Impact Analysis)

```
POST /pipeline/start
Body: {"message": "Add fraud detection to payments"}
Response: PipelineState

POST /pipeline/{id}/respond
POST /pipeline/{id}/confirm
POST /pipeline/{id}/approve
POST /pipeline/{id}/reject
GET /pipeline/{id}
```

### Code Generation

```
POST /codegen/start
Body: {"pipeline_id": "uuid"}
Response: CodeGenState

GET /codegen/{id}
GET /codegen/{id}/plan
GET /codegen/{id}/diffs
POST /codegen/{id}/approve
POST /codegen/{id}/refine
```

### Graph Explorer

```
GET /graph/overview          - Service topology (all services + HTTP edges)
GET /graph/service/{name}    - Expand service to see its symbols
GET /graph/symbol/{id}       - Expand symbol to see call chains
GET /graph/stats             - Symbol counts, edge counts, services
POST /graph/query            - Raw Cypher query
  Body: {"cypher": "MATCH (s:Symbol) RETURN s LIMIT 10"}
```

### Graph Enrichment (Added Sep 2026)

```
GET /graph/enrichment/packages?service=<name>
  Returns npm package dependencies grouped by service.
  Includes shared_packages list (packages used by 2+ services).

GET /graph/enrichment/db-tables?service=<name>
  Returns SQLite table names grouped by service.

GET /graph/enrichment/api-endpoints?service=<name>
  Returns OpenAPI endpoints (method + path) grouped by service.

GET /graph/enrichment/env-vars?service=<name>
  Returns env var names grouped by service.
  Includes shared_vars list (vars read by 2+ services).

All enrichment endpoints accept optional ?service= query param to filter to one service.
```

---

## Frontend

**Directory**: `forge/frontend/src/`

Built with React + TypeScript + Vite. Served by FastAPI at `http://localhost:8000`.

### Pages

| Page | Route | Purpose |
|------|-------|---------|
| `Dashboard.tsx` | `/` | Entry point — "Make Changes" button, graph stats |
| `Chat.tsx` | `/chat` | ContextGatherer conversation UI |
| `Pipeline.tsx` | `/pipeline/:id` | Live pipeline logs during analysis |
| `Results.tsx` | `/results/:id` | Layered impact report viewer |
| `Approval.tsx` | `/approval/:id` | Approve/reject impact report |
| `CodeGen.tsx` | `/codegen/:id` | Code generation progress |
| `DiffApproval.tsx` | `/diffs/:id` | Review diffs before applying |
| `Graph.tsx` | `/explore` | Graph Explorer with EnrichmentPanel |

### Components

| Component | Purpose |
|-----------|---------|
| `HowForgeWorks.tsx` | 5-step animated modal showing how Forge works |
| `HowItWorks.tsx` | Code graph "How it works" modal (5 stages) |
| `PlanViewer.tsx` | Renders plan.json visually |
| `DiffViewer.tsx` | Syntax-highlighted unified diff viewer |
| `GraphCanvas.tsx` | Cytoscape.js graph with fCose layout |
| `EnrichmentPanel.tsx` | **NEW** 4-tab panel: Packages / DB Tables / Endpoints / Env Vars |

### EnrichmentPanel (Added Sep 2026)

**File**: `frontend/src/components/EnrichmentPanel.tsx`

Accessible from the Graph Explorer page via the "Dependencies" button in the
bottom toolbar. Replaces the node details panel when active.

**4 tabs:**

| Tab | API Endpoint | What it shows |
|-----|-------------|---------------|
| Packages | `GET /graph/enrichment/packages` | Runtime npm packages per service, shared packages highlighted in amber |
| DB Tables | `GET /graph/enrichment/db-tables` | SQLite tables per service, collapsible |
| Endpoints | `GET /graph/enrichment/api-endpoints` | OpenAPI routes with colour-coded methods (GET green, POST blue, DELETE red) |
| Env Vars | `GET /graph/enrichment/env-vars` | Env vars per service, shared vars highlighted in blue |

All 4 data sources are fetched in parallel on mount. Each tab is collapsible per service.

---

## Target Services

**Directory**: `services/`

| Service | Purpose | Indexed Symbols |
|---------|---------|-----------------|
| `account-service` | Account management | ~30 |
| `audit-service` | Audit logging | ~25 |
| `fx-service` | Foreign exchange rates | ~20 |
| `gateway-service` | API gateway, routing | ~35 |
| `ledger-service` | Transaction ledger | ~30 |
| `payment-processor` | Payment processing logic | ~40 |
| `payment-ui` | Frontend for payments | ~30 |
| `validation-service` | Input validation | ~25 |

**Total**: 8 services, ~253 symbols, 87 call edges

### Extraction Output

```
services/codegraph-out/
├── combined_extraction.json    # Source JSON (nodes + edges)
└── code_graph.kuzu/            # Kuzu database directory
    ├── data.mdb
    └── lock.mdb
```

---

## Data Models

### Graph Data (Kuzu)

```
Service: {name: "payment-processor", path: ""}
Symbol: {id: "processPayment", name: "processPayment", kind: "function", 
         file: "src/processor.js", start_line: 42, service: "payment-processor"}
CALLS: (processPayment)-[:CALLS]->(validatePayment)
```

### CodeGraphTools Output

```python
# search_symbols
{"query": "validate", "results": [...], "count": 10}

# analyze_impact
{
    "symbol": {"name": "processPayment", "service": "payment-processor", ...},
    "direct_callers": [...],
    "outgoing_calls": [...],
    "affected_services": ["gateway-service"],
    "risk_level": "LOW",
    "explanation": "**processPayment** in **payment-processor**\n- 0 direct callers..."
}

# trace_call_path
{"symbol": "validatePayment", "direction": "outgoing", "paths": [...], "total_paths": 3}
```

---

## Configuration

### Environment Variables

```bash
GOOGLE_API_KEY=<your-gemini-api-key>
```

### Paths

| Path | Purpose |
|------|---------|
| `services/` | Target microservices |
| `services/codegraph-out/combined_extraction.json` | Extraction JSON |
| `services/codegraph-out/code_graph.kuzu/` | Kuzu database |

---

## Running the Application

### 1. Extract Code Graph (one-time or on code changes)

```bash
cd forge
python -c "
from src.modules.codegraph import CodeGraphIndexer
indexer = CodeGraphIndexer('../services')
extraction = indexer.index_all()
indexer.save_extraction('../services/codegraph-out/combined_extraction.json')
"
```

### 2. Start Backend

```bash
cd forge
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

On startup, main.py will:
1. Load extraction JSON
2. Initialize Kuzu database
3. Load symbols into Kuzu (if empty)
4. Initialize agents with CodeGraphTools

### 3. Frontend (Development)

```bash
cd forge/frontend
npm install
npm run dev
```

---

## Summary: Agent Tool Usage

| Agent | Tools Used | Source |
|-------|------------|--------|
| **ImpactAgent** | `get_schema`, `search_symbols`, `analyze_impact`, `trace_call_path`, `get_service_topology`, `query_cypher` | CodeGraphTools + Kuzu direct |
| **ContextGathererAgent** | `.services`, `search_symbols()` | CodeGraphTools |
| **VerificationAgent** | `trace_call_path()`, `search_symbols()` | CodeGraphTools |

All agents share the same `CodeGraphTools` instance, which wraps `KuzuCodeGraphStore` for Cypher query execution.

---

*Updated: September 2026 — Reflects codegraph-tools + Kuzu architecture with enrichment layer (packages, DB schemas, OpenAPI contracts, env vars), updated agent tools, 4 new API endpoints, and EnrichmentPanel UI.*
