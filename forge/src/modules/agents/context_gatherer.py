"""
Context Gatherer Agent (Google ADK)

Clarifies vague requirements through conversation.
Uses graph tools to show available services.
"""

from typing import TypedDict, Optional
from .base import BaseADKAgent


class RequirementsOutput(TypedDict):
    """Structured requirements from conversation."""
    complete: bool
    clarity_score: int
    description: str
    services: list[str]
    functions: list[str]
    change_type: str
    constraints: list[str]
    follow_up_question: Optional[str]


# Module-level tools instance
_graph_tools = None


def get_available_services() -> dict:
    """Get list of available services in the codebase."""
    if _graph_tools:
        return {"services": _graph_tools.services}
    return {"services": []}


def search_functions(query: str, service: str = None) -> dict:
    """Search for functions by name."""
    if _graph_tools:
        return _graph_tools.search_symbols(query, kind="function", service=service)
    return {"matches": []}


def get_function_impact_summary(function_name: str) -> dict:
    """
    Get a quick impact summary for a function - how many callers, which services.
    Useful to warn user about scope of their change.
    """
    if not _graph_tools:
        return {"error": "Graph tools not available"}
    
    try:
        impact = _graph_tools.analyze_impact(function_name)
        if "error" in impact:
            return {"error": impact["error"]}
        
        return {
            "function": function_name,
            "service": impact.get("symbol", {}).get("service", "unknown"),
            "caller_count": len(impact.get("direct_callers", [])),
            "callers_preview": [c.get("name", "?") for c in impact.get("direct_callers", [])[:5]],
            "affected_services": impact.get("affected_services", []),
            "risk_level": impact.get("risk_level", "UNKNOWN"),
        }
    except Exception as e:
        return {"error": str(e)}


def get_service_overview(service_name: str) -> dict:
    """
    Get overview of a service - function count, dependencies, HTTP routes.
    Helps user understand what they're working with.
    """
    if not _graph_tools:
        return {"error": "Graph tools not available"}
    
    try:
        # Get symbols in service
        symbols = _graph_tools.search_symbols("", service=service_name)
        symbol_count = symbols.get("count", 0)
        
        # Get HTTP topology
        topology = _graph_tools.get_service_topology(service_name)
        
        # Extract dependencies
        http_calls = topology.get("http_calls", [])
        calls_to = list(set(c.get("target", "") for c in http_calls if c.get("source") == service_name))
        called_by = list(set(c.get("source", "") for c in http_calls if c.get("target") == service_name))
        
        return {
            "service": service_name,
            "function_count": symbol_count,
            "calls_services": calls_to,
            "called_by_services": called_by,
            "is_critical": len(called_by) > 2,  # Many dependents = critical
        }
    except Exception as e:
        return {"error": str(e)}


def get_service_enrichment(service_name: str) -> dict:
    """
    Get enrichment details for a service: npm packages, DB tables, API endpoints,
    and environment variables it reads.

    Use this to give the user a richer picture of what a service owns before
    they confirm their requirement. Helps surface hidden impact:
    - If the change touches DB interactions, show which tables the service owns
    - If the change involves HTTP config, show which env vars are used
    - If the change is about dependencies, show which npm packages are used
    """
    if not _graph_tools:
        return {"error": "Graph tools not available"}

    try:
        store = _graph_tools._store

        # npm packages
        pkg_rows = store.query(
            "MATCH (s:Service)-[r:DEPENDS_ON]->(p:Package) WHERE s.name = $svc "
            "RETURN p.name AS pkg, r.version AS ver, r.dep_type AS dt",
            {"svc": service_name}
        )
        packages = [
            f"{r['pkg']}@{r['ver']}" for r in pkg_rows if r.get("dt") == "runtime"
        ]

        # DB tables
        tbl_rows = store.query(
            "MATCH (s:Service)-[:OWNS_TABLE]->(t:DbTable) WHERE s.name = $svc "
            "RETURN t.table_name AS tbl",
            {"svc": service_name}
        )
        tables = [r["tbl"] for r in tbl_rows]

        # OpenAPI endpoints count
        ep_rows = store.query(
            "MATCH (s:Service)-[:EXPOSES_ENDPOINT]->(e:ApiEndpoint) WHERE s.name = $svc "
            "RETURN e.method AS m, e.path AS p",
            {"svc": service_name}
        )
        endpoints = [f"{r['m']} {r['p']}" for r in ep_rows]

        # Env vars
        ev_rows = store.query(
            "MATCH (s:Service)-[:READS_ENV]->(e:EnvVar) WHERE s.name = $svc "
            "RETURN e.name AS var",
            {"svc": service_name}
        )
        env_vars = [r["var"] for r in ev_rows]

        return {
            "service": service_name,
            "runtime_packages": packages,
            "db_tables_owned": tables,
            "api_endpoints": endpoints,
            "env_vars_used": env_vars,
            "warnings": _build_enrichment_warnings(tables, env_vars, packages),
        }
    except Exception as e:
        return {"error": str(e)}


