"""
CodeGraph module - graph-based code analysis using codegraph-tools + Kuzu.

Architecture:
- codegraph-tools: Extracts code AST → JSON
- Kuzu: Persistent graph database for queries
- CodeGraphTools: Tool interface for agents

Usage:
    from modules.codegraph import KuzuCodeGraphStore, CodeGraphTools
    
    store = KuzuCodeGraphStore('path/to/db.kuzu')
    store.init_schema()
    store.load_extraction('extraction.json')
    
    tools = CodeGraphTools(kuzu_store=store)
    tools.search_symbols('validate')
    tools.analyze_impact('processPayment')
"""

from .kuzu_store import KuzuCodeGraphStore
from .tools import CodeGraphTools
from .indexer import CodeGraphIndexer
from .http_linker import HttpLinker
from .enricher import CodeGraphEnricher

__all__ = [
    "KuzuCodeGraphStore",
    "CodeGraphTools",
    "CodeGraphIndexer",
    "HttpLinker",
    "CodeGraphEnricher",
]
