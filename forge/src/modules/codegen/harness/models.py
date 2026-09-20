"""
Harness Data Models
===================

Core data structures for the verification harness.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Any


class ViolationSeverity(str, Enum):
    """Severity levels for violations."""
    ERROR = "error"      # Hard failure - blocks merge
    WARNING = "warning"  # Should review - may be intentional
    INFO = "info"        # Informational - no action needed


class CheckType(str, Enum):
    """Types of verification checks."""
    SYNTAX = "syntax"
    IMPORT = "import"
    HALLUCINATION = "hallucination"
    SECURITY = "security"
    CONTRACT = "contract"
    NEGATIVE_CONSTRAINT = "negative_constraint"


@dataclass
class FileDiff:
    """Represents a proposed file change."""
    file_path: str
    original_content: str
    modified_content: str
    service_id: Optional[str] = None
    task_id: Optional[str] = None
    
    @property
    def is_new_file(self) -> bool:
        return not self.original_content or self.original_content.strip() == ""
    
    @property
    def lines_added(self) -> int:
        orig_lines = len(self.original_content.splitlines()) if self.original_content else 0
        new_lines = len(self.modified_content.splitlines()) if self.modified_content else 0
        return max(0, new_lines - orig_lines)
    
    @property
    def lines_removed(self) -> int:
        orig_lines = len(self.original_content.splitlines()) if self.original_content else 0
        new_lines = len(self.modified_content.splitlines()) if self.modified_content else 0
        return max(0, orig_lines - new_lines)


@dataclass
class HarnessViolation:
    """A single verification violation found by the harness."""
    severity: ViolationSeverity
    check: CheckType
    service_id: str
    file_path: str
    description: str
    fix_hint: Optional[str] = None
    line_number: Optional[int] = None
    column: Optional[int] = None
    details: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "severity": self.severity.value,
            "check": self.check.value,
            "service_id": self.service_id,
            "file_path": self.file_path,
            "description": self.description,
            "fix_hint": self.fix_hint,
            "line_number": self.line_number,
            "column": self.column,
            "details": self.details,
        }
    
    def __str__(self) -> str:
        loc = f":{self.line_number}" if self.line_number else ""
        return f"[{self.severity.value.upper()}] {self.check.value}: {self.file_path}{loc} - {self.description}"


@dataclass
class HarnessResult:
    """Complete result of harness verification."""
    passed: bool
    violations: List[HarnessViolation] = field(default_factory=list)
    checks_run: List[str] = field(default_factory=list)
    duration_ms: float = 0.0
    
    @property
    def errors(self) -> List[HarnessViolation]:
        return [v for v in self.violations if v.severity == ViolationSeverity.ERROR]
    
    @property
    def warnings(self) -> List[HarnessViolation]:
        return [v for v in self.violations if v.severity == ViolationSeverity.WARNING]
    
    @property
    def error_count(self) -> int:
        return len(self.errors)
    
    @property
    def warning_count(self) -> int:
        return len(self.warnings)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "checks_run": self.checks_run,
            "duration_ms": self.duration_ms,
            "violations": [v.to_dict() for v in self.violations],
        }
    
    def get_feedback_for_agent(self) -> str:
        """Format violations as actionable feedback for the LLM agent."""
        if self.passed:
            return "All harness checks passed."
        
        lines = [f"Harness verification FAILED: {self.error_count} errors, {self.warning_count} warnings\n"]
        
        for v in self.errors:
            lines.append(f"ERROR [{v.check.value}] {v.file_path}")
            lines.append(f"  Issue: {v.description}")
            if v.fix_hint:
                lines.append(f"  Fix: {v.fix_hint}")
            if v.line_number:
                lines.append(f"  Location: line {v.line_number}")
            lines.append("")
        
        for v in self.warnings[:5]:  # Limit warnings to 5
            lines.append(f"WARNING [{v.check.value}] {v.file_path}: {v.description}")
        
        if len(self.warnings) > 5:
            lines.append(f"... and {len(self.warnings) - 5} more warnings")
        
        return "\n".join(lines)


@dataclass
class CheckResult:
    """Result of a single check."""
    check_type: CheckType
    passed: bool
    violations: List[HarnessViolation] = field(default_factory=list)
    duration_ms: float = 0.0
    skipped: bool = False
    skip_reason: Optional[str] = None
