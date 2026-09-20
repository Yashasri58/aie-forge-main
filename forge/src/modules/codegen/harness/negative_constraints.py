"""
Negative Constraint Checker
===========================

Enforces explicit failure bounds - rules that define what code MUST NOT do.

Based on the "Negative Constraint Assertions" pattern from:
"How to Build Zero-Hallucination AI Agents"

Key principle: Positive prompts tell the model what to do.
Negative constraints define explicit failure bounds that trigger
automated rejection BEFORE execution.

Default Constraints:
1. DO NOT remove code marked with [PERSIST] or @preserve
2. DO NOT introduce new third-party dependencies
3. DO NOT return whole-file rewrites (unified diff only)
4. DO NOT catch generic exceptions
5. DO NOT delete test files
6. DO NOT remove error handling
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
class NegativeConstraint:
    """A negative constraint that must NOT be violated."""
    name: str
    description: str
    check_fn: str  # Method name to call
    severity: ViolationSeverity = ViolationSeverity.ERROR


class NegativeConstraintChecker:
    """
    Enforces negative constraints - things the generated code must NOT do.
    
    Unlike positive validation (does the code work?), negative constraints
    define explicit failure bounds that trigger automated rejection.
    """
    
    def __init__(self, custom_constraints: List[NegativeConstraint] = None):
        """
        Args:
            custom_constraints: Additional constraints to enforce
        """
        # Default constraints
        self.constraints = [
            NegativeConstraint(
                name="no_persist_removal",
                description="Code marked with [PERSIST] or @preserve must not be removed",
                check_fn="_check_persist_removal",
            ),
            NegativeConstraint(
                name="no_whole_file_rewrite",
                description="Whole-file rewrites are not allowed - use targeted changes",
                check_fn="_check_whole_file_rewrite",
            ),
            NegativeConstraint(
                name="no_generic_catch",
                description="Generic catch(e) without specific error types is not allowed",
                check_fn="_check_generic_catch",
                severity=ViolationSeverity.WARNING,
            ),
            NegativeConstraint(
                name="no_test_deletion",
                description="Test files must not be deleted",
                check_fn="_check_test_deletion",
            ),
            NegativeConstraint(
                name="no_error_handling_removal",
                description="Error handling (try/catch) should not be removed",
                check_fn="_check_error_handling_removal",
                severity=ViolationSeverity.WARNING,
            ),
            NegativeConstraint(
                name="no_logging_removal",
                description="Logging statements should not be removed without replacement",
                check_fn="_check_logging_removal",
                severity=ViolationSeverity.WARNING,
            ),
            NegativeConstraint(
                name="no_env_hardcoding",
                description="Environment variables should not be replaced with hardcoded values",
                check_fn="_check_env_hardcoding",
            ),
        ]
        
        if custom_constraints:
            self.constraints.extend(custom_constraints)
    
    def check(self, service_id: str, diffs: List[FileDiff]) -> CheckResult:
        """
        Check all diffs against negative constraints.
        
        Args:
            service_id: Service being checked
            diffs: List of file changes
        
        Returns:
            CheckResult with constraint violations
        """
        violations = []
        
        logger.info(f"[NEGCONST] service={service_id}: Checking {len(self.constraints)} constraints across {len(diffs)} diffs")
        for c in self.constraints:
            logger.debug(f"[NEGCONST]    constraint: {c.name} ({c.severity.value})")
        
        for diff in diffs:
            for constraint in self.constraints:
                check_method = getattr(self, constraint.check_fn, None)
                if check_method:
                    constraint_violations = check_method(
                        service_id, diff, constraint
                    )
                    if constraint_violations:
                        logger.warning(f"[NEGCONST]    {diff.file_path} — violated: {constraint.name}")
                        for v in constraint_violations:
                            logger.warning(f"[NEGCONST]      [{v.severity.value}] line {v.line_number}: {v.description[:80]}")
                    violations.extend(constraint_violations)
        
        passed = len([v for v in violations if v.severity == ViolationSeverity.ERROR]) == 0
        if violations:
            violated_names = list({v.name for v in violations})
            logger.info(f"[NEGCONST] service={service_id}: {'PASS' if passed else 'FAIL'} — violated: {violated_names}")
        else:
            logger.info(f"[NEGCONST] service={service_id}: PASS — all constraints satisfied")
        return CheckResult(
            check_type=CheckType.NEGATIVE_CONSTRAINT,
            passed=passed,
            violations=violations,
        )
    
    def _check_persist_removal(
        self,
        service_id: str,
        diff: FileDiff,
        constraint: NegativeConstraint
    ) -> List[HarnessViolation]:
        """Check that [PERSIST] or @preserve marked code is not removed."""
        violations = []
        old_content = diff.original_content or ""
        new_content = diff.modified_content
        
        # Find persist-marked sections in original
        persist_patterns = [
            r'//\s*\[PERSIST\].*?(?://\s*\[/PERSIST\]|$)',
            r'/\*\s*@preserve[\s\S]*?\*/',
            r'//\s*@preserve.*',
            r'//\s*DO NOT MODIFY.*',
        ]
        
        for pattern in persist_patterns:
            old_matches = re.findall(pattern, old_content, re.IGNORECASE | re.DOTALL)
            for match in old_matches:
                # Check if this section still exists in new content
                if match not in new_content:
                    # Extract first line for context
                    first_line = match.split('\n')[0][:80]
                    violations.append(HarnessViolation(
                        severity=constraint.severity,
                        check=CheckType.NEGATIVE_CONSTRAINT,
                        service_id=service_id,
                        file_path=diff.file_path,
                        description=f"Persist-marked code was removed: {first_line}...",
                        fix_hint="Do not remove code marked with [PERSIST] or @preserve",
                        details={"constraint": constraint.name},
                    ))
        
        return violations
    
    def _check_whole_file_rewrite(
        self,
        service_id: str,
        diff: FileDiff,
        constraint: NegativeConstraint
    ) -> List[HarnessViolation]:
        """Check for whole-file rewrites (more than 80% changed)."""
        violations = []
        old_content = diff.original_content or ""
        new_content = diff.modified_content
        
        # Skip for new files
        if diff.is_new_file:
            return violations
        
        # Calculate similarity
        old_lines = set(line.strip() for line in old_content.split('\n') if line.strip())
        new_lines = set(line.strip() for line in new_content.split('\n') if line.strip())
        
        if not old_lines:
            return violations
        
        preserved = old_lines & new_lines
        preservation_ratio = len(preserved) / len(old_lines)
        
        # If less than 20% preserved, it's effectively a rewrite
        if preservation_ratio < 0.2 and len(old_lines) > 10:
            violations.append(HarnessViolation(
                severity=constraint.severity,
                check=CheckType.NEGATIVE_CONSTRAINT,
                service_id=service_id,
                file_path=diff.file_path,
                description=f"Whole-file rewrite detected ({int(preservation_ratio*100)}% preserved)",
                fix_hint="Make targeted changes instead of rewriting the entire file",
                details={
                    "constraint": constraint.name,
                    "preservation_ratio": preservation_ratio,
                    "old_lines": len(old_lines),
                    "new_lines": len(new_lines),
                },
            ))
        
        return violations
    
    def _check_generic_catch(
        self,
        service_id: str,
        diff: FileDiff,
        constraint: NegativeConstraint
    ) -> List[HarnessViolation]:
        """Check for generic catch blocks without specific error types."""
        violations = []
        new_content = diff.modified_content
        old_content = diff.original_content or ""
        
        # Pattern for generic catch
        generic_catch = r'catch\s*\(\s*(?:e|err|error|ex)\s*\)\s*{'
        
        # Find new generic catches
        new_matches = list(re.finditer(generic_catch, new_content))
        old_matches = list(re.finditer(generic_catch, old_content))
        
        # Only flag new generic catches
        if len(new_matches) > len(old_matches):
            for match in new_matches[len(old_matches):]:
                line_num = new_content[:match.start()].count('\n') + 1
                violations.append(HarnessViolation(
                    severity=constraint.severity,
                    check=CheckType.NEGATIVE_CONSTRAINT,
                    service_id=service_id,
                    file_path=diff.file_path,
                    description="Generic catch block - consider specific error handling",
                    line_number=line_num,
                    fix_hint="Use specific error types or add error type checking",
                    details={"constraint": constraint.name},
                ))
        
        return violations
    
    def _check_test_deletion(
        self,
        service_id: str,
        diff: FileDiff,
        constraint: NegativeConstraint
    ) -> List[HarnessViolation]:
        """Check that test files are not being deleted."""
        violations = []
        
        # Check if this is a test file
        is_test = any(p in diff.file_path.lower() for p in [
            'test', 'spec', '__tests__', '.test.', '.spec.'
        ])
        
        if is_test and not diff.modified_content.strip():
            violations.append(HarnessViolation(
                severity=constraint.severity,
                check=CheckType.NEGATIVE_CONSTRAINT,
                service_id=service_id,
                file_path=diff.file_path,
                description="Test file is being deleted",
                fix_hint="Do not delete test files - update them instead",
                details={"constraint": constraint.name},
            ))
        
        return violations
    
    def _check_error_handling_removal(
        self,
        service_id: str,
        diff: FileDiff,
        constraint: NegativeConstraint
    ) -> List[HarnessViolation]:
        """Check that error handling is not being removed."""
        violations = []
        old_content = diff.original_content or ""
        new_content = diff.modified_content
        
        # Count try/catch blocks
        old_try_count = len(re.findall(r'\btry\s*{', old_content))
        new_try_count = len(re.findall(r'\btry\s*{', new_content))
        
        if old_try_count > new_try_count and old_try_count > 0:
            removed = old_try_count - new_try_count
            violations.append(HarnessViolation(
                severity=constraint.severity,
                check=CheckType.NEGATIVE_CONSTRAINT,
                service_id=service_id,
                file_path=diff.file_path,
                description=f"{removed} try/catch block(s) removed",
                fix_hint="Maintain error handling or replace with equivalent handling",
                details={"constraint": constraint.name, "removed_count": removed},
            ))
        
        return violations
    
    def _check_logging_removal(
        self,
        service_id: str,
        diff: FileDiff,
        constraint: NegativeConstraint
    ) -> List[HarnessViolation]:
        """Check that logging is not being removed without replacement."""
        violations = []
        old_content = diff.original_content or ""
        new_content = diff.modified_content
        
        # Count logging statements
        log_pattern = r'(?:console|logger|log)\s*\.\s*(?:log|info|warn|error|debug)\s*\('
        
        old_log_count = len(re.findall(log_pattern, old_content))
        new_log_count = len(re.findall(log_pattern, new_content))
        
        # Flag if significant logging removed
        if old_log_count - new_log_count >= 3:
            removed = old_log_count - new_log_count
            violations.append(HarnessViolation(
                severity=constraint.severity,
                check=CheckType.NEGATIVE_CONSTRAINT,
                service_id=service_id,
                file_path=diff.file_path,
                description=f"{removed} logging statement(s) removed",
                fix_hint="Maintain logging for observability",
                details={"constraint": constraint.name, "removed_count": removed},
            ))
        
        return violations
    
    def _check_env_hardcoding(
        self,
        service_id: str,
        diff: FileDiff,
        constraint: NegativeConstraint
    ) -> List[HarnessViolation]:
        """Check that env vars are not replaced with hardcoded values."""
        violations = []
        old_content = diff.original_content or ""
        new_content = diff.modified_content
        
        # Find process.env usages that were removed
        env_pattern = r'process\.env\.(\w+)'
        
        old_env_vars = set(re.findall(env_pattern, old_content))
        new_env_vars = set(re.findall(env_pattern, new_content))
        
        removed_env_vars = old_env_vars - new_env_vars
        
        for var in removed_env_vars:
            # Check if the variable name appears as a hardcoded string in new content
            if f"'{var}'" in new_content or f'"{var}"' in new_content:
                continue  # Probably just renamed, not hardcoded
            
            violations.append(HarnessViolation(
                severity=constraint.severity,
                check=CheckType.NEGATIVE_CONSTRAINT,
                service_id=service_id,
                file_path=diff.file_path,
                description=f"Environment variable '{var}' removed - may be hardcoded",
                fix_hint=f"Keep using process.env.{var}",
                details={"constraint": constraint.name, "env_var": var},
            ))
        
        return violations
