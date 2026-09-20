"""
Impact Analysis API Router.

All endpoints related to code impact analysis.
"""

import uuid
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

router = APIRouter(prefix="/impact", tags=["Impact Analysis"])


# =============================================================================
# MODELS
# =============================================================================

class AnalyzeRequest(BaseModel):
    """Request for natural language analysis."""
    query: str = Field(..., description="Natural language query", example="What breaks if I change validatePayment?")


class AnalyzeResponse(BaseModel):
    """Response from the agent."""
    query: str
    response: str


class ImpactResponse(BaseModel):
    """Impact analysis result."""
    symbol: dict
    affected_services: list
    risk_level: str
    testing_recommendation: str
    explanation: str


class SearchRequest(BaseModel):
    """Request for symbol search."""
    query: str = Field(..., description="Search pattern")
    kind: Optional[str] = Field(None, description="Filter by kind: function, class, method")
    service: Optional[str] = Field(None, description="Filter by service name")


class QueryRequest(BaseModel):
    """Request for custom Cypher query."""
    cypher: str = Field(..., description="Cypher query string")


class TopologyResponse(BaseModel):
    """Service topology response."""
    services: list
    dependencies: list
    outgoing: dict
    incoming: dict
    summary: str


class ChatMessage(BaseModel):
    """Single chat message."""
    role: str   # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    """Send a message in a chat session."""
    message: str
    session_id: Optional[str] = Field(None, description="Omit to start a new session")


class ChatResponse(BaseModel):
    """Chat turn response."""
    session_id: str
    message: str
    history: list[ChatMessage]
    impacted_services: Optional[list] = None


# ponytail: simple in-memory store, no persistence needed for a demo
# ceiling: lost on server restart; upgrade path: redis or sqlite
_sessions: dict[str, list[ChatMessage]] = {}


# =============================================================================
# DEPENDENCIES (set by main.py)
# =============================================================================

_agent = None
_tools = None


def set_dependencies(agent, tools):
    """Set the agent and tools instances."""
    global _agent, _tools
    _agent = agent
    _tools = tools


def get_tools():
    if not _tools:
        raise HTTPException(status_code=503, detail="Graph not loaded")
    return _tools


def get_agent():
    if not _agent:
        raise HTTPException(
            status_code=503,
            detail="Agent not available. Set GOOGLE_API_KEY environment variable."
        )
    return _agent


# =============================================================================
# ENDPOINTS
# =============================================================================

@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(request: AnalyzeRequest):
    """
    Analyze a natural language query using the LLM agent.
    
    Example queries:
    - "What breaks if I change validatePayment?"
    - "Show me the dependencies of payment-processor"
    - "Find all validation functions"
    """
    agent = get_agent()
    
    try:
        response = await agent.analyze(request.query)
        return AnalyzeResponse(query=request.query, response=response)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/symbol/{symbol}", response_model=ImpactResponse)
async def get_symbol_impact(symbol: str):
    """
    Get impact analysis for a specific symbol.
    
    Returns affected services, risk level, and testing recommendations.
    No LLM required - direct graph query.
    """
    tools = get_tools()
    result = tools.analyze_impact(symbol)
    
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    
    return ImpactResponse(
        symbol=result["symbol"],
        affected_services=result["affected_services"],
        risk_level=result["risk_level"],
        testing_recommendation=result["testing_recommendation"],
        explanation=result["explanation"]
    )


@router.get("/topology", response_model=TopologyResponse)
async def get_topology(service: Optional[str] = None):
    """
    Get service dependency topology.
    
    Optionally filter by a specific service.
    """
    tools = get_tools()
    result = tools.get_service_topology(service)
    
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    
    return TopologyResponse(
        services=result["services"],
        dependencies=result["dependencies"],
        outgoing=result["outgoing"],
        incoming=result["incoming"],
        summary=result["summary"]
    )


@router.post("/search")
async def search_symbols(request: SearchRequest):
    """
    Search for symbols by name pattern.
    
    Optionally filter by kind (function, class, method) and service.
    """
    tools = get_tools()
    return tools.search_symbols(request.query, request.kind, request.service)


@router.post("/query")
async def execute_query(request: QueryRequest):
    """
    Execute a custom Cypher query against the code graph.
    
    Example:
    ```cypher
    MATCH (s:Symbol)-[:CALLS]->(t:Symbol) 
    WHERE s.name = 'processPayment' 
    RETURN t.name, t.repo_id
    ```
    """
    tools = get_tools()
    result = tools.query_graph(request.cypher)
    
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    
    return result


@router.get("/trace/{symbol}")
async def trace_calls(
    symbol: str,
    direction: str = Query(default="outgoing", pattern="^(outgoing|incoming|both)$"),
    depth: int = Query(default=3, ge=1, le=6)
):
    """
    Trace call chains from/to a symbol.
    
    Args:
        symbol: Function name to trace
        direction: 'outgoing' (what it calls), 'incoming' (what calls it), or 'both'
        depth: How many hops to traverse (1-6)
    """
    tools = get_tools()
    result = tools.trace_call_path(symbol, direction, depth)
    
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    
    return result



@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Multi-turn chat session with the Impact Agent.

    - Omit session_id to start a new session.
    - Reuse the returned session_id to continue the conversation.
    - The agent accumulates context across turns and returns
      impacted_services once it has enough information.
    """
    agent = get_agent()
    tools = get_tools()

    # Create or retrieve session
    session_id = request.session_id or str(uuid.uuid4())
    history: list[ChatMessage] = _sessions.setdefault(session_id, [])

    # Append user message
    history.append(ChatMessage(role="user", content=request.message))

    # Build prompt: full history so the agent has context
    full_prompt = "\n\n".join(
        f"{'User' if m.role == 'user' else 'Assistant'}: {m.content}"
        for m in history
    )

    try:
        response_text = await agent.analyze(full_prompt)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    history.append(ChatMessage(role="assistant", content=response_text))

    # Try to extract impacted services from the graph for display
    impacted = None
    try:
        # Quick heuristic: look for service names in the response
        svc_result = tools.get_service_topology(None)
        known_services = {s["name"] for s in svc_result.get("services", [])}
        mentioned = [s for s in known_services if s.lower() in response_text.lower()]
        if mentioned:
            impacted = mentioned
    except Exception:
        pass

    return ChatResponse(
        session_id=session_id,
        message=response_text,
        history=list(history),
        impacted_services=impacted,
    )


@router.delete("/chat/{session_id}")
async def delete_session(session_id: str):
    """Clear a chat session."""
    _sessions.pop(session_id, None)
    return {"deleted": session_id}
