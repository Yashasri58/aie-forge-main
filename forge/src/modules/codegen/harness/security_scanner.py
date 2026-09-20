"""
Security Scanner
================

Detects dangerous code patterns that could introduce security vulnerabilities:
1. eval/exec usage
2. Hardcoded secrets/credentials
3. SQL injection vulnerabilities
4. Command injection risks
5. Insecure crypto usage
6. XSS-prone patterns

Based on:
- OWASP Top 10
- Common JavaScript security anti-patterns
- vallm security scanning approach
"""

import re
from typing import List, Dict, Any, Optional, Tuple
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
class SecurityPattern:
    """A security anti-pattern to detect."""
    name: str
    pattern: str
    severity: ViolationSeverity
    description: str
    fix_hint: str
    flags: int = re.IGNORECASE


# Security patterns to detect
SECURITY_PATTERNS: List[SecurityPattern] = [
    # Code execution
    SecurityPattern(
        name="eval_usage",
        pattern=r'\beval\s*\(',
        severity=ViolationSeverity.ERROR,
        description="Use of eval() is dangerous - allows arbitrary code execution",
        fix_hint="Replace eval() with safer alternatives like JSON.parse() or specific parsers",
    ),
    SecurityPattern(
        name="function_constructor",
        pattern=r'\bnew\s+Function\s*\(',
        severity=ViolationSeverity.ERROR,
        description="new Function() is equivalent to eval() - dangerous",
        fix_hint="Use explicit function definitions instead",
    ),
    SecurityPattern(
        name="settimeout_string",
        pattern=r'\bsetTimeout\s*\(\s*["\'][^"\']+["\']',
        severity=ViolationSeverity.WARNING,
        description="setTimeout with string argument acts like eval()",
        fix_hint="Pass a function reference instead of a string",
    ),
    SecurityPattern(
        name="setinterval_string",
        pattern=r'\bsetInterval\s*\(\s*["\'][^"\']+["\']',
        severity=ViolationSeverity.WARNING,
        description="setInterval with string argument acts like eval()",
        fix_hint="Pass a function reference instead of a string",
    ),
    
    # Command injection
    SecurityPattern(
        name="child_process_exec",
        pattern=r'\bexec\s*\([^)]*\$\{',
        severity=ViolationSeverity.ERROR,
        description="Command injection risk - user input in exec()",
        fix_hint="Use execFile() with array arguments, or sanitize input",
    ),
    SecurityPattern(
        name="shell_command",
        pattern=r'\bexec(?:Sync)?\s*\(\s*[`"\'][^`"\']*\+',
        severity=ViolationSeverity.WARNING,
        description="Possible command injection - concatenating strings in exec()",
        fix_hint="Use parameterized commands or execFile()",
    ),
    SecurityPattern(
        name="child_process_exec_general",
        pattern=r'(?:child_process|require\s*\(\s*["\']child_process["\']\s*\)).*\.exec\s*\(',
        severity=ViolationSeverity.WARNING,
        description="child_process.exec() runs commands in shell - prefer execFile()",
        fix_hint="Use execFile() or spawn() with explicit arguments array",
        flags=re.IGNORECASE | re.DOTALL,
    ),
    
    # SQL injection
    SecurityPattern(
        name="sql_injection_template",
        pattern=r'(?:SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER)\s+[^;]*\$\{',
        severity=ViolationSeverity.ERROR,
        description="SQL injection vulnerability - template literal in SQL query",
        fix_hint="Use parameterized queries or prepared statements",
        flags=re.IGNORECASE,
    ),
    SecurityPattern(
        name="sql_concat",
        pattern=r'(?:SELECT|INSERT|UPDATE|DELETE)\s+[^;]*\'\s*\+\s*\w+\s*\+\s*\'',
        severity=ViolationSeverity.ERROR,
        description="SQL injection via string concatenation",
        fix_hint="Use parameterized queries instead of string concatenation",
        flags=re.IGNORECASE,
    ),
    SecurityPattern(
        name="sql_concat_simple",
        pattern=r'(?:SELECT|INSERT|UPDATE|DELETE|WHERE)\s+[^;]*["\']?\s*\+\s*(?:req\.|params\.|query\.)',
        severity=ViolationSeverity.ERROR,
        description="SQL injection - concatenating request parameters into query",
        fix_hint="Use parameterized queries with placeholders (?, $1, etc.)",
        flags=re.IGNORECASE,
    ),
    SecurityPattern(
        name="sql_string_interpolation",
        pattern=r'(?:query|execute|sql)\s*\(\s*`[^`]*\$\{',
        severity=ViolationSeverity.ERROR,
        description="SQL injection via template literal interpolation",
        fix_hint="Use parameterized queries instead of template literals",
        flags=re.IGNORECASE,
    ),
    
    # Hardcoded secrets
    SecurityPattern(
        name="hardcoded_password",
        pattern=r'(?:password|passwd|pwd)\s*[:=]\s*["\'][^"\']{4,}["\']',
        severity=ViolationSeverity.ERROR,
        description="Hardcoded password detected",
        fix_hint="Use environment variables or a secrets manager",
        flags=re.IGNORECASE,
    ),
    SecurityPattern(
        name="hardcoded_api_key",
        pattern=r'(?:api[_-]?key|apikey|api[_-]?secret)\s*[:=]\s*["\'][a-zA-Z0-9_-]{16,}["\']',
        severity=ViolationSeverity.ERROR,
        description="Hardcoded API key detected",
        fix_hint="Use environment variables or a secrets manager",
        flags=re.IGNORECASE,
    ),
    SecurityPattern(
        name="hardcoded_token",
        pattern=r'(?:token|bearer|auth[_-]?token)\s*[:=]\s*["\'][a-zA-Z0-9_.-]{20,}["\']',
        severity=ViolationSeverity.WARNING,
        description="Possible hardcoded token detected",
        fix_hint="Use environment variables instead",
        flags=re.IGNORECASE,
    ),
    SecurityPattern(
        name="private_key",
        pattern=r'-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----',
        severity=ViolationSeverity.ERROR,
        description="Private key embedded in code",
        fix_hint="Load private keys from secure file storage or secrets manager",
    ),
    
    # XSS vulnerabilities
    SecurityPattern(
        name="innerhtml_assignment",
        pattern=r'\.innerHTML\s*=',
        severity=ViolationSeverity.WARNING,
        description="XSS risk - setting innerHTML can execute malicious scripts",
        fix_hint="Use textContent for plain text, or sanitize HTML with DOMPurify",
    ),
    SecurityPattern(
        name="innerhtml_dynamic",
        pattern=r'\.innerHTML\s*=\s*[^;]*(?:\$\{|\+\s*\w+)',
        severity=ViolationSeverity.ERROR,
        description="XSS vulnerability - innerHTML with dynamic content",
        fix_hint="Use textContent or sanitize HTML before setting innerHTML",
    ),
    SecurityPattern(
        name="document_write",
        pattern=r'\bdocument\.write\s*\(',
        severity=ViolationSeverity.WARNING,
        description="document.write() is often a sign of XSS vulnerability",
        fix_hint="Use DOM manipulation methods instead",
    ),
    
    # Insecure crypto
    SecurityPattern(
        name="md5_usage",
        pattern=r'["\']md5["\']|\.createHash\s*\(\s*["\']md5["\']',
        severity=ViolationSeverity.WARNING,
        description="MD5 is cryptographically broken - don't use for security",
        fix_hint="Use SHA-256 or bcrypt for passwords",
    ),
    SecurityPattern(
        name="sha1_usage",
        pattern=r'["\']sha1["\']|\.createHash\s*\(\s*["\']sha1["\']',
        severity=ViolationSeverity.WARNING,
        description="SHA-1 is deprecated - consider SHA-256",
        fix_hint="Use SHA-256 or stronger hash algorithms",
    ),
    
    # Insecure configurations
    SecurityPattern(
        name="cors_allow_all",
        pattern=r'(?:Access-Control-Allow-Origin|origin)\s*[:=]\s*["\']?\s*\*',
        severity=ViolationSeverity.WARNING,
        description="CORS configured to allow all origins",
        fix_hint="Specify allowed origins explicitly",
    ),
    SecurityPattern(
        name="disable_ssl",
        pattern=r'rejectUnauthorized\s*:\s*false|NODE_TLS_REJECT_UNAUTHORIZED\s*=\s*["\']?0',
        severity=ViolationSeverity.ERROR,
        description="SSL certificate validation disabled",
        fix_hint="Enable SSL validation in production",
    ),
    
    # Path traversal
    SecurityPattern(
        name="path_traversal",
        pattern=r'(?:readFile|writeFile|createReadStream|createWriteStream)\s*\([^)]*\.\.',
        severity=ViolationSeverity.WARNING,
        description="Possible path traversal vulnerability",
        fix_hint="Validate and sanitize file paths, use path.resolve() and check bounds",
    ),
]


