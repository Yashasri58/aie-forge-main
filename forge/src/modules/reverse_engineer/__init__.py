"""
Reverse Engineer module.

Pipeline 3 — Reverse engineers third-party application behavior
from log files, producing structured specification documents.

Usage:
    from modules.reverse_engineer import REOrchestrator, RESession, REStage
"""

from .orchestrator import REOrchestrator
from .schemas import RESession, REStage, SpecSection, ExtractedFacts, Confidence, SPEC_SECTIONS

__all__ = [
    "REOrchestrator",
    "RESession",
    "REStage",
    "SpecSection",
    "ExtractedFacts",
    "Confidence",
    "SPEC_SECTIONS",
]
