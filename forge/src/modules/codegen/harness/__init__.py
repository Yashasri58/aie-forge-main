"""
Forge Verification Harness
==========================

A comprehensive, deterministic verification pipeline for LLM-generated code.
Inspired by research on AST gating, negative constraints, and hallucination detection.

Pipeline Tiers (fail-fast):
- Tier 1 (ms): Syntax validation (vallm/tree-sitter), Import resolution
- Tier 2 (seconds): Security scanning (vallm + our patterns), Contract checking, Complexity (vallm/lizard)
- Tier 3 (seconds): Hallucination detection, Negative constraints

Key Principles:
1. Never trust LLM self-assessment - use deterministic external checks
2. AST-based validation catches issues linters miss
3. Negative constraints define explicit failure bounds
4. Fail fast - Tier 1 errors stop execution immediately

Integration:
- vallm: Syntax (tree-sitter), Complexity (lizard), Security (base patterns)
- Our checks: Import paths, Hallucination, Contracts, Negative Constraints, Security (extended)

References:
- "Detecting and Correcting Hallucinations in LLM-Generated Code via Deterministic AST Analysis"
- "How to Build Zero-Hallucination AI Agents: Negative Constraint Assertions and AST Gating"
- vallm: A complete toolkit for validating LLM-generated code (https://github.com/semcod/vallm)
"""

from .models import (
    HarnessResult,
    HarnessViolation,
    ViolationSeverity,
    CheckType,
    FileDiff,
)
from .syntax_checker import SyntaxChecker
from .import_resolver import ImportResolver
from .hallucination_detector import HallucinationDetector
from .security_scanner import SecurityScanner
from .contract_checker import ContractChecker
from .negative_constraints import NegativeConstraintChecker
from .gate import DeterministicGate, GateConfig
from .vallm_adapter import VallmAdapter, VallmConfig, VALLM_AVAILABLE

__all__ = [
    # Models
    "HarnessResult",
    "HarnessViolation", 
    "ViolationSeverity",
    "CheckType",
    "FileDiff",
    # Checkers
    "SyntaxChecker",
    "ImportResolver",
    "HallucinationDetector",
    "SecurityScanner",
    "ContractChecker",
    "NegativeConstraintChecker",
    # Gate
    "DeterministicGate",
    "GateConfig",
    # vallm integration
    "VallmAdapter",
    "VallmConfig",
    "VALLM_AVAILABLE",
]
