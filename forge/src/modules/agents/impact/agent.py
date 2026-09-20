"""
Impact Analysis Agent.

Google ADK agent that uses code graph tools to answer
"what breaks if I change X?" questions.

Tools available:
- CodeGraph tools: search_symbols, analyze_impact, trace_call_path, get_service_topology
- Kuzu Cypher: query_cypher (raw Cypher queries)
"""

import asyncio
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from .prompts import SYSTEM_INSTRUCTION

if TYPE_CHECKING:
    from modules.codegraph import CodeGraphTools, KuzuCodeGraphStore


# Module-level tool instances (set by ImpactAgent)
_tools: Optional["CodeGraphTools"] = None
_store: Optional["KuzuCodeGraphStore"] = None


# =============================================================================
# CODEGRAPH TOOL FUNCTIONS (high-level)
# =============================================================================

def get_schema() -> dict:
    """Get the graph schema to understand what can be queried.
    
    Returns node types, edge types, services list, and symbol count.
    Use this first to understand what's available.
    """
    return _tools.get_schema()


def search_symbols(query: str, kind: str = None, service: str = None) -> dict:
    """Search for symbols (functions, classes, methods) by name pattern.
    
    Args:
        query: Name or partial name to search (case-insensitive)
        kind: Filter by type: 'function', 'class', 'method'
        service: Filter by service name
    
    Returns:
        Matching symbols with name, kind, service, file, line
    """
    return _tools.search_symbols(query, kind, service)


def analyze_impact(symbol_name: str) -> dict:
    """Comprehensive impact analysis - THE key tool for "what breaks if I change X?"
    
    Args:
        symbol_name: The function/class to analyze
    
    Returns:
        - symbol: Info about the target symbol
        - direct_callers: Functions that call this symbol
        - outgoing_calls: Functions this symbol calls
        - affected_services: Services impacted by changes
        - risk_level: HIGH/MEDIUM/LOW based on blast radius
        - explanation: Human-readable impact summary
        - testing_recommendation: What to test
    """
    return _tools.analyze_impact(symbol_name)


def trace_call_path(start_symbol: str, direction: str = "outgoing", max_depth: int = 4) -> dict:
    """Trace call chains from or to a symbol.
    
    Args:
        start_symbol: Name of the function/method to start from
        direction: 'outgoing' (what does X call?) or 'incoming' (what calls X?)
        max_depth: How many hops to traverse (1-6, default 4)
    
    Returns:
        - paths: List of call chains with names and services
        - affected_services: All services in the call chains
        - total_paths: Number of paths found
    """
    return _tools.trace_call_path(start_symbol, direction, max_depth)


def get_service_topology(service_name: str = None) -> dict:
    """Get HTTP-level service dependencies.
    
    Args:
        service_name: Focus on a specific service, or None for full topology
    
    Returns:
        - services: All services
        - dependencies: HTTP call relationships
        - outgoing: Services each service calls
        - incoming: Services that call each service
    """
    return _tools.get_service_topology(service_name)


# =============================================================================
# KUZU CYPHER TOOL (low-level, raw queries)
# =============================================================================

