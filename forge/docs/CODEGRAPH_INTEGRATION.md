# CodeGraph Integration Guide

## Overview

CodeGraph is a local-first code knowledge graph tool that uses tree-sitter for AST parsing. It extracts symbols, call relationships, and builds a queryable NetworkX graph.

**Package:** `codegraph-tools` (PyPI)
**Version tested:** 0.3.29

## Installation

```bash
pip install codegraph-tools
```

## Usage

### 1. Collect and Extract

```python
from codegraph.extract import extract, collect_files
from pathlib import Path
import json

# Collect all files (respects .gitignore)
files = collect_files(Path('./services'))

# Filter to specific extensions
js_files = [f for f in files if f.suffix == '.js' and 'node_modules' not in str(f)]

# Extract symbols and relationships
extraction = extract(js_files)

# Save to JSON
with open('codegraph-out/extraction.json', 'w') as f:
    json.dump(extraction, f, indent=2)
```

### 2. Extraction Output Structure

```json
{
  "nodes": [
    {
      "id": "database_getdatabase",
      "label": "getDatabase()",
      "file_type": "code",
      "source_file": "account-service/src/db/database.js",
      "source_location": "L9"
    }
  ],
  "edges": [
    {
      "source": "database_initializedatabase",
      "target": "database_getdatabase",
      "relation": "calls",
      "confidence": "EXTRACTED",
      "source_file": "account-service/src/db/database.js",
      "source_location": "L23",
      "weight": 1.0
    }
  ],
  "input_tokens": 12345,
  "output_tokens": 0
}
```

### 3. Edge Relation Types

| Relation | Description | Count (our demo) |
|----------|-------------|------------------|
| `contains` | File contains function/class | 166 |
| `method` | Class contains method | 101 |
| `calls` | Function calls another function | 87 |

### 4. Build NetworkX Graph

```python
from codegraph.build import build
import networkx as nx

# Build directed graph (important for call analysis)
G = build([extraction], directed=True)

# Graph stats
print(f"Nodes: {G.number_of_nodes()}")  # 295
print(f"Edges: {G.number_of_edges()}")  # 335
```

### 5. Query Examples

#### Find Callers (Impact Analysis)
```python
target = 'accountservice_accountservice_getaccountbyid'
callers = list(G.predecessors(target))
# Returns: ['debitaccount', 'creditaccount', 'freezeaccount', ...]
```

#### Find Callees
```python
callees = list(G.successors(target))
```

#### Search by Label
```python
for n in G.nodes():
    label = G.nodes[n].get('label', '')
    if 'processPayment' in label:
        print(f"Found: {label} in {G.nodes[n]['source_file']}")
```

#### Find Call Path
```python
if nx.has_path(G, source, target):
    path = nx.shortest_path(G, source, target)
```

#### Get Node Attributes
```python
attrs = G.nodes['orchestrator_paymentorchestrator_processpayment']
# {'id': '...', 'label': '.processPayment()', 'source_file': '...', 'source_location': 'L45'}
```

## Our Demo Results

Indexed 8 microservices:

| Service | Functions |
|---------|-----------|
| account-service | 35 |
| audit-service | 27 |
| fx-service | 21 |
| gateway-service | 4 |
| ledger-service | 22 |
| payment-processor | 55 |
| payment-ui | 28 |
| validation-service | 41 |

**Total:** 68 JS files, 335 nodes, 354 edges, 253 functions

## Hybrid Architecture with Forge

### What CodeGraph Provides (Intra-Service)
- Symbol extraction (functions, classes, methods)
- Internal call graph (function A calls function B)
- File-to-symbol relationships
- Source location tracking

### What Forge Provides (Inter-Service)
- HTTP route detection (`app.get('/payments', ...)`)
- Service-to-service HTTP calls (`fetch('http://payment-processor/...')`)
- Service topology (which service calls which)
- Route-to-handler mapping

### Integration Strategy

