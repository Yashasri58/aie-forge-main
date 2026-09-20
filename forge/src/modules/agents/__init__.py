"""
Impact Analysis Pipeline (Google ADK)

All agents use Google ADK with Gemini:

    ContextGathererAgent  → Clarifies requirements via conversation
    ImpactAgent           → Produces layered impact report (uses CodeGraphTools + Cypher)
    VerificationAgent     → Checks completeness at all levels
    
    Loop: ImpactAgent ↔ VerificationAgent until all paths traced (max 3x)

Tools (used by ImpactAgent):
    - search_symbols      → Find functions by name
    - analyze_impact      → Full impact analysis
    - trace_call_path     → Follow call chains
    - get_service_topology→ HTTP dependencies
    - query_cypher        → Raw Kuzu Cypher queries
"""

from .base import BaseADKAgent
from .context_gatherer import ContextGathererAgent, RequirementsOutput
from .verification_agent import VerificationAgent
from .orchestrator import PipelineOrchestrator, PipelineState, PipelineStage

from .impact.agent import ImpactAgent

__all__ = [
    # Base
    "BaseADKAgent",
    
    # Agents
    "ContextGathererAgent",
    "ImpactAgent",
    "VerificationAgent",
    
    # Types
    "RequirementsOutput",
    
    # Orchestrator
    "PipelineOrchestrator",
    "PipelineState",
    "PipelineStage",
]
