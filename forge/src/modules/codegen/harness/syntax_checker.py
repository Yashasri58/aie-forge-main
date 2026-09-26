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

import logging
logger = logging.getLogger("forge.codegen.harness")

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
        
        js_diffs = [d for d in diffs if self._is_javascript_file(d.file_path)]
        logger.info(f"[SYNTAX] service={service_id}: Checking {len(js_diffs)}/{len(diffs)} JS/TS files")
        
        for diff in diffs:
            # Only check JS/TS files
            if not self._is_javascript_file(diff.file_path):
                continue
            
            method = "node" if self._is_node_available() else "structural"
            logger.debug(f"[SYNTAX]    {diff.file_path} via {method} ({len(diff.modified_content or '')} chars)")
            file_violations = self._check_file(service_id, diff)
            if file_violations:
                errors = [v for v in file_violations if v.severity == ViolationSeverity.ERROR]
                logger.error(f"[SYNTAX]    {diff.file_path}: {len(errors)} errors")
                for v in errors:
                    logger.error(f"[SYNTAX]      line {v.line_number}: {v.description}")
            else:
                logger.debug(f"[SYNTAX]    {diff.file_path}: OK")
            violations.extend(file_violations)
        
        passed = len([v for v in violations if v.severity == ViolationSeverity.ERROR]) == 0
        logger.info(f"[SYNTAX] service={service_id}: {'PASS' if passed else 'FAIL'} — {len(violations)} violations")
        return CheckResult(
            check_type=CheckType.SYNTAX,
            passed=passed,
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
        logger.info(f"[SYNTAX][NODE] _check_with_node: file={diff.file_path} content_len={len(diff.modified_content or '')}")
        
        try:
            # Write content to temp file
            suffix = Path(diff.file_path).suffix or '.js'
            logger.info(f"[SYNTAX][NODE] creating temp file suffix={suffix}")
            with tempfile.NamedTemporaryFile(
                mode='w',
                suffix=suffix,
                delete=False,
                encoding='utf-8'
            ) as f:
                f.write(diff.modified_content)
                temp_path = f.name
            logger.info(f"[SYNTAX][NODE] temp file written: {temp_path}")
            
            try:
                # Run node --check
                logger.info(f"[SYNTAX][NODE] running: node --check {temp_path}")
                result = subprocess.run(
                    [self.node_path, "--check", temp_path],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                logger.info(f"[SYNTAX][NODE] node returncode={result.returncode}")
                logger.info(f"[SYNTAX][NODE] node stdout={result.stdout[:300]!r}")
                logger.info(f"[SYNTAX][NODE] node stderr={result.stderr[:300]!r}")
                
                if result.returncode != 0:
                    # Parse error message
                    error_msg = result.stderr or result.stdout
                    logger.info(f"[SYNTAX][NODE] SYNTAX ERROR raw error_msg={error_msg[:300]!r}")
                    line_num = self._extract_line_number(error_msg)
                    logger.info(f"[SYNTAX][NODE] extracted line_num={line_num}")
                    clean_msg = self._clean_error_message(error_msg)
                    logger.info(f"[SYNTAX][NODE] clean_msg={clean_msg!r}")
                    
                    violations.append(HarnessViolation(
                        severity=ViolationSeverity.ERROR,
                        check=CheckType.SYNTAX,
                        service_id=service_id,
                        file_path=diff.file_path,
                        description=clean_msg,
                        line_number=line_num,
                        fix_hint="Fix the syntax error before proceeding",
                    ))
                    logger.info(f"[SYNTAX][NODE] violation added: line={line_num} desc={clean_msg!r}")
                else:
                    logger.info(f"[SYNTAX][NODE] PASS — no syntax errors")
            finally:
                os.unlink(temp_path)
                logger.info(f"[SYNTAX][NODE] temp file deleted")
            
            logger.info(f"[SYNTAX][NODE] returning {len(violations)} violations")
            return violations
            
        except subprocess.TimeoutExpired:
            logger.warning(f"[SYNTAX][NODE] TIMEOUT — falling back")
            return None  # Timeout - fall back to other methods
        except Exception as e:
            logger.error(f"[SYNTAX][NODE] EXCEPTION: {e}", exc_info=True)
            return None  # Any error - fall back
    
    def _extract_line_number(self, error_msg: str) -> Optional[int]:
        """Extract line number from node error message."""
        logger.info(f"[SYNTAX][LINE_NUM] extracting from: {error_msg[:200]!r}")
        # node stderr format: C:\path\to\tmpXXX.js:LINE\n  code\n  ^\n\nSyntaxError: ...
        # We must match the FIRST :LINE: occurrence (the file line), NOT internal stack traces.
        # Strategy: find the temp file path pattern and grab the line number immediately after it.
        match = re.search(r'\.js:(\d+)\n', error_msg)
        if match:
            val = int(match.group(1))
            logger.info(f"[SYNTAX][LINE_NUM] matched file:line pattern → line={val}")
            return val
        # Fallback: first :digits: not preceded by internal/ (avoids loader:1713)
        match = re.search(r'(?<!internal/modules/cjs/loader):(\d+):\d+', error_msg)
        if match:
            val = int(match.group(1))
            logger.info(f"[SYNTAX][LINE_NUM] fallback match → line={val}")
            return val
        logger.warning(f"[SYNTAX][LINE_NUM] no match found — returning None")
        return None

    def _clean_error_message(self, error_msg: str) -> str:
        """Clean up node error message for display."""
        logger.info(f"[SYNTAX][CLEAN_MSG] input: {error_msg[:300]!r}")
        # Extract the SyntaxError: line which has the actual description
        match = re.search(r'(SyntaxError:[^\n]+)', error_msg)
        if match:
            result = match.group(1).strip()
            logger.info(f"[SYNTAX][CLEAN_MSG] extracted SyntaxError line: {result!r}")
            return result[:200]
        # Fallback: strip temp file path and return first meaningful line
        lines = error_msg.strip().split('\n')
        for line in lines:
            line = line.strip()
            if line and not line.startswith('(') and not line.startswith('at '):
                # Remove temp file path prefix
                line = re.sub(r'^[A-Za-z]:\\[^:]+\.js:\d+\s*', '', line)
                line = re.sub(r'^/tmp/[^:]+:\d+\s*', '', line)
                if line:
                    logger.info(f"[SYNTAX][CLEAN_MSG] fallback result: {line[:200]!r}")
                    return line[:200]
        logger.warning(f"[SYNTAX][CLEAN_MSG] could not extract clean message")
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