```
┌─────────────────────────────────────────────────────────────┐
│                     FORGE IMPACT AGENT                       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────────┐    ┌─────────────────────┐        │
│  │    CodeGraph        │    │   Forge HTTP Layer  │        │
│  │  (Symbol Graph)     │    │  (Service Topology) │        │
│  ├─────────────────────┤    ├─────────────────────┤        │
│  │ - get_callers()     │    │ - get_services()    │        │
│  │ - get_callees()     │    │ - get_http_edges()  │        │
│  │ - search_symbol()   │    │ - get_routes()      │        │
│  │ - get_call_path()   │    │ - trace_http_call() │        │
│  └─────────────────────┘    └─────────────────────┘        │
│                                                             │
│              ↓ Combined Queries ↓                           │
│                                                             │
│  "If I change processPayment(), who is affected?"           │
│   1. CodeGraph: Find internal callers within service        │
│   2. Forge: Find HTTP callers from other services           │
│   3. Combine: Full impact chain                             │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Adapter API (To Build)

```python
class CodeGraphAdapter:
    """Bridges CodeGraph to Forge's tool interface."""
    
    def __init__(self, extraction_path: str):
        with open(extraction_path) as f:
            data = json.load(f)
        self.graph = build([data], directed=True)
    
    def search_symbol(self, query: str) -> list[dict]:
        """Find symbols matching query."""
        results = []
        for n in self.graph.nodes():
            label = self.graph.nodes[n].get('label', '')
            if query.lower() in label.lower():
                results.append(self.graph.nodes[n])
        return results
    
    def get_callers(self, symbol_id: str) -> list[dict]:
        """Get functions that call this symbol."""
        callers = []
        for c in self.graph.predecessors(symbol_id):
            attrs = self.graph.nodes[c]
            if '()' in attrs.get('label', ''):  # Only functions
                callers.append(attrs)
        return callers
    
    def get_callees(self, symbol_id: str) -> list[dict]:
        """Get functions this symbol calls."""
        callees = []
        for c in self.graph.successors(symbol_id):
            attrs = self.graph.nodes[c]
            if '()' in attrs.get('label', ''):
                callees.append(attrs)
        return callees
    
    def get_call_path(self, source: str, target: str) -> list[str]:
        """Get shortest call path between two symbols."""
        if nx.has_path(self.graph, source, target):
            return nx.shortest_path(self.graph, source, target)
        return []
```

## Key Insight: Scope Division

| Scope | CodeGraph | Forge HTTP Layer |
|-------|-----------|------------------|
| **Intra-service** (within a repo) | ✅ Yes | ❌ Redundant |
| **Inter-service** (between repos) | ❌ No | ✅ Yes |

**CodeGraph** understands:
```
processPayment() → calls → validatePayment()     ✅
processPayment() → calls → createPaymentRecord() ✅
```

**CodeGraph does NOT understand:**
```
processPayment() → fetch('http://account-service/...') → ??? 
                   ↑ Sees fetch() but doesn't know it's calling another service
```

**Forge HTTP Layer fills the gap:**
```
payment-processor ──HTTP_CALLS──> account-service:/accounts
gateway-service   ──HTTP_CALLS──> payment-processor:/payments
```

---

## Next Steps (TODO)

### Step 1: Build Multi-Repo Indexer

```python
# forge/src/modules/codegraph/indexer.py

from codegraph.extract import extract, collect_files
from codegraph.build import build
from pathlib import Path

def index_all_repos(repos: list[str], output_dir: str) -> dict:
    """
    Run CodeGraph on multiple repos, save individual + combined extractions.
    
    Args:
        repos: List of repo paths ['./services/payment-processor', './services/account-service', ...]
        output_dir: Where to save extraction JSONs
    
    Returns:
        Combined extraction dict with all symbols from all repos
    """
    all_extractions = []
    
    for repo_path in repos:
        # Collect files (exclude node_modules)
        files = collect_files(Path(repo_path))
        code_files = [f for f in files if f.suffix in ['.js', '.ts', '.py', '.java'] 
                      and 'node_modules' not in str(f)]
        
        # Extract symbols
        extraction = extract(code_files)
        
        # Tag nodes with repo name for cross-repo identification
        repo_name = Path(repo_path).name
        for node in extraction['nodes']:
            node['repo'] = repo_name
        for edge in extraction['edges']:
            edge['repo'] = repo_name
        
        all_extractions.append(extraction)
        
        # Save individual repo extraction
        save_json(extraction, f"{output_dir}/{repo_name}_extraction.json")
    
    # Merge all extractions
    combined = merge_extractions(all_extractions)
    save_json(combined, f"{output_dir}/combined_extraction.json")
    
    return combined
```

### Step 2: Build HTTP Service Linker

```python
# forge/src/modules/codegraph/http_linker.py

import re
from pathlib import Path

def find_http_routes(repo_path: str) -> list[dict]:
    """
    Scan repo for HTTP route definitions.
    
    Patterns detected:
    - app.get('/path', handler)
    - router.post('/path', ...)
    - @app.route('/path')
    - @GetMapping('/path')
    """
    routes = []
    patterns = [
        r"app\.(get|post|put|delete|patch)\s*\(\s*['\"]([^'\"]+)['\"]",
        r"router\.(get|post|put|delete|patch)\s*\(\s*['\"]([^'\"]+)['\"]",
        r"@(Get|Post|Put|Delete)Mapping\s*\(\s*['\"]([^'\"]+)['\"]",
    ]
    
    for file in Path(repo_path).rglob('*.js'):
        if 'node_modules' in str(file):
            continue
        content = file.read_text()
        for pattern in patterns:
            for match in re.finditer(pattern, content):
                routes.append({
                    'method': match.group(1).upper(),
                    'path': match.group(2),
                    'file': str(file),
                    'repo': Path(repo_path).name
                })
    
    return routes


