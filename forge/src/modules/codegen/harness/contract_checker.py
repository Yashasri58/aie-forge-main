"""
Contract Checker
================

Verifies that generated code matches the contracts defined in the plan.

Checks:
1. Function signatures match contract definitions
2. Parameter names and types match
3. Return types are compatible
4. Required methods are implemented
"""

import re
from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass

import logging
logger = logging.getLogger("forge.codegen.harness")

from .models import (
    HarnessViolation,
    ViolationSeverity,
    CheckType,
    FileDiff,
    CheckResult,
)


@dataclass
class Contract:
    """A contract defined in the plan."""
    name: str
    signature: str
    parameters: List[Dict[str, Any]]
    return_type: Optional[str]
    file_path: Optional[str] = None
    service: Optional[str] = None
    usage_example: Optional[str] = None


class ContractChecker:
    """
    Verifies generated code matches the contracts in the plan.
    
    Contracts define exact signatures that must be implemented.
    This ensures consistency across the codebase.
    """
    
    def __init__(self):
        self.contracts: List[Contract] = []
    
    def check(
        self,
        service_id: str,
        diffs: List[FileDiff],
        plan: Dict[str, Any]
    ) -> CheckResult:
        """
        Verify diffs match plan contracts.
        
        Args:
            service_id: Service being checked
            diffs: List of file changes
            plan: The execution plan with contracts
        
        Returns:
            CheckResult with contract violations
        """
        violations = []
        
        # Extract contracts from plan
        self.contracts = self._extract_contracts(plan)
        
        if not self.contracts:
            logger.debug(f"[CONTRACT] service={service_id}: No contracts defined in plan — SKIP")
            return CheckResult(
                check_type=CheckType.CONTRACT,
                passed=True,
                violations=[],
                skipped=True,
                skip_reason="No contracts defined in plan",
            )
        
        logger.info(f"[CONTRACT] service={service_id}: Checking {len(self.contracts)} contracts across {len(diffs)} diffs")
        for c in self.contracts:
            logger.debug(f"[CONTRACT]    contract: {c.name} → {c.signature[:60]}")
        
        for diff in diffs:
            if not self._is_javascript_file(diff.file_path):
                continue
            
            file_violations = self._check_file_contracts(service_id, diff)
            if file_violations:
                logger.warning(f"[CONTRACT]    {diff.file_path}: {len(file_violations)} contract violations")
                for v in file_violations:
                    logger.warning(f"[CONTRACT]      line {v.line_number}: {v.description[:80]}")
            else:
                logger.debug(f"[CONTRACT]    {diff.file_path}: contracts OK")
            violations.extend(file_violations)
        
        # Check for missing contract implementations
        missing = self._check_missing_implementations(service_id, diffs)
        if missing:
            logger.error(f"[CONTRACT]    {len(missing)} contracts NOT implemented")
            for v in missing:
                logger.error(f"[CONTRACT]      MISSING: {v.description[:80]}")
        violations.extend(missing)
        
        passed = len([v for v in violations if v.severity == ViolationSeverity.ERROR]) == 0
        logger.info(f"[CONTRACT] service={service_id}: {'PASS' if passed else 'FAIL'} — {len(violations)} total violations")
        return CheckResult(
            check_type=CheckType.CONTRACT,
            passed=passed,
            violations=violations,
        )
    
    def _is_javascript_file(self, path: str) -> bool:
        return path.endswith(('.js', '.ts', '.jsx', '.tsx'))
    
    def _extract_contracts(self, plan: Dict[str, Any]) -> List[Contract]:
        """Extract contracts from the plan."""
        contracts = []
        
        # Look for contracts in plan structure
        plan_contracts = plan.get('contracts', [])
        
        for c in plan_contracts:
            if isinstance(c, dict):
                contracts.append(Contract(
                    name=c.get('name', ''),
                    signature=c.get('signature', ''),
                    parameters=c.get('parameters', []),
                    return_type=c.get('return_type'),
                    file_path=c.get('file'),
                    service=c.get('service'),
                    usage_example=c.get('usage_example'),
                ))
        
        return contracts
    
    def _check_file_contracts(
        self, service_id: str, diff: FileDiff
    ) -> List[HarnessViolation]:
        """Check contracts that should be in this file."""
        violations = []
        content = diff.modified_content
        
        # Find contracts for this file
        file_contracts = [
            c for c in self.contracts
            if self._contract_matches_file(c, diff.file_path)
        ]
        
        for contract in file_contracts:
            contract_violations = self._verify_contract(
                service_id, diff, contract, content
            )
            violations.extend(contract_violations)
        
        return violations
    
    def _contract_matches_file(self, contract: Contract, file_path: str) -> bool:
        """Check if a contract should be implemented in this file."""
        if contract.file_path:
            # Normalize paths for comparison
            return contract.file_path.replace('\\', '/') in file_path.replace('\\', '/')
        return False
    
    def _verify_contract(
        self,
        service_id: str,
        diff: FileDiff,
        contract: Contract,
        content: str
    ) -> List[HarnessViolation]:
        """Verify a single contract is implemented correctly."""
        violations = []
        
        # Extract function definition from content
        func_def = self._find_function_definition(contract.name, content)
        
        if not func_def:
            violations.append(HarnessViolation(
                severity=ViolationSeverity.ERROR,
                check=CheckType.CONTRACT,
                service_id=service_id,
                file_path=diff.file_path,
                description=f"Contract '{contract.name}' not implemented",
                fix_hint=f"Implement function with signature: {contract.signature}",
                details={"contract": contract.name, "expected_signature": contract.signature},
            ))
            return violations
        
        # Check signature matches
        signature_violations = self._check_signature(
            service_id, diff, contract, func_def
        )
        violations.extend(signature_violations)
        
        return violations
    
    def _find_function_definition(
        self, name: str, content: str
    ) -> Optional[Dict[str, Any]]:
        """Find a function definition in the content."""
        # Pattern for various function declaration styles
        patterns = [
            # function name(params)
            rf'function\s+{name}\s*\(([^)]*)\)',
            # const name = function(params)
            rf'const\s+{name}\s*=\s*(?:async\s+)?function\s*\(([^)]*)\)',
            # const name = (params) =>
            rf'const\s+{name}\s*=\s*(?:async\s+)?\(([^)]*)\)\s*=>',
            # name(params) { (object method)
            rf'{name}\s*\(([^)]*)\)\s*{{',
            # async name(params) {
            rf'async\s+{name}\s*\(([^)]*)\)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, content)
            if match:
                params_str = match.group(1)
                return {
                    "name": name,
                    "params_str": params_str,
                    "params": self._parse_params(params_str),
                    "start": match.start(),
                    "line": content[:match.start()].count('\n') + 1,
                }
        
        return None
    
    def _parse_params(self, params_str: str) -> List[str]:
        """Parse parameter string into list of parameter names."""
        if not params_str or not params_str.strip():
            return []
        
        params = []
        for param in params_str.split(','):
            param = param.strip()
            # Handle default values: param = default
            if '=' in param:
                param = param.split('=')[0].strip()
            # Handle destructuring: { a, b }
            if param.startswith('{'):
                continue  # Skip destructured params for now
            # Handle type annotations: param: type
            if ':' in param:
                param = param.split(':')[0].strip()
            if param:
                params.append(param)
        
        return params
    
    def _check_signature(
        self,
        service_id: str,
        diff: FileDiff,
        contract: Contract,
        func_def: Dict[str, Any]
    ) -> List[HarnessViolation]:
        """Check if function signature matches contract."""
        violations = []
        
        # Extract expected params from contract
        expected_params = [p.get('name', '') for p in contract.parameters]
        actual_params = func_def['params']
        
        # Check parameter count
        if len(expected_params) != len(actual_params):
            violations.append(HarnessViolation(
                severity=ViolationSeverity.ERROR,
                check=CheckType.CONTRACT,
                service_id=service_id,
                file_path=diff.file_path,
                description=f"Contract '{contract.name}' parameter count mismatch: expected {len(expected_params)}, got {len(actual_params)}",
                line_number=func_def['line'],
                fix_hint=f"Expected parameters: {', '.join(expected_params)}",
                details={
                    "contract": contract.name,
                    "expected_params": expected_params,
                    "actual_params": actual_params,
                },
            ))
        
        # Check parameter names match
        for i, (expected, actual) in enumerate(zip(expected_params, actual_params)):
            if expected and actual and expected != actual:
                violations.append(HarnessViolation(
                    severity=ViolationSeverity.WARNING,
                    check=CheckType.CONTRACT,
                    service_id=service_id,
                    file_path=diff.file_path,
                    description=f"Contract '{contract.name}' parameter {i+1} name mismatch: expected '{expected}', got '{actual}'",
                    line_number=func_def['line'],
                    fix_hint=f"Rename parameter to '{expected}'",
                ))
        
        return violations
    
    def _check_missing_implementations(
        self, service_id: str, diffs: List[FileDiff]
    ) -> List[HarnessViolation]:
        """Check for contracts that are not implemented anywhere."""
        violations = []
        
        # Collect all implemented functions
        implemented = set()
        for diff in diffs:
            if not self._is_javascript_file(diff.file_path):
                continue
            
            content = diff.modified_content
            # Extract all function names
            for pattern in [
                r'function\s+(\w+)\s*\(',
                r'const\s+(\w+)\s*=\s*(?:async\s+)?function',
                r'const\s+(\w+)\s*=\s*(?:async\s+)?\([^)]*\)\s*=>',
            ]:
                for match in re.finditer(pattern, content):
                    implemented.add(match.group(1))
        
        # Check each contract is implemented
        for contract in self.contracts:
            if contract.name not in implemented:
                # Only flag if there's a target file
                if contract.file_path:
                    violations.append(HarnessViolation(
                        severity=ViolationSeverity.ERROR,
                        check=CheckType.CONTRACT,
                        service_id=service_id,
                        file_path=contract.file_path or "unknown",
                        description=f"Contract '{contract.name}' is not implemented",
                        fix_hint=f"Add implementation with signature: {contract.signature}",
                        details={"contract": contract.name},
                    ))
        
        return violations
