"""
Vallm Adapter
=============

Integrates vallm (https://github.com/semcod/vallm) with our harness.

We use vallm for:
- Syntax validation (tree-sitter - robust, 165 languages)
- Complexity metrics (lizard integration)
- Security scanning (complements our patterns)

We keep our own checks for:
- Hallucination detection (vallm doesn't do this)
- Import path verification (vallm only checks syntax)
- Negative constraints (vallm doesn't do this)
- Contract checking (vallm doesn't do this)
"""

from typing import List, Optional
from dataclasses import dataclass

from .models import (
    HarnessViolation,
    ViolationSeverity,
    CheckType,
    FileDiff,
    CheckResult,
)

# Try to import vallm - graceful fallback if not installed
try:
    from vallm import Proposal, validate
    from vallm.validators.syntax import SyntaxValidator
    from vallm.validators.complexity import ComplexityValidator
    from vallm.validators.security import SecurityValidator
    VALLM_AVAILABLE = True
except ImportError:
    VALLM_AVAILABLE = False


@dataclass
class VallmConfig:
    """Configuration for vallm integration."""
    use_syntax: bool = True        # Use vallm's tree-sitter syntax
    use_complexity: bool = True    # Use vallm's lizard complexity
    use_security: bool = True      # Use vallm's security patterns
    complexity_threshold: int = 15  # Max cyclomatic complexity before warning
    max_function_length: int = 100  # Max lines per function