def query_cypher(cypher_query: str) -> dict:
    """Execute a raw Cypher query against the Kuzu graph database.
    
    Use this for custom queries not covered by the high-level tools.
    
    Schema:
        Nodes:
        - Service(name, path)
        - Symbol(id, name, kind, file, start_line, end_line, service)
        - HttpRoute(id, service, method, path, handler)
        - Package(name)                          -- npm packages
        - DbTable(id, service, table_name)       -- SQLite tables owned by each service
        - ApiEndpoint(id, service, method, path, operation_id)  -- OpenAPI endpoints
        - EnvVar(name)                           -- environment variables read in code
        
        Relationships:
        - (Service)-[:CONTAINS]->(Symbol)
        - (Symbol)-[:CALLS]->(Symbol)
        - (Service)-[:EXPOSES]->(HttpRoute)
        - (Service)-[:HTTP_CALLS {method, path}]->(Service)
        - (Service)-[:DEPENDS_ON {version, dep_type}]->(Package)   -- npm deps
        - (Service)-[:OWNS_TABLE]->(DbTable)                       -- DB schemas
        - (Service)-[:EXPOSES_ENDPOINT]->(ApiEndpoint)             -- OpenAPI routes
        - (Service)-[:READS_ENV]->(EnvVar)                         -- env var usage
    
    Args:
        cypher_query: A Cypher query string. Examples:
            -- Function calls:
            MATCH (a:Symbol)-[:CALLS]->(b:Symbol) WHERE a.name = 'processPayment' RETURN b.name
            -- Which services use axios (CVE blast radius)?
            MATCH (s:Service)-[:DEPENDS_ON]->(p:Package) WHERE p.name = 'axios' RETURN s.name
            -- What tables does payment-processor own?
            MATCH (s:Service)-[:OWNS_TABLE]->(t:DbTable) WHERE s.name = 'payment-processor' RETURN t.table_name
            -- What env vars does gateway-service read?
            MATCH (s:Service)-[:READS_ENV]->(e:EnvVar) WHERE s.name = 'gateway-service' RETURN e.name
            -- All OpenAPI endpoints for a service:
            MATCH (s:Service)-[:EXPOSES_ENDPOINT]->(e:ApiEndpoint) WHERE s.name = 'payment-processor' RETURN e.method, e.path
    
    Returns:
        Query results (limited to 100 rows) with count
    """
    try:
        results = _store.query(cypher_query)
        return {
            "query": cypher_query,
            "results": results[:100],
            "total_count": len(results),
            "truncated": len(results) > 100
        }
    except Exception as e:
        return {
            "error": str(e),
            "query": cypher_query,
            "hint": "Check Cypher syntax. Use get_schema() to see valid node/edge types."
        }


# =============================================================================
# AGENT CREATION
# =============================================================================

def _create_agent() -> Agent:
    """Create the ADK agent with all tools."""
    return Agent(
        model="gemini-2.5-flash",
        name="forge_impact_agent",
        instruction=SYSTEM_INSTRUCTION,
        description="Analyzes code dependencies and impact of changes using graph queries",
        tools=[
            # High-level CodeGraph tools
            get_schema,
            search_symbols,
            analyze_impact,
            trace_call_path,
            get_service_topology,
            # Low-level Cypher access
            query_cypher,
        ],
    )


