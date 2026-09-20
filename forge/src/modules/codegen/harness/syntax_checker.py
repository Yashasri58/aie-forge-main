"""
Syntax Checker
==============

Validates JavaScript/TypeScript syntax using multiple methods:
1. Node.js --check (subprocess, most accurate)
2. Regex-based bracket/quote matching (fast fallback)
3. Basic structural validation

This is Tier 1 - runs first and fails fast on syntax errors.
"""

import re
import subprocess
import tempfile
import os
from typing import List, Optional
from pathlib import Path

from .models import (
    HarnessViolation,
    ViolationSeverity,
    CheckType,
    FileDiff,
    CheckResult,
)


class SyntaxChecker:
    """
    Validates code syntax without executing it.
    
    For JavaScript:
    - Uses `node --check` for accurate parsing
    - Falls back to structural validation if node unavailable
    """
    
    def __init__(self, node_path: str = "node"):
        self.node_path = node_path
        self._node_available = None
    
    def check(self, service_id: str, diffs: List[FileDiff]) -> CheckResult:
        """
        Run syntax validation on all diffs.
        
        Args:
            service_id: Service being checked
            diffs: List of file changes to validate
        
        Returns:
            CheckResult with any syntax violations
        """
        violations = []
        
        for diff in diffs:
            # Only check JS/TS files
            if not self._is_javascript_file(diff.file_path):
                continue
            
            file_violations = self._check_file(service_id, diff)
            violations.extend(file_violations)
        
        return CheckResult(
            check_type=CheckType.SYNTAX,
            passed=len([v for v in violations if v.severity == ViolationSeverity.ERROR]) == 0,
            violations=violations,
        )
    
    def _is_javascript_file(self, path: str) -> bool:
        """Check if file is JavaScript/TypeScript."""
        return path.endswith(('.js', '.ts', '.jsx', '.tsx', '.mjs', '.cjs'))
    
    def _check_file(self, service_id: str, diff: FileDiff) -> List[HarnessViolation]:
        """Check syntax of a single file."""
        violations = []
        content = diff.modified_content
        
        if not content or not content.strip():
            return violations
        
        # Try node --check first
        if self._is_node_available():
            node_violations = self._check_with_node(service_id, diff)
            if node_violations is not None:
                return node_violations
        
        # Fallback to structural validation
        violations.extend(self._check_brackets(service_id, diff))
        violations.extend(self._check_quotes(service_id, diff))
        violations.extend(self._check_common_errors(service_id, diff))
        
        return violations
    
    def _is_node_available(self) -> bool:
        """Check if Node.js is available."""
        if self._node_available is None:
            try:
                result = subprocess.run(
                    [self.node_path, "--version"],
                    capture_output=True,
                    timeout=5
                )
                self._node_available = result.returncode == 0
            except Exception:
                self._node_available = False
        return self._node_available
    
    def _check_with_node(self, service_id: str, diff: FileDiff) -> Optional[List[HarnessViolation]]:
        """
        Use node --check for accurate syntax validation.
        
        Returns None if node check fails (fallback to other methods).
        """
        violations = []
        
        try:
            # Write content to temp file
            suffix = Path(diff.file_path).suffix or '.js'
            with tempfile.NamedTemporaryFile(
                mode='w',
                suffix=suffix,
                delete=False,
                encoding='utf-8'
            ) as f:
                f.write(diff.modified_content)
                temp_path = f.name
            
            try:
                # Run node --check
                result = subprocess.run(
                    [self.node_path, "--check", temp_path],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                
                if result.returncode != 0:
                    # Parse error message
                    error_msg = result.stderr or result.stdout
                    line_num = self._extract_line_number(error_msg)
                    
                    violations.append(HarnessViolation(
                        severity=ViolationSeverity.ERROR,
                        check=CheckType.SYNTAX,
                        service_id=service_id,
                        file_path=diff.file_path,
                        description=self._clean_error_message(error_msg),
                        line_number=line_num,
                        fix_hint="Fix the syntax error before proceeding",
                    ))
            finally:
                os.unlink(temp_path)
            
            return violations
            
        except subprocess.TimeoutExpired:
            return None  # Timeout - fall back to other methods
        except Exception:
            return None  # Any error - fall back
    
    def _extract_line_number(self, error_msg: str) -> Optional[int]:
        """Extract line number from node error message."""
        # Pattern: filename:line:column
        match = re.search(r':(\d+):\d+', error_msg)
        if match:
            return int(match.group(1))
        return None
    
    def _clean_error_message(self, error_msg: str) -> str:
        """Clean up node error message for display."""
        lines = error_msg.strip().split('\n')
        # Get first meaningful line
        for line in lines:
            line = line.strip()
            if line and not line.startswith('('):
                # Remove temp file path
                line = re.sub(r'[A-Za-z]:\\[^:]+:', '', line)
                line = re.sub(r'/tmp/[^:]+:', '', line)
                return line[:200]  # Limit length
        return error_msg[:200]
    
    def _check_brackets(self, service_id: str, diff: FileDiff) -> List[HarnessViolation]:
        """Check for mismatched brackets."""
        violations = []
        content = diff.modified_content
        
        # Track bracket pairs
        stack = []
        pairs = {')': '(', ']': '[', '}': '{'}
        openers = set(pairs.values())
        closers = set(pairs.keys())
        
        in_string = False
        string_char = None
        in_comment = False
        in_multiline_comment = False
        
        lines = content.split('\n')
        for line_num, line in enumerate(lines, 1):
            i = 0
            while i < len(line):
                char = line[i]
                
                # Handle comments
                if not in_string:
                    if i < len(line) - 1:
                        two_char = line[i:i+2]
                        if two_char == '//' and not in_multiline_comment:
                            break  # Rest of line is comment
                        if two_char == '/*':
                            in_multiline_comment = True
                            i += 2
                            continue
                        if two_char == '*/' and in_multiline_comment:
                            in_multiline_comment = False
                            i += 2
                            continue
                
                if in_multiline_comment:
                    i += 1
                    continue
                
                # Handle strings
                if char in ('"', "'", '`'):
                    if not in_string:
                        in_string = True
                        string_char = char
                    elif char == string_char and (i == 0 or line[i-1] != '\\'):
                        in_string = False
                        string_char = None
                    i += 1
                    continue
                
                if in_string:
                    i += 1
                    continue
                
                # Track brackets
                if char in openers:
                    stack.append((char, line_num))
                elif char in closers:
                    expected = pairs[char]
                    if not stack:
                        violations.append(HarnessViolation(
                            severity=ViolationSeverity.ERROR,
                            check=CheckType.SYNTAX,
                            service_id=service_id,
                            file_path=diff.file_path,
                            description=f"Unexpected closing bracket '{char}'",
                            line_number=line_num,
                            fix_hint=f"Remove or match this '{char}'",
                        ))
                    elif stack[-1][0] != expected:
                        violations.append(HarnessViolation(
                            severity=ViolationSeverity.ERROR,
                            check=CheckType.SYNTAX,
                            service_id=service_id,
                            file_path=diff.file_path,
                            description=f"Mismatched brackets: expected '{stack[-1][0]}' but found '{char}'",
                            line_number=line_num,
                            fix_hint="Check bracket matching",
                        ))
                    else:
                        stack.pop()
                
                i += 1
        
        # Check for unclosed brackets
        for bracket, line_num in stack:
            violations.append(HarnessViolation(
                severity=ViolationSeverity.ERROR,
                check=CheckType.SYNTAX,
                service_id=service_id,
                file_path=diff.file_path,
                description=f"Unclosed bracket '{bracket}'",
                line_number=line_num,
                fix_hint=f"Add closing bracket for '{bracket}'",
            ))
        
        return violations
    
    def _check_quotes(self, service_id: str, diff: FileDiff) -> List[HarnessViolation]:
        """Check for unclosed string literals."""
        violations = []
        content = diff.modified_content
        
        lines = content.split('\n')
        for line_num, line in enumerate(lines, 1):
            # Skip comment lines
            stripped = line.strip()
            if stripped.startswith('//') or stripped.startswith('*'):
                continue
            
            # Count quotes (basic check - doesn't handle all edge cases)
            single_quotes = line.count("'") - line.count("\\'")
            double_quotes = line.count('"') - line.count('\\"')
            
            # Template literals can span multiple lines
            backticks = line.count('`') - line.count('\\`')
            
            if single_quotes % 2 != 0:
                # Check if it's a contraction (e.g., don't, it's)
                if not re.search(r"\w'\w", line):
                    violations.append(HarnessViolation(
                        severity=ViolationSeverity.WARNING,
                        check=CheckType.SYNTAX,
                        service_id=service_id,
                        file_path=diff.file_path,
                        description="Possible unclosed single quote",
                        line_number=line_num,
                        fix_hint="Check string literal",
                    ))
            
            if double_quotes % 2 != 0:
                violations.append(HarnessViolation(
                    severity=ViolationSeverity.WARNING,
                    check=CheckType.SYNTAX,
                    service_id=service_id,
                    file_path=diff.file_path,
                    description="Possible unclosed double quote",
                    line_number=line_num,
                    fix_hint="Check string literal",
                ))
        
        return violations
    
    def _check_common_errors(self, service_id: str, diff: FileDiff) -> List[HarnessViolation]:
        """Check for common JavaScript syntax errors."""
        violations = []
        content = diff.modified_content
        lines = content.split('\n')
        
        for line_num, line in enumerate(lines, 1):
            stripped = line.strip()
            
            # Skip comments
            if stripped.startswith('//') or stripped.startswith('*'):
                continue
            
            # Check for = instead of == in conditions
            if re.search(r'\bif\s*\([^=]*[^=!<>]=[^=][^)]*\)', line):
                if '==' not in line and '===' not in line:
                    violations.append(HarnessViolation(
                        severity=ViolationSeverity.WARNING,
                        check=CheckType.SYNTAX,
                        service_id=service_id,
                        file_path=diff.file_path,
                        description="Possible assignment instead of comparison in if condition",
                        line_number=line_num,
                        fix_hint="Use == or === for comparison",
                    ))
            
            # Check for missing semicolon after return with value on next line
            if stripped == 'return':
                if line_num < len(lines):
                    next_line = lines[line_num].strip()
                    if next_line and not next_line.startswith(('/', '*', '}', ';')):
                        violations.append(HarnessViolation(
                            severity=ViolationSeverity.WARNING,
                            check=CheckType.SYNTAX,
                            service_id=service_id,
                            file_path=diff.file_path,
                            description="Return statement possibly missing value (ASI issue)",
                            line_number=line_num,
                            fix_hint="Put return value on same line or add semicolon",
                        ))
        
        return violations