class VallmAdapter:
    """
    Adapter that converts vallm validation to our harness format.
    
    Usage:
        adapter = VallmAdapter()
        result = adapter.check(service_id, diffs)
    """
    
    def __init__(self, config: VallmConfig = None):
        self.config = config or VallmConfig()
        self._available = VALLM_AVAILABLE
        
        if self._available:
            # Initialize validators we want to use
            if self.config.use_syntax:
                self._syntax_validator = SyntaxValidator()
            if self.config.use_complexity:
                self._complexity_validator = ComplexityValidator()
            if self.config.use_security:
                self._security_validator = SecurityValidator()
    
    @property
    def available(self) -> bool:
        """Check if vallm is available."""
        return self._available
    
    def check_syntax(self, service_id: str, diffs: List[FileDiff]) -> CheckResult:
        """
        Run vallm syntax validation using tree-sitter.
        
        Returns:
            CheckResult with syntax violations
        """
        if not self._available or not self.config.use_syntax:
            return CheckResult(
                check_type=CheckType.SYNTAX,
                passed=True,
                skipped=True,
                skip_reason="vallm not available or syntax disabled"
            )
        
        violations = []
        
        for diff in diffs:
            language = self._detect_language(diff.file_path)
            if not language:
                continue
            
            proposal = Proposal(
                code=diff.modified_content,
                language=language
            )
            
            try:
                result = self._syntax_validator.validate(proposal, context={})
                
                if result.score < 1.0:
                    # Convert vallm issues to our violations
                    for issue in result.issues or []:
                        violations.append(HarnessViolation(
                            severity=ViolationSeverity.ERROR,
                            check=CheckType.SYNTAX,
                            service_id=service_id,
                            file_path=diff.file_path,
                            description=issue.message,
                            line_number=issue.line,
                            fix_hint="Fix the syntax error to proceed",
                            details={"source": "vallm/tree-sitter", "rule": issue.rule}
                        ))
            except Exception as e:
                # Log but don't fail - fallback to our checker
                violations.append(HarnessViolation(
                    severity=ViolationSeverity.WARNING,
                    check=CheckType.SYNTAX,
                    service_id=service_id,
                    file_path=diff.file_path,
                    description=f"vallm syntax check error: {str(e)[:100]}",
                    details={"source": "vallm", "error": str(e)}
                ))
        
        return CheckResult(
            check_type=CheckType.SYNTAX,
            passed=len([v for v in violations if v.severity == ViolationSeverity.ERROR]) == 0,
            violations=violations,
        )
    
    def check_complexity(self, service_id: str, diffs: List[FileDiff]) -> CheckResult:
        """
        Run vallm complexity analysis using lizard.
        
        Returns:
            CheckResult with complexity violations
        """
        if not self._available or not self.config.use_complexity:
            return CheckResult(
                check_type=CheckType.SECURITY,  # Using SECURITY as no COMPLEXITY type
                passed=True,
                skipped=True,
                skip_reason="vallm not available or complexity disabled"
            )
        
        violations = []
        
        for diff in diffs:
            language = self._detect_language(diff.file_path)
            if not language:
                continue
            
            proposal = Proposal(
                code=diff.modified_content,
                language=language
            )
            
            try:
                result = self._complexity_validator.validate(proposal, context={})
                
                # Extract function-level complexity from details
                if hasattr(result, 'details') and result.details:
                    functions = result.details.get('lizard_functions', [])
                    
                    for func in functions:
                        complexity = func.get('complexity', 0)
                        length = func.get('length', 0)
                        name = func.get('name', 'unknown')
                        
                        # Check complexity threshold
                        if complexity > self.config.complexity_threshold:
                            violations.append(HarnessViolation(
                                severity=ViolationSeverity.WARNING,
                                check=CheckType.SECURITY,
                                service_id=service_id,
                                file_path=diff.file_path,
                                description=f"Function '{name}' has high complexity ({complexity} > {self.config.complexity_threshold})",
                                fix_hint="Consider breaking down this function into smaller pieces",
                                details={
                                    "source": "vallm/lizard",
                                    "function": name,
                                    "complexity": complexity,
                                    "length": length,
                                }
                            ))
                        
                        # Check function length
                        if length > self.config.max_function_length:
                            violations.append(HarnessViolation(
                                severity=ViolationSeverity.WARNING,
                                check=CheckType.SECURITY,
                                service_id=service_id,
                                file_path=diff.file_path,
                                description=f"Function '{name}' is too long ({length} lines > {self.config.max_function_length})",
                                fix_hint="Consider extracting helper functions",
                                details={
                                    "source": "vallm/lizard",
                                    "function": name,
                                    "length": length,
                                }
                            ))
            except Exception as e:
                # Non-fatal
                pass
        
        return CheckResult(
            check_type=CheckType.SECURITY,
            passed=True,  # Complexity is warnings only
            violations=violations,
        )
    
    def check_security(self, service_id: str, diffs: List[FileDiff]) -> CheckResult:
        """
        Run vallm security patterns (complements our SecurityScanner).
        
        Returns:
            CheckResult with security violations
        """
        if not self._available or not self.config.use_security:
            return CheckResult(
                check_type=CheckType.SECURITY,
                passed=True,
                skipped=True,
                skip_reason="vallm not available or security disabled"
            )
        
        violations = []
        
        for diff in diffs:
            language = self._detect_language(diff.file_path)
            if not language:
                continue
            
            proposal = Proposal(
                code=diff.modified_content,
                language=language
            )
            
            try:
                result = self._security_validator.validate(proposal, context={})
                
                for issue in result.issues or []:
                    severity = ViolationSeverity.WARNING
                    if issue.severity and issue.severity.value == 'error':
                        severity = ViolationSeverity.ERROR
                    
                    violations.append(HarnessViolation(
                        severity=severity,
                        check=CheckType.SECURITY,
                        service_id=service_id,
                        file_path=diff.file_path,
                        description=issue.message,
                        line_number=issue.line,
                        fix_hint="Review and fix this security issue",
                        details={
                            "source": "vallm",
                            "rule": issue.rule,
                        }
                    ))
            except Exception as e:
                # Non-fatal
                pass
        
        return CheckResult(
            check_type=CheckType.SECURITY,
            passed=len([v for v in violations if v.severity == ViolationSeverity.ERROR]) == 0,
            violations=violations,
        )
    
    def check_all(self, service_id: str, diffs: List[FileDiff]) -> List[CheckResult]:
        """
        Run all vallm checks.
        
        Returns:
            List of CheckResults from all vallm validators
        """
        results = []
        
        if self.config.use_syntax:
            results.append(self.check_syntax(service_id, diffs))
        
        if self.config.use_complexity:
            results.append(self.check_complexity(service_id, diffs))
        
        if self.config.use_security:
            results.append(self.check_security(service_id, diffs))
        
        return results
    
    def _detect_language(self, file_path: str) -> Optional[str]:
        """Detect language from file extension."""
        ext_map = {
            '.js': 'javascript',
            '.mjs': 'javascript',
            '.cjs': 'javascript',
            '.jsx': 'javascript',
            '.ts': 'typescript',
            '.tsx': 'typescript',
            '.py': 'python',
            '.go': 'go',
            '.rs': 'rust',
            '.java': 'java',
            '.c': 'c',
            '.cpp': 'cpp',
            '.h': 'c',
            '.hpp': 'cpp',
        }
        
        for ext, lang in ext_map.items():
            if file_path.endswith(ext):
                return lang
        
        return None


# Singleton for easy access
_vallm_adapter: Optional[VallmAdapter] = None

def get_vallm_adapter(config: VallmConfig = None) -> VallmAdapter:
    """Get the vallm adapter singleton."""
    global _vallm_adapter
    if _vallm_adapter is None:
        _vallm_adapter = VallmAdapter(config)
    return _vallm_adapter