def find_http_calls(repo_path: str, service_urls: dict) -> list[dict]:
    """
    Scan repo for HTTP calls to other services.
    
    Patterns detected:
    - fetch('http://service-name/...')
    - axios.get('http://service-name/...')
    - http.request({url: 'http://...'})
    
    Args:
        service_urls: Mapping of URL patterns to service names
                      {'account-service': ['localhost:3001', 'account-service']}
    """
    calls = []
    patterns = [
        r"fetch\s*\(\s*['\"`]([^'\"`]+)['\"`]",
        r"axios\.(get|post|put|delete)\s*\(\s*['\"`]([^'\"`]+)['\"`]",
        r"http\.request\s*\([^)]*url:\s*['\"`]([^'\"`]+)['\"`]",
    ]
    
    for file in Path(repo_path).rglob('*.js'):
        if 'node_modules' in str(file):
            continue
        content = file.read_text()
        for pattern in patterns:
            for match in re.finditer(pattern, content):
                url = match.group(1) if match.lastindex == 1 else match.group(2)
                target_service = resolve_service_from_url(url, service_urls)
                if target_service:
                    calls.append({
                        'source_repo': Path(repo_path).name,
                        'target_service': target_service,
                        'url': url,
                        'file': str(file)
                    })
    
    return calls


def link_all_services(repos: list[str], service_urls: dict) -> list[dict]:
    """
    Build HTTP edges between all services.
    
    Returns:
        List of edges: [
            {'source': 'gateway-service', 'target': 'payment-processor', 
             'route': '/payments', 'relation': 'HTTP_CALLS'}
        ]
    """
    http_edges = []
    
    for repo_path in repos:
        calls = find_http_calls(repo_path, service_urls)
        for call in calls:
            http_edges.append({
                'source': call['source_repo'],
                'target': call['target_service'],
                'url': call['url'],
                'relation': 'HTTP_CALLS',
                'source_file': call['file']
            })
    
    return http_edges
```

### Step 3: Build Unified Graph Adapter

```python
# forge/src/modules/codegraph/adapter.py

from codegraph.build import build
import networkx as nx

class UnifiedGraphAdapter:
    """
    Combines CodeGraph symbol graph with Forge HTTP service topology.
    Provides unified query API for impact analysis.
    """
    
    def __init__(self, extraction_path: str, http_edges: list[dict]):
        # Load CodeGraph symbol graph
        with open(extraction_path) as f:
            extraction = json.load(f)
        self.symbol_graph = build([extraction], directed=True)
        
        # Build service topology graph
        self.service_graph = nx.DiGraph()
        for edge in http_edges:
            self.service_graph.add_edge(
                edge['source'], 
                edge['target'],
                route=edge.get('url'),
                relation='HTTP_CALLS'
            )
    
    def search_symbol(self, query: str) -> list[dict]:
        """Find symbols matching query across all repos."""
        results = []
        for n in self.symbol_graph.nodes():
            attrs = self.symbol_graph.nodes[n]
            if query.lower() in attrs.get('label', '').lower():
                results.append(attrs)
        return results
    
    def get_internal_callers(self, symbol_id: str) -> list[dict]:
        """Get callers WITHIN the same service (CodeGraph)."""
        callers = []
        for c in self.symbol_graph.predecessors(symbol_id):
            attrs = self.symbol_graph.nodes[c]
            if '()' in attrs.get('label', ''):
                callers.append(attrs)
        return callers
    
    def get_external_callers(self, service: str) -> list[str]:
        """Get services that call this service via HTTP (Forge)."""
        return list(self.service_graph.predecessors(service))
    
    def trace_full_impact(self, symbol_id: str) -> dict:
        """
        Get complete impact chain: internal + external callers.
        
        Returns:
            {
                'symbol': 'processPayment()',
                'service': 'payment-processor',
                'internal_callers': [...functions in same service...],
                'external_callers': [...services calling via HTTP...],
                'http_routes_affected': ['/payments']
            }
        """
        attrs = self.symbol_graph.nodes.get(symbol_id, {})
        service = self._get_service_from_file(attrs.get('source_file', ''))
        
        return {
            'symbol': attrs.get('label'),
            'service': service,
            'file': attrs.get('source_file'),
            'internal_callers': self.get_internal_callers(symbol_id),
            'external_callers': self.get_external_callers(service),
            'call_chain': self._build_call_chain(symbol_id, service)
        }
    
    def _get_service_from_file(self, file_path: str) -> str:
        """Extract service name from file path."""
        parts = file_path.replace('\\', '/').split('/')
        return parts[0] if parts else 'unknown'
    
    def _build_call_chain(self, symbol_id: str, service: str) -> list[dict]:
        """Build layered impact chain."""
        chain = []
        
        # Layer 0: The changed symbol
        chain.append({
            'layer': 0,
            'type': 'direct',
            'items': [{'symbol': symbol_id, 'service': service}]
        })
        
        # Layer 1: Internal callers
        internal = self.get_internal_callers(symbol_id)
        if internal:
            chain.append({
                'layer': 1,
                'type': 'internal_callers',
                'items': internal
            })
        
        # Layer 2: External service callers
        external = self.get_external_callers(service)
        if external:
            chain.append({
                'layer': 2,
                'type': 'http_callers',
                'items': [{'service': s} for s in external]
            })
        
        return chain