class SecurityScanner:
    """
    Scans code for security vulnerabilities and anti-patterns.
    
    This is a deterministic, pattern-based scanner that catches
    common security issues without running the code.
    """
    
    def __init__(self, custom_patterns: List[SecurityPattern] = None):
        """
        Args:
            custom_patterns: Additional security patterns to check
        """
        self.patterns = SECURITY_PATTERNS.copy()
        if custom_patterns:
            self.patterns.extend(custom_patterns)
    
    def check(self, service_id: str, diffs: List[FileDiff]) -> CheckResult:
        """
        Scan all diffs for security issues.
        
        Args:
            service_id: Service being checked
            diffs: List of file changes
        
        Returns:
            CheckResult with security violations
        """
        violations = []
        
        code_diffs = [d for d in diffs if self._is_code_file(d.file_path)]
        logger.info(f"[SECURITY] service={service_id}: Scanning {len(code_diffs)}/{len(diffs)} files ({len(self.patterns)} patterns)")
        
        for diff in diffs:
            if not self._is_code_file(diff.file_path):
                continue
            
            file_violations = self._scan_file(service_id, diff)
            if file_violations:
                errors = [v for v in file_violations if v.severity == ViolationSeverity.ERROR]
                warns  = [v for v in file_violations if v.severity != ViolationSeverity.ERROR]
                logger.warning(f"[SECURITY]    {diff.file_path}: {len(errors)} errors, {len(warns)} warnings")
                for v in file_violations:
                    lvl = logger.error if v.severity == ViolationSeverity.ERROR else logger.warning
                    lvl(f"[SECURITY]      [{v.severity.value}] line {v.line_number} — {v.name}: {v.description[:80]}")
            else:
                logger.debug(f"[SECURITY]    {diff.file_path}: clean")
            violations.extend(file_violations)
        
        passed = len([v for v in violations if v.severity == ViolationSeverity.ERROR]) == 0
        logger.info(f"[SECURITY] service={service_id}: {'PASS' if passed else 'FAIL'} — {len(violations)} findings")
        return CheckResult(
            check_type=CheckType.SECURITY,
            passed=passed,
            violations=violations,
        )
    
    def _is_code_file(self, path: str) -> bool:
        """Check if file should be scanned."""
        return path.endswith(('.js', '.ts', '.jsx', '.tsx', '.mjs', '.cjs', '.json'))
    
    def _scan_file(self, service_id: str, diff: FileDiff) -> List[HarnessViolation]:
        """Scan a single file for security issues."""
        violations = []
        content = diff.modified_content
        
        if not content:
            return violations
        
        # Check each pattern
        for pattern in self.patterns:
            pattern_violations = self._check_pattern(
                service_id, diff, pattern
            )
            violations.extend(pattern_violations)
        
        # Additional context-aware checks
        violations.extend(self._check_new_security_issues(service_id, diff))
        
        return violations
    
    def _check_pattern(
        self,
        service_id: str,
        diff: FileDiff,
        pattern: SecurityPattern
    ) -> List[HarnessViolation]:
        """Check for a specific security pattern."""
        violations = []
        content = diff.modified_content
        
        try:
            regex = re.compile(pattern.pattern, pattern.flags)
        except re.error:
            return violations
        
        for match in regex.finditer(content):
            # Find line number
            line_num = content[:match.start()].count('\n') + 1
            
            # Get context (the matched line)
            lines = content.split('\n')
            context = lines[line_num - 1].strip() if line_num <= len(lines) else ""
            
            violations.append(HarnessViolation(
                severity=pattern.severity,
                check=CheckType.SECURITY,
                service_id=service_id,
                file_path=diff.file_path,
                description=pattern.description,
                line_number=line_num,
                fix_hint=pattern.fix_hint,
                details={
                    "pattern_name": pattern.name,
                    "matched_text": match.group(0)[:100],
                    "context": context[:100],
                },
            ))
        
        return violations
    
    def _check_new_security_issues(
        self, service_id: str, diff: FileDiff
    ) -> List[HarnessViolation]:
        """
        Check for security issues introduced by the change.
        
        Only flags issues that are NEW in the modified content.
        """
        violations = []
        
        new_content = diff.modified_content
        old_content = diff.original_content or ""
        
        # Check for newly introduced dangerous patterns
        dangerous_patterns = [
            (r'process\.env\[.*\+', "Dynamic environment variable access", ViolationSeverity.WARNING),
            (r'JSON\.parse\s*\(\s*req\.', "Parsing untrusted JSON from request", ViolationSeverity.WARNING),
            (r'\.query\s*\(\s*[`"\']', "Check for parameterized queries", ViolationSeverity.INFO),
        ]
        
        for pattern, desc, severity in dangerous_patterns:
            # Only flag if new
            new_matches = set(re.findall(pattern, new_content, re.IGNORECASE))
            old_matches = set(re.findall(pattern, old_content, re.IGNORECASE))
            
            if new_matches - old_matches:
                for match in new_matches - old_matches:
                    line_num = self._find_pattern_line(pattern, new_content)
                    violations.append(HarnessViolation(
                        severity=severity,
                        check=CheckType.SECURITY,
                        service_id=service_id,
                        file_path=diff.file_path,
                        description=desc,
                        line_number=line_num,
                        fix_hint="Review this pattern for security implications",
                    ))
        
        return violations
    
    def _find_pattern_line(self, pattern: str, content: str) -> Optional[int]:
        """Find line number of first pattern match."""
        try:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                return content[:match.start()].count('\n') + 1
        except Exception:
            pass
        return None
