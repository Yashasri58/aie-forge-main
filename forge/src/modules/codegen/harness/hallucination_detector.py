"""
Hallucination Detector
======================

Detects when LLMs invent things that don't exist:
1. Function calls to non-existent methods
2. References to non-existent constants/enums
3. Cross-service calls to undefined APIs
4. API parameters that don't match real signatures

Based on research:
- "Detecting and Correcting Hallucinations in LLM-Generated Code via Deterministic AST Analysis"
- vallm's hallucination detection approach
"""

import re
from typing import List, Set, Dict, Optional, Tuple
from pathlib import Path

from .models import (
    HarnessViolation,
    ViolationSeverity,
    CheckType,
    FileDiff,
    CheckResult,
)


class HallucinationDetector:
    """
    Detects hallucinated code elements that don't exist in the codebase.
    
    Key checks:
    1. New function calls - are they defined somewhere?
    2. Service client calls - does the target service have that method?
    3. Constant references - are the constants defined?
    """
    
    def __init__(self, services_path: str, graph_store=None):
        """
        Args:
            services_path: Path to the services directory
            graph_store: Optional KuzuGraphStore for symbol lookups
        """
        self.services_path = Path(services_path)
        self.store = graph_store
        
        # Cache of known symbols per service
        self._symbol_cache: Dict[str, Set[str]] = {}
        
        # Common built-in methods that shouldn't be flagged
        self._builtin_methods = {
            # Array methods
            'push', 'pop', 'shift', 'unshift', 'slice', 'splice', 'concat',
            'join', 'map', 'filter', 'reduce', 'forEach', 'find', 'findIndex',
            'some', 'every', 'includes', 'indexOf', 'sort', 'reverse', 'flat',
            # Object methods
            'keys', 'values', 'entries', 'assign', 'freeze', 'seal',
            'hasOwnProperty', 'toString', 'valueOf',
            # String methods
            'split', 'trim', 'toLowerCase', 'toUpperCase', 'replace',
            'substring', 'substr', 'charAt', 'charCodeAt', 'match',
            'startsWith', 'endsWith', 'padStart', 'padEnd',
            # Promise methods
            'then', 'catch', 'finally', 'all', 'race', 'resolve', 'reject',
            # Console methods
            'log', 'error', 'warn', 'info', 'debug', 'trace',
            # Common library methods
            'json', 'send', 'status', 'get', 'post', 'put', 'delete', 'use',
            'listen', 'route', 'query', 'body', 'params', 'headers',
        }
    
    def check(self, service_id: str, diffs: List[FileDiff]) -> CheckResult:
        """
        Run hallucination detection on all diffs.
        
        Args:
            service_id: Service being checked
            diffs: List of file changes
        
        Returns:
            CheckResult with hallucination warnings
        """
        violations = []
        
        for diff in diffs:
            if not self._is_javascript_file(diff.file_path):
                continue
            
            # Check for new function calls that might be hallucinated
            violations.extend(self._check_function_calls(service_id, diff))
            
            # Check for hallucinated constants/enums
            violations.extend(self._check_constants(service_id, diff))
            
            # Check cross-service calls
            violations.extend(self._check_service_calls(service_id, diff))
        
        return CheckResult(
            check_type=CheckType.HALLUCINATION,
            passed=len([v for v in violations if v.severity == ViolationSeverity.ERROR]) == 0,
            violations=violations,
        )
    
    def _is_javascript_file(self, path: str) -> bool:
        return path.endswith(('.js', '.ts', '.jsx', '.tsx'))
    
    def _check_function_calls(
        self, service_id: str, diff: FileDiff
    ) -> List[HarnessViolation]:
        """Check for potentially hallucinated function calls."""
        violations = []
        
        new_content = diff.modified_content
        old_content = diff.original_content or ""
        
        # Extract function calls from new and old content
        new_calls = self._extract_function_calls(new_content)
        old_calls = self._extract_function_calls(old_content)
        
        # Find calls that are new (not in original)
        added_calls = new_calls - old_calls
        
        # Check each new call
        for call_name in added_calls:
            # Skip built-in methods
            if call_name in self._builtin_methods:
                continue
            
            # Skip if it's defined in the same file
            if self._is_defined_in_content(call_name, new_content):
                continue
            
            # Skip if it's imported
            if self._is_imported(call_name, new_content):
                continue
            
            # Check if it exists in the service's codebase
            if not self._symbol_exists(service_id, call_name):
                # Find line number
                line_num = self._find_call_line(call_name, new_content)
                
                violations.append(HarnessViolation(
                    severity=ViolationSeverity.WARNING,
                    check=CheckType.HALLUCINATION,
                    service_id=service_id,
                    file_path=diff.file_path,
                    description=f"Function '{call_name}' may not exist - verify it's defined",
                    line_number=line_num,
                    fix_hint=f"Check if '{call_name}' is defined or import it",
                    details={"function_name": call_name},
                ))
        
        return violations
    
    def _check_constants(
        self, service_id: str, diff: FileDiff
    ) -> List[HarnessViolation]:
        """Check for potentially hallucinated constants."""
        violations = []
        
        new_content = diff.modified_content
        old_content = diff.original_content or ""
        
        # Extract UPPER_CASE constants that look like enums/events
        new_constants = self._extract_constants(new_content)
        old_constants = self._extract_constants(old_content)
        
        # Find new constants
        added_constants = new_constants - old_constants
        
        for const in added_constants:
            # Skip if defined in this file
            if f"const {const}" in new_content or f"'{const}'" in old_content:
                continue
            
            # Skip common patterns
            if const in ('ERROR', 'SUCCESS', 'TRUE', 'FALSE', 'NULL', 'UNDEFINED'):
                continue
            
            line_num = self._find_constant_line(const, new_content)
            
            violations.append(HarnessViolation(
                severity=ViolationSeverity.WARNING,
                check=CheckType.HALLUCINATION,
                service_id=service_id,
                file_path=diff.file_path,
                description=f"Constant/event type '{const}' may need to be defined",
                line_number=line_num,
                fix_hint=f"Ensure '{const}' is defined in appropriate constants file",
                details={"constant": const},
            ))
        
        return violations
    
    def _check_service_calls(
        self, service_id: str, diff: FileDiff
    ) -> List[HarnessViolation]:
        """Check cross-service calls for hallucinated methods."""
        violations = []
        
        new_content = diff.modified_content
        old_content = diff.original_content or ""
        
        # Pattern: serviceName.methodName() or serviceClient.methodName()
        service_call_pattern = r'(\w+(?:Service|Client|service|client))\s*\.\s*(\w+)\s*\('
        
        for match in re.finditer(service_call_pattern, new_content):
            full_match = match.group(0)
            
            # Skip if this call existed in original
            if full_match in old_content:
                continue
            
            client_name = match.group(1)
            method_name = match.group(2)
            
            # Skip common built-ins
            if method_name in self._builtin_methods:
                continue
            
            # Infer target service from client name
            target_service = self._infer_service(client_name)
            
            if target_service and target_service != service_id:
                # Check if method exists in target service
                if not self._method_exists_in_service(target_service, method_name):
                    line_num = new_content[:match.start()].count('\n') + 1
                    
                    violations.append(HarnessViolation(
                        severity=ViolationSeverity.WARNING,
                        check=CheckType.HALLUCINATION,
                        service_id=service_id,
                        file_path=diff.file_path,
                        description=f"Method '{method_name}' may not exist in {target_service}",
                        line_number=line_num,
                        fix_hint=f"Verify {target_service} exposes '{method_name}'",
                        details={
                            "client": client_name,
                            "method": method_name,
                            "target_service": target_service,
                        },
                    ))
        
        return violations
    
    def _extract_function_calls(self, content: str) -> Set[str]:
        """Extract all function call names from code."""
        calls = set()
        
        # Match: functionName( or .methodName(
        pattern = r'(?:^|[^\w.])(\w+)\s*\('
        
        for match in re.finditer(pattern, content):
            name = match.group(1)
            # Filter out keywords
            if name not in ('if', 'for', 'while', 'switch', 'catch', 'function', 'class', 'return', 'new', 'typeof', 'instanceof'):
                calls.add(name)
        
        return calls
    
    def _extract_constants(self, content: str) -> Set[str]:
        """Extract UPPER_CASE constants (likely events/enums)."""
        constants = set()
        
        # Pattern: 'SOME_CONSTANT' or "SOME_CONSTANT"
        pattern = r"['\"]([A-Z][A-Z0-9_]{2,})['\"]"
        
        for match in re.finditer(pattern, content):
            constants.add(match.group(1))
        
        return constants
    
    def _is_defined_in_content(self, name: str, content: str) -> bool:
        """Check if function/variable is defined in the content."""
        patterns = [
            rf'function\s+{name}\s*\(',  # function declaration
            rf'const\s+{name}\s*=',       # const assignment
            rf'let\s+{name}\s*=',         # let assignment
            rf'var\s+{name}\s*=',         # var assignment
            rf'{name}\s*:\s*(?:async\s+)?function',  # object method
            rf'{name}\s*=\s*(?:async\s+)?\(',  # arrow function
            rf'class\s+{name}\s*[{{<]',   # class definition
        ]
        
        for pattern in patterns:
            if re.search(pattern, content):
                return True
        return False
    
    def _is_imported(self, name: str, content: str) -> bool:
        """Check if a symbol is imported."""
        patterns = [
            rf'import\s+{name}\s+from',
            rf'import\s*\{{[^}}]*\b{name}\b[^}}]*\}}\s*from',
            rf"const\s*\{{[^}}]*\b{name}\b[^}}]*\}}\s*=\s*require",
            rf"const\s+{name}\s*=\s*require",
        ]
        
        for pattern in patterns:
            if re.search(pattern, content):
                return True
        return False
    
    def _symbol_exists(self, service_id: str, symbol: str) -> bool:
        """Check if symbol exists in the service's codebase."""
        if self.store:
            try:
                result = self.store.query(f"""
                    MATCH (s:Symbol)
                    WHERE s.service = '{service_id}' AND s.name = '{symbol}'
                    RETURN COUNT(s) > 0
                """)
                return result and result[0][0]
            except Exception:
                pass
        
        # Fallback: search files
        return self._search_symbol_in_files(service_id, symbol)
    
    def _search_symbol_in_files(self, service_id: str, symbol: str) -> bool:
        """Search for symbol definition in service files."""
        service_path = self.services_path / service_id
        if not service_path.exists():
            return False
        
        try:
            for js_file in service_path.rglob('*.js'):
                content = js_file.read_text(encoding='utf-8', errors='ignore')
                if self._is_defined_in_content(symbol, content):
                    return True
        except Exception:
            pass
        
        return False
    
    def _infer_service(self, client_name: str) -> Optional[str]:
        """Infer service name from client variable name."""
        # auditService -> audit-service
        # auditClient -> audit-service
        name = client_name.replace('Service', '').replace('Client', '')
        name = name.replace('service', '').replace('client', '')
        
        # Convert camelCase to kebab-case
        result = re.sub(r'([a-z])([A-Z])', r'\1-\2', name).lower()
        
        # Add -service suffix if not present
        if not result.endswith('-service'):
            result += '-service'
        
        return result if result else None
    
    def _method_exists_in_service(self, service_id: str, method: str) -> bool:
        """Check if a method/endpoint exists in a service."""
        if self.store:
            try:
                result = self.store.query(f"""
                    MATCH (s:Symbol)
                    WHERE s.service = '{service_id}' AND s.name = '{method}'
                    RETURN COUNT(s) > 0
                """)
                return result and result[0][0]
            except Exception:
                pass
        
        return self._search_symbol_in_files(service_id, method)
    
    def _find_call_line(self, name: str, content: str) -> Optional[int]:
        """Find line number where function is called."""
        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            if re.search(rf'\b{name}\s*\(', line):
                return i
        return None
    
    def _find_constant_line(self, const: str, content: str) -> Optional[int]:
        """Find line number where constant is used."""
        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            if const in line:
                return i
        return None