```

### Step 4: Integrate with Forge Impact Agent

```python
# Update forge/src/modules/agents/impact/tools.py

from forge.src.modules.codegraph.adapter import UnifiedGraphAdapter

def get_graph_tools(adapter: UnifiedGraphAdapter) -> list[dict]:
    """Return tools that use the unified graph."""
    
    return [
        {
            "name": "search_symbol",
            "description": "Search for functions/symbols across all microservices",
            "function": adapter.search_symbol
        },
        {
            "name": "trace_callers", 
            "description": "Find all callers of a symbol (internal + cross-service)",
            "function": lambda sym: {
                'internal': adapter.get_internal_callers(sym),
                'external': adapter.get_external_callers(adapter._get_service_from_file(
                    adapter.symbol_graph.nodes.get(sym, {}).get('source_file', '')
                ))
            }
        },
        {
            "name": "get_full_impact",
            "description": "Get complete impact analysis for a symbol change",
            "function": adapter.trace_full_impact
        }
    ]
```

### Step 5: Test End-to-End

```python
# Test script: test_unified_graph.py

# 1. Index all repos
extraction = index_all_repos([
    './services/payment-processor',
    './services/account-service', 
    './services/gateway-service',
    './services/audit-service',
    # ... more repos
], output_dir='./codegraph-out')

# 2. Build HTTP edges
http_edges = link_all_services(repos, service_urls={
    'payment-processor': ['localhost:3002', 'payment-processor'],
    'account-service': ['localhost:3001', 'account-service'],
    # ...
})

# 3. Create unified adapter
adapter = UnifiedGraphAdapter(
    extraction_path='./codegraph-out/combined_extraction.json',
    http_edges=http_edges
)

# 4. Test impact query
result = adapter.trace_full_impact('orchestrator_paymentorchestrator_processpayment')
print(result)
# Expected:
# {
#   'symbol': '.processPayment()',
#   'service': 'payment-processor',
#   'internal_callers': [validatePayment, createRecord, ...],
#   'external_callers': ['gateway-service'],
#   'call_chain': [Layer0, Layer1, Layer2]
# }
```

---

## File Structure (After Implementation)

```
forge/
├── src/
│   └── modules/
│       └── codegraph/              # NEW MODULE
│           ├── __init__.py
│           ├── indexer.py          # Multi-repo CodeGraph extraction
│           ├── http_linker.py      # HTTP route/call detection  
│           ├── adapter.py          # Unified graph query API
│           └── tools.py            # LLM tool wrappers
├── docs/
│   └── CODEGRAPH_INTEGRATION.md    # This file
└── codegraph-out/                  # Generated outputs
    ├── payment-processor_extraction.json
    ├── account-service_extraction.json
    ├── combined_extraction.json
    └── http_edges.json
```

---

## Summary

| Component | Purpose | Status |
|-----------|---------|--------|
| CodeGraph | Symbol extraction per repo | ✅ Working |
| HTTP Linker | Cross-service connections | ✅ Exists in Forge |
| Unified Adapter | Merge both graphs | 🔲 TODO |
| LLM Tools | Expose to Impact Agent | 🔲 TODO |
| End-to-End Test | Verify full chain | 🔲 TODO |

**Tomorrow's Work:**
1. Create `forge/src/modules/codegraph/` module
2. Implement `indexer.py` - multi-repo extraction
3. Implement `adapter.py` - unified query API
4. Wire into existing Impact Agent
5. Test with "change processPayment()" scenario