def _build_enrichment_warnings(tables: list, env_vars: list, packages: list) -> list[str]:
    """Generate contextual warnings based on enrichment data."""
    warnings = []
    if tables:
        warnings.append(
            f"This service owns {len(tables)} DB table(s): {', '.join(tables)}. "
            "Schema changes will affect stored data."
        )
    if any("URL" in v for v in env_vars):
        url_vars = [v for v in env_vars if "URL" in v]
        warnings.append(
            f"This service reads service URLs from env vars: {', '.join(url_vars)}. "
            "Changes to downstream services may require config updates."
        )
    if "axios" in packages or "node-fetch" in packages:
        warnings.append(
            "This service makes HTTP calls via axios/fetch. "
            "HTTP client changes affect all outgoing calls."
        )
    return warnings


INSTRUCTION = """You are a requirements clarification agent. Your job is to understand what code change the user wants to make.

TOOLS AVAILABLE:
- get_available_services(): See what services exist in the codebase
- search_functions(query, service): Find functions by name
- get_function_impact_summary(function_name): Get caller count, affected services, risk level for a function
- get_service_overview(service_name): Get function count, HTTP dependencies, and whether service is critical
- get_service_enrichment(service_name): Get npm packages, DB tables, API endpoints, and env vars for a service

WORKFLOW:
1. If the user's requirement is vague, use get_available_services() to show them options
2. If they mention a function, use search_functions() to verify it exists
3. Use get_function_impact_summary() to warn them about high-impact changes
4. Use get_service_overview() to show HTTP dependencies when targeting a service
5. Use get_service_enrichment() to surface DB tables, packages, env vars the service owns
6. Ask focused questions until you have: service name, function name (if applicable), and what change to make

PROACTIVE WARNINGS (surface these to the user proactively):
- If a function has >3 callers: "This function is called by X places, changes will affect all of them"
- If a service is called by >2 other services: "This is a critical service with multiple dependents"
- If risk_level is HIGH: mention it explicitly
- If get_service_enrichment returns warnings: relay them to the user
  e.g. "Note: payment-processor owns 2 DB tables (payments, payment_status_history).
        If your change touches data storage, schema changes will be needed."
  e.g. "Note: gateway-service reads ACCOUNT_SERVICE_URL and AUDIT_SERVICE_URL from env.
        Config updates may be needed alongside code changes."

OUTPUT FORMAT:
When you have enough information (or are asking a question), respond with ONLY this JSON:
{
    "complete": boolean,           // true if ready for analysis
    "clarity_score": number,       // 1-10
    "description": "string",       // what they want to do
    "services": ["service-name"],  // target services
    "functions": ["functionName"], // target functions (if known)
    "change_type": "add_feature|modify|refactor|delete",
    "constraints": [],             // any mentioned constraints
    "follow_up_question": "string or null"  // question if complete=false
}

RULES:
- Set complete=true only when you know the service and have a clear description
- Ask ONE question at a time
- Use tools to provide helpful suggestions and context
- Proactively warn about high-impact changes using enrichment data
- Output ONLY the JSON, no other text"""


class ContextGathererAgent(BaseADKAgent):
    """
    Clarifies requirements through conversation using ADK.
    """
    
    name = "context_gatherer"
    instruction = INSTRUCTION
    
    def __init__(self, graph_tools=None):
        super().__init__()
        global _graph_tools
        _graph_tools = graph_tools
        self._conversation: list[dict] = []
        self._current: dict = {}
    
    def _get_tools(self) -> list:
        return [
            get_available_services,
            search_functions,
            get_function_impact_summary,
            get_service_overview,
            get_service_enrichment,
        ]
    
    def reset(self):
        """Reset for new conversation."""
        self._conversation = []
        self._current = {}
        self.reset_session()
    
    async def process(self, input_data: dict) -> RequirementsOutput:
        """
        Process user message.
        
        Args:
            input_data: {"message": str, "is_initial": bool}
        """
        message = input_data.get("message", "")
        is_initial = input_data.get("is_initial", False)
        
        self._conversation.append({"role": "user", "content": message})
        
        # Build prompt
        if is_initial:
            prompt = f"User requirement: {message}"
        else:
            history = "\n".join([
                f"{'User' if m['role'] == 'user' else 'You'}: {m['content']}"
                for m in self._conversation[:-1]
            ])
            prompt = f"Conversation so far:\n{history}\n\nUser's latest message: {message}"
        
        # Run agent
        response = await self.run(prompt)
        
        # Parse response
        result = self.parse_json(response)
        
        output: RequirementsOutput = {
            "complete": result.get("complete", False),
            "clarity_score": result.get("clarity_score", 1),
            "description": result.get("description", message),
            "services": result.get("services", []),
            "functions": result.get("functions", []),
            "change_type": result.get("change_type", "modify"),
            "constraints": result.get("constraints", []),
            "follow_up_question": result.get("follow_up_question"),
        }
        
        if output["follow_up_question"]:
            self._conversation.append({
                "role": "assistant",
                "content": output["follow_up_question"]
            })
        
        self._current = output
        return output
    
    def get_conversation_history(self) -> list[dict]:
        return self._conversation.copy()
