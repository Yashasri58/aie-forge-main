"""
Deterministic Gate
==================

The final gate that aggregates all harness checks and produces a pass/fail verdict.

Key principle from "How to Build Zero-Hallucination AI Agents":
- The Model is Stateless Compute: It proposes a candidate patch
- The Harness is Deterministic Truth: It executes local validation

This gate:
1. Runs all checks in order (fail-fast on Tier 1)
2. Aggregates results
3. Produces actionable feedback for the agent
4. Returns deterministic pass/fail verdict

Pipeline Tiers:
- Tier 1 (ms): Syntax, Imports - FAIL FAST (uses vallm tree-sitter)
- Tier 2 (seconds): Security, Contracts, Complexity
- Tier 3 (seconds): Hallucination, Negative Constraints

Integration:
- vallm: Syntax (tree-sitter), Complexity (lizard), Security (patterns)
- Our checks: Import resolution, Hallucination, Contracts, Negative Constraints
"""

import time
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from .models import (
    HarnessResult,
    HarnessViolation,
    ViolationSeverity,
    CheckType,
    FileDiff,
    CheckResult,
)
from .syntax_checker import SyntaxChecker
from .import_resolver import ImportResolver
from .hallucination_detector import HallucinationDetector
from .security_scanner import SecurityScanner
from .contract_checker import ContractChecker
from .negative_constraints import NegativeConstraintChecker
from .vallm_adapter import VallmAdapter, VallmConfig, VALLM_AVAILABLE

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from logging_config import harness_logger as logger


@dataclass
class GateConfig:
    """Configuration for the deterministic gate."""
    fail_fast: bool = True  # Stop on first Tier 1 error
    skip_security: bool = False
    skip_hallucination: bool = False
    skip_contracts: bool = False
    skip_constraints: bool = False
    skip_complexity: bool = False
    max_warnings: int = 20  # Cap warnings in output
    
    # vallm integration
    use_vallm: bool = True  # Use vallm when available
    vallm_syntax: bool = False  # Disable vallm tree-sitter — v0.1.94 rejects valid JS template literals (e.g. `${VAR}`) after diff apply; use Node --check instead
    vallm_complexity: bool = True  # Use vallm for complexity (lizard)
    vallm_security: bool = True  # Use vallm security patterns (complement ours)
    complexity_threshold: int = 15  # Max cyclomatic complexity


