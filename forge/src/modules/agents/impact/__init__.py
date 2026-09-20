"""
Impact Analysis Agent Module.

Analyzes code dependencies to answer "what breaks if I change X?"

Tools:
- CodeGraph tools: search_symbols, analyze_impact, trace_call_path, get_service_topology
- Kuzu Cypher: query_cypher (raw Cypher queries)

Usage:
    from modules.codegraph import KuzuCodeGraphStore, CodeGraphTools
    from modules.agents.impact import ImpactAgent
    
    store = KuzuCodeGraphStore('path/to/db.kuzu')
    tools = CodeGraphTools(kuzu_store=store)
    
    agent = ImpactAgent(store, tools)
    response = await agent.analyze("What breaks if I change validatePayment?")
"""

from .agent import ImpactAgent

__all__ = ["ImpactAgent"]