class ImpactAgent:
    """
    High-level facade for the Impact Analysis Agent.
    
    Usage:
        from modules.codegraph import KuzuCodeGraphStore, CodeGraphTools
        
        store = KuzuCodeGraphStore('path/to/db.kuzu')
        tools = CodeGraphTools(kuzu_store=store)
        
        agent = ImpactAgent(store, tools)
        response = await agent.analyze("What breaks if I change validatePayment?")
    """
    
    def __init__(self, graph_store, tools=None):
        """
        Args:
            graph_store: KuzuCodeGraphStore instance
            tools: CodeGraphTools instance (optional, created if not provided)
        """
        global _tools, _store
        
        self._store = graph_store
        _store = graph_store
        
        # Create tools if not provided
        if tools is None:
            from modules.codegraph import CodeGraphTools
            tools = CodeGraphTools(kuzu_store=graph_store)
        
        self._tools = tools
        _tools = tools
        
        self.agent = _create_agent()
        self.session_service = InMemorySessionService()
        self.runner = None
        self.session = None
    
    @property
    def services(self) -> list:
        """List of indexed services."""
        return _tools.services
    
    @property
    def symbol_count(self) -> int:
        """Number of indexed symbols."""
        return len(_tools.all_symbols)
    
    async def _ensure_session(self):
        """Ensure we have an active session."""
        if self.session is None:
            self.session = await self.session_service.create_session(
                app_name="forge_impact",
                user_id="developer"
            )
            self.runner = Runner(
                agent=self.agent,
                app_name="forge_impact",
                session_service=self.session_service
            )
    
    async def analyze(self, query: str) -> str:
        """Analyze a query and return the response."""
        await self._ensure_session()
        
        content = types.Content(
            role='user',
            parts=[types.Part(text=query)]
        )
        
        response_text = ""
        async for event in self.runner.run_async(
            user_id="developer",
            session_id=self.session.id,
            new_message=content
        ):
            if event.is_final_response() and event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:
                        response_text += part.text
        
        return response_text
    
    async def analyze_for_pipeline(self, requirements: dict, iteration: int = 1, previous_tasks: list = None) -> str:
        """
        Analyze impacts for the pipeline - returns the LAYERED REPORT directly.
        
        The agent queries the graph, traces paths, and produces the full
        human-readable report with layers, file changes, and execution order.
        
        Args:
            requirements: RequirementsOutput from Context Gatherer
            iteration: Current loop iteration (1-3)
            previous_tasks: Tasks from previous iteration (for chain analysis)
            
        Returns:
            Formatted layered impact report (string)
        """
        target_services = requirements.get("services", [])
        target_functions = requirements.get("functions", [])
        change_description = requirements.get("description", "")
        constraints = requirements.get("constraints", [])
        
        # Build the prompt that produces the layered report
        query = f"""Analyze the full impact of this requirement and produce a LAYERED IMPACT REPORT.

REQUIREMENT: "{change_description}"
TARGET SERVICES: {', '.join(target_services) if target_services else 'Determine from requirement'}
TARGET FUNCTIONS: {', '.join(target_functions) if target_functions else 'Determine from requirement'}
CONSTRAINTS: {', '.join(constraints) if constraints else 'None specified'}

INSTRUCTIONS:
1. Use search_symbols() to find the target functions
2. Use analyze_impact() on each target to find callers/callees  
3. Use trace_call_path() to find the full call chains
4. Use get_service_topology() to find HTTP dependencies
5. Use query_cypher() for any custom queries needed

Then produce a report in EXACTLY this format:

════════════════════════════════════════════════════════════════
LAYER 0 — Directly required by the requirement
════════════════════════════════════════════════════════════════

SERVICE: <service-name>  [conf: <0-100>%  evidence: <contract|call_graph|inferred>]
│
├── FILE: <file-path>
│   ├── <ADD|MODIFY|DELETE> <method|function|constant>: <name>
│   │   WHY: <why this change is needed>
│   │   CHANGE: <specific change to make>
│   └── ...
│
└── FILE: ...

SERVICE: <next-service> ...

════════════════════════════════════════════════════════════════
LAYER 1 — Secondary impact (callers of changed functions)
════════════════════════════════════════════════════════════════

SERVICE: <service-name>  [conf: <0-100>%  evidence: <type>]
│
│  WHY IN LAYER 1: 
│  <explain the call path that causes this service to be impacted>
│
└── FILE: ...

════════════════════════════════════════════════════════════════
LAYER 2 — Tertiary impact
════════════════════════════════════════════════════════════════

  No additional services affected. Cascade stops here.
  (OR list services if there are tertiary impacts)

════════════════════════════════════════════════════════════════
SHARED INTERFACE CHANGES (all services must agree on these)
════════════════════════════════════════════════════════════════

  New error code:  <CODE> (HTTP <status>)
  New event type:  <TYPE> in audit log
  Configurable:    <VAR>=<default>
                   (<description>)

════════════════════════════════════════════════════════════════
EXECUTION ORDER
════════════════════════════════════════════════════════════════

  1. <service>           ← <reason - e.g., no dependencies>
  2. <service>           ← depends on <service> <reason>
  3. ...

════════════════════════════════════════════════════════════════
SUMMARY
════════════════════════════════════════════════════════════════

  Layer 0 (direct):    X services  /  Y files  /  Z function changes
  Layer 1 (secondary): X services  /  Y files  /  Z function changes
  Layer 2 (tertiary):  X services

  Total: X services, Y files, Z function-level changes
  Confidence: HIGH|MEDIUM|LOW (<reason>)

RULES:
- Be SPECIFIC about file paths and function names from the graph
- Include the actual call paths that cause impacts
- Confidence should reflect how certain you are based on graph evidence
- Every change needs a WHY and ideally a CHANGE description
- Layer 0 = directly implementing the requirement
- Layer 1 = callers of Layer 0 functions that need updates
- Layer 2 = callers of Layer 1 (usually none or minimal)
"""
        
        if previous_tasks:
            query += f"""

ADDITIONAL CONTEXT (Iteration {iteration}):
Previous iteration identified these changes:
{chr(10).join(f'- {t.get("title", t.get("target_function", "unknown"))}' for t in previous_tasks)}

Check if these changes cause any ADDITIONAL impacts not already covered.
If no new impacts, state "No additional services affected" for Layer 1 and 2.
"""
        
        # Get response from ADK agent (which will use tools)
        report = await self.analyze(query)
        
        return report
    
    async def analyze_for_pipeline_json(self, requirements: dict, iteration: int = 1, previous_tasks: list = None) -> dict:
        """
        Analyze impacts and return structured JSON (for programmatic use).
        
        Use analyze_for_pipeline() for the human-readable report.
        """
        target_services = requirements.get("services", [])
        target_functions = requirements.get("functions", [])
        change_description = requirements.get("description", "")
        
        query = f"""Analyze impact of: {change_description}
Services: {', '.join(target_services) if target_services else 'Any'}
Functions: {', '.join(target_functions) if target_functions else 'Any'}

Use tools to find all affected components, then respond with ONLY this JSON:
{{
  "layers": [
    {{
      "level": 0,
      "title": "Directly required",
      "services": [
        {{
          "name": "service-name",
          "confidence": 95,
          "files": [
            {{
              "path": "src/...",
              "changes": [
                {{"action": "MODIFY", "symbol": "functionName", "why": "reason", "change": "detail"}}
              ]
            }}
          ]
        }}
      ]
    }}
  ],
  "shared_interfaces": {{
    "error_codes": [{{"code": "...", "http_status": 400}}],
    "event_types": ["..."],
    "config_vars": [{{"name": "...", "default": "...", "description": "..."}}]
  }},
  "execution_order": [
    {{"step": 1, "service": "...", "reason": "..."}}
  ],
  "summary": {{
    "total_services": 4,
    "total_files": 8,
    "total_changes": 10,
    "confidence": "HIGH",
    "confidence_reason": "all callers traced"
  }}
}}"""
        
        response_text = await self.analyze(query)
        
        # Parse JSON
        import json
        import re
        
        result = {"layers": [], "shared_interfaces": {}, "execution_order": [], "summary": {}}
        
        json_patterns = [
            r'```json\s*([\s\S]*?)\s*```',
            r'```\s*([\s\S]*?)\s*```',
            r'\{[\s\S]*"layers"[\s\S]*\}',
        ]
        
        for pattern in json_patterns:
            match = re.search(pattern, response_text)
            if match:
                try:
                    json_str = match.group(1) if '```' in pattern else match.group(0)
                    result = json.loads(json_str)
                    break
                except (json.JSONDecodeError, IndexError):
                    continue
        
        return result
    
    def get_tools(self) -> "CodeGraphTools":
        """Get the CodeGraphTools instance for direct access."""
        return _tools
    
    def get_graph_tools(self) -> "CodeGraphTools":
        """Get the CodeGraphTools instance (alias for get_tools)."""
        return _tools
    
    def get_store(self) -> "KuzuCodeGraphStore":
        """Get the KuzuCodeGraphStore instance for direct Cypher queries."""
        return _store
    
    async def run_interactive(self):
        """Run an interactive session."""
        await self._ensure_session()
        
        print("=" * 60)
        print("FORGE IMPACT AGENT")
        print("=" * 60)
        print(f"\nServices: {', '.join(self.services)}")
        print(f"Symbols: {self.symbol_count}")
        print("\nTools available:")
        print("  - search_symbols(query)     : Find functions by name")
        print("  - analyze_impact(symbol)    : Full impact analysis")
        print("  - trace_call_path(symbol)   : Follow call chains")
        print("  - get_service_topology()    : HTTP dependencies")
        print("  - query_cypher(cypher)      : Raw Cypher queries")
        print("\n" + "-" * 60)
        print("Ask about code impact, dependencies, or changes.")
        print("Type 'quit' to exit.")
        print("-" * 60)
        
        while True:
            try:
                user_input = input("\nYou: ").strip()
                
                if not user_input:
                    continue
                
                if user_input.lower() in ('quit', 'exit', 'q'):
                    print("\nGoodbye!")
                    break
                
                print("\nAgent: ", end="", flush=True)
                response = await self.analyze(user_input)
                # Handle Unicode for Windows console
                safe_response = response.replace('\u2192', '->').replace('\u2190', '<-')
                print(safe_response)
                
            except KeyboardInterrupt:
                print("\n\nInterrupted.")
                break
            except Exception as e:
                print(f"\nError: {e}")