class DeterministicGate:
    """
    The deterministic verification gate.
    
    Runs all checks and produces a pass/fail verdict based on
    deterministic rules - NOT on LLM self-assessment.
    
    Integration strategy:
    - vallm: Syntax (tree-sitter), Complexity (lizard), Security (base patterns)
    - Our checks: Import paths, Hallucination, Contracts, Negative Constraints, Security (extended)
    
    Usage:
        gate = DeterministicGate(services_path)
        result = await gate.run(service_id, diffs, plan)
        
        if result.passed:
            # Safe to proceed
        else:
            # Use result.get_feedback_for_agent() for LLM retry
    """
    
    def __init__(
        self,
        services_path: str,
        graph_store=None,
        config: GateConfig = None
    ):
        """
        Args:
            services_path: Path to the services directory
            graph_store: Optional KuzuGraphStore for symbol lookups
            config: Gate configuration
        """
        self.services_path = services_path
        self.graph_store = graph_store
        self.config = config or GateConfig()
        
        # Initialize vallm adapter if available and enabled
        self.vallm_adapter = None
        if self.config.use_vallm and VALLM_AVAILABLE:
            vallm_config = VallmConfig(
                use_syntax=self.config.vallm_syntax,
                use_complexity=self.config.vallm_complexity,
                use_security=self.config.vallm_security,
                complexity_threshold=self.config.complexity_threshold,
            )
            self.vallm_adapter = VallmAdapter(vallm_config)
        
        # Initialize our checkers
        self.syntax_checker = SyntaxChecker()  # Fallback if vallm unavailable
        self.import_resolver = ImportResolver(services_path)
        self.hallucination_detector = HallucinationDetector(services_path, graph_store)
        self.security_scanner = SecurityScanner()  # Our extended patterns
        self.contract_checker = ContractChecker()
        self.constraint_checker = NegativeConstraintChecker()
    
    async def run(
        self,
        service_id: str,
        diffs: List[FileDiff],
        plan: Dict[str, Any] = None
    ) -> HarnessResult:
        """
        Run the full verification pipeline.
        
        Args:
            service_id: Service being checked
            diffs: List of file changes
            plan: Optional execution plan (for contract checking)
        
        Returns:
            HarnessResult with pass/fail verdict and violations
        """
        start_time = time.time()
        all_violations = []
        checks_run = []
        
        files_changed = [d.file_path for d in diffs]
        logger.info(f"[GATE] >> HARNESS START: service={service_id}, diffs={len(diffs)}, files={files_changed}")
        logger.debug(f"[GATE]    vallm_available={self.vallm_adapter is not None}, plan={'yes' if plan else 'no'}")
        
        # =========================================
        # TIER 1: Syntax & Imports (FAIL FAST)
        # =========================================
        
        # Syntax check - prefer vallm (tree-sitter) if available
        if self.vallm_adapter and self.config.vallm_syntax:
            logger.info(f"[GATE]    [T1] Syntax check via vallm (tree-sitter)...")
            syntax_result = self.vallm_adapter.check_syntax(service_id, diffs)
            checks_run.append("syntax:vallm")
        else:
            logger.info(f"[GATE]    [T1] Syntax check via node --check (fallback)...")
            syntax_result = self.syntax_checker.check(service_id, diffs)
            checks_run.append("syntax:native")
        
        syntax_errors = [v for v in syntax_result.violations if v.severity == ViolationSeverity.ERROR]
        syntax_warns  = [v for v in syntax_result.violations if v.severity != ViolationSeverity.ERROR]
        if syntax_errors:
            logger.error(f"[GATE]    [T1] SYNTAX FAIL: {len(syntax_errors)} errors, {len(syntax_warns)} warnings")
            for v in syntax_errors:
                logger.error(f"[GATE]         {v.file_path}:{v.line_number} — {v.description}")
        else:
            logger.info(f"[GATE]    [T1] SYNTAX PASS ({len(syntax_warns)} warnings)")
        
        all_violations.extend(syntax_result.violations)
        
        if self.config.fail_fast and syntax_errors:
            logger.warning(f"[GATE]    [T1] FAIL-FAST triggered by syntax errors — skipping remaining checks")
            result = self._build_result(all_violations, checks_run, start_time)
            logger.info(f"[GATE] << HARNESS DONE: FAIL in {result.duration_ms:.0f}ms — {len(syntax_errors)} syntax errors")
            return result
        
        # Import resolution - our checker (vallm doesn't verify paths)
        logger.info(f"[GATE]    [T1] Import resolution check...")
        import_result = self.import_resolver.check(service_id, diffs)
        import_errors = [v for v in import_result.violations if v.severity == ViolationSeverity.ERROR]
        if import_errors:
            logger.error(f"[GATE]    [T1] IMPORT FAIL: {len(import_errors)} unresolved imports")
            for v in import_errors:
                logger.error(f"[GATE]         {v.file_path}:{v.line_number} — {v.description}")
        else:
            logger.info(f"[GATE]    [T1] IMPORT PASS")
        
        all_violations.extend(import_result.violations)
        checks_run.append(CheckType.IMPORT.value)
        
        if self.config.fail_fast and import_errors:
            logger.warning(f"[GATE]    [T1] FAIL-FAST triggered by import errors")
            result = self._build_result(all_violations, checks_run, start_time)
            logger.info(f"[GATE] << HARNESS DONE: FAIL in {result.duration_ms:.0f}ms — {len(import_errors)} import errors")
            return result
        
        # =========================================
        # TIER 2: Security, Contracts, Complexity
        # =========================================
        
        # Security scan - combine vallm patterns + our extended patterns
        if not self.config.skip_security:
            if self.vallm_adapter and self.config.vallm_security:
                logger.info(f"[GATE]    [T2] Security scan via vallm patterns...")
                vallm_security = self.vallm_adapter.check_security(service_id, diffs)
                vallm_sec_violations = vallm_security.violations
                if vallm_sec_violations:
                    logger.warning(f"[GATE]    [T2] vallm security: {len(vallm_sec_violations)} findings")
                    for v in vallm_sec_violations:
                        logger.warning(f"[GATE]         [{v.severity.value}] {v.file_path}:{v.line_number} — {v.name}: {v.description[:80]}")
                else:
                    logger.info(f"[GATE]    [T2] vallm security: PASS")
                all_violations.extend(vallm_sec_violations)
                checks_run.append("security:vallm")
            
            logger.info(f"[GATE]    [T2] Security scan via native patterns (SQL injection, eval, secrets)...")
            security_result = self.security_scanner.check(service_id, diffs)
            native_sec_violations = security_result.violations
            if native_sec_violations:
                logger.warning(f"[GATE]    [T2] native security: {len(native_sec_violations)} findings")
                for v in native_sec_violations:
                    logger.warning(f"[GATE]         [{v.severity.value}] {v.file_path}:{v.line_number} — {v.name}: {v.description[:80]}")
            else:
                logger.info(f"[GATE]    [T2] native security: PASS")
            all_violations.extend(native_sec_violations)
            checks_run.append("security:native")
        else:
            logger.debug(f"[GATE]    [T2] Security scan SKIPPED (config)")
        
        # Complexity analysis - vallm/lizard
        if not self.config.skip_complexity and self.vallm_adapter and self.config.vallm_complexity:
            logger.info(f"[GATE]    [T2] Complexity check via lizard (threshold={self.config.complexity_threshold})...")
            complexity_result = self.vallm_adapter.check_complexity(service_id, diffs)
            complexity_violations = complexity_result.violations
            if complexity_violations:
                logger.warning(f"[GATE]    [T2] Complexity: {len(complexity_violations)} functions exceed threshold")
                for v in complexity_violations:
                    logger.warning(f"[GATE]         {v.file_path}:{v.line_number} — {v.description[:80]}")
            else:
                logger.info(f"[GATE]    [T2] Complexity: PASS")
            all_violations.extend(complexity_violations)
            checks_run.append("complexity:vallm")
        else:
            logger.debug(f"[GATE]    [T2] Complexity check SKIPPED")
        
        # Contract verification - our checker (vallm doesn't do this)
        if not self.config.skip_contracts and plan:
            logger.info(f"[GATE]    [T2] Contract check (function signatures vs plan)...")
            contract_result = self.contract_checker.check(service_id, diffs, plan)
            contract_violations = contract_result.violations
            if contract_violations:
                logger.error(f"[GATE]    [T2] Contract FAIL: {len(contract_violations)} signature mismatches")
                for v in contract_violations:
                    logger.error(f"[GATE]         {v.file_path}:{v.line_number} — {v.description[:80]}")
            else:
                logger.info(f"[GATE]    [T2] Contract: PASS")
            all_violations.extend(contract_violations)
            checks_run.append(CheckType.CONTRACT.value)
        else:
            logger.debug(f"[GATE]    [T2] Contract check SKIPPED (plan={'missing' if not plan else 'skipped by config'})")
        
        # =========================================
        # TIER 3: Hallucination & Constraints
        # =========================================
        
        # Hallucination detection - our checker (vallm doesn't do this)
        if not self.config.skip_hallucination:
            logger.info(f"[GATE]    [T3] Hallucination detection (invented functions/constants)...")
            hallucination_result = self.hallucination_detector.check(service_id, diffs)
            hallucination_violations = hallucination_result.violations
            if hallucination_violations:
                logger.error(f"[GATE]    [T3] Hallucination FAIL: {len(hallucination_violations)} invented symbols")
                for v in hallucination_violations:
                    logger.error(f"[GATE]         {v.file_path}:{v.line_number} — {v.description[:80]}")
            else:
                logger.info(f"[GATE]    [T3] Hallucination: PASS")
            all_violations.extend(hallucination_violations)
            checks_run.append(CheckType.HALLUCINATION.value)
        else:
            logger.debug(f"[GATE]    [T3] Hallucination check SKIPPED (config)")
        
        # Negative constraint checking - our checker (vallm doesn't do this)
        if not self.config.skip_constraints:
            logger.info(f"[GATE]    [T3] Negative constraints check (no persist removal, no new deps, etc.)...")
            constraint_result = self.constraint_checker.check(service_id, diffs)
            constraint_violations = constraint_result.violations
            if constraint_violations:
                logger.error(f"[GATE]    [T3] Negative constraint FAIL: {len(constraint_violations)} violations")
                for v in constraint_violations:
                    logger.error(f"[GATE]         {v.name}: {v.file_path}:{v.line_number} — {v.description[:80]}")
            else:
                logger.info(f"[GATE]    [T3] Negative constraints: PASS")
            all_violations.extend(constraint_violations)
            checks_run.append(CheckType.NEGATIVE_CONSTRAINT.value)
        else:
            logger.debug(f"[GATE]    [T3] Negative constraint check SKIPPED (config)")
        
        result = self._build_result(all_violations, checks_run, start_time)
        total_errors = len([v for v in result.violations if v.severity == ViolationSeverity.ERROR])
        total_warns  = len([v for v in result.violations if v.severity != ViolationSeverity.ERROR])
        verdict = "PASS" if result.passed else "FAIL"
        logger.info(f"[GATE] << HARNESS DONE: {verdict} in {result.duration_ms:.0f}ms — checks={checks_run} errors={total_errors} warnings={total_warns}")
        return result
    
    def _build_result(
        self,
        violations: List[HarnessViolation],
        checks_run: List[str],
        start_time: float
    ) -> HarnessResult:
        """Build the final result."""
        duration_ms = (time.time() - start_time) * 1000
        
        # Count errors
        errors = [v for v in violations if v.severity == ViolationSeverity.ERROR]
        
        # Deduplicate violations
        unique_violations = self._deduplicate_violations(violations)
        
        # Cap warnings
        if len(unique_violations) > self.config.max_warnings:
            errors_list = [v for v in unique_violations if v.severity == ViolationSeverity.ERROR]
            warnings_list = [v for v in unique_violations if v.severity != ViolationSeverity.ERROR]
            unique_violations = errors_list + warnings_list[:self.config.max_warnings - len(errors_list)]
        
        return HarnessResult(
            passed=len(errors) == 0,
            violations=unique_violations,
            checks_run=checks_run,
            duration_ms=duration_ms,
        )
    
    def _deduplicate_violations(
        self, violations: List[HarnessViolation]
    ) -> List[HarnessViolation]:
        """Remove duplicate violations."""
        seen = set()
        unique = []
        
        for v in violations:
            key = (v.check, v.file_path, v.description[:50], v.line_number)
            if key not in seen:
                seen.add(key)
                unique.append(v)
        
        return unique


# Convenience function for simple usage
async def run_harness_gate(
    service_id: str,
    diffs: List[FileDiff],
    services_path: str,
    plan: Dict[str, Any] = None,
    graph_store=None
) -> HarnessResult:
    """
    Run the harness gate with default configuration.
    
    Args:
        service_id: Service being checked
        diffs: List of file changes
        services_path: Path to services directory
        plan: Optional execution plan
        graph_store: Optional graph store for lookups
    
    Returns:
        HarnessResult with pass/fail and violations
    """
    gate = DeterministicGate(services_path, graph_store)
    return await gate.run(service_id, diffs, plan)
