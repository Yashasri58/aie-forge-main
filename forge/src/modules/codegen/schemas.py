"""
Code Generation Schemas.

Defines all data structures used in the code generation pipeline.
These schemas are the contract between all components.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Any
import time
import uuid


# =============================================================================
# ENUMS
# =============================================================================

class CodeGenStage(str, Enum):
    """Stages of code generation pipeline."""
    PENDING = "pending"                    # Not started
    DESIGNING = "designing"                # Design Agent working
    DESIGN_COMPLETE = "design_complete"    # Plan ready for review (optional)
    DISTRIBUTING = "distributing"          # Creating task files
    IMPLEMENTING = "implementing"          # Implementation agents working
    VERIFYING = "verifying"                # Verification in progress
    FIXING = "fixing"                      # Fixing failed tasks
    AWAITING_APPROVAL = "awaiting_approval"# Ready for user approval
    APPROVED = "approved"                  # User approved
    REJECTED = "rejected"                  # User rejected
    FAILED = "failed"                      # Unrecoverable error


class TaskAction(str, Enum):
    """Type of file action."""
    CREATE = "create"
    MODIFY = "modify"
    DELETE = "delete"


class ChangeType(str, Enum):
    """Type of code change."""
    ADD = "add"
    MODIFY = "modify"
    DELETE = "delete"
    WRAP = "wrap"
    REPLACE = "replace"
    UNKNOWN = "unknown"


class ContractType(str, Enum):
    """Type of interface contract."""
    FUNCTION = "function"
    CLASS = "class"
    TYPE = "type"
    INTERFACE = "interface"
    CONSTANT = "constant"
    OBJECT = "object"
    METHOD = "method"
    PROPERTY = "property"
    UNKNOWN = "unknown"


class LocationType(str, Enum):
    """Type of location in a file."""
    FUNCTION = "function"
    CLASS = "class"
    METHOD = "method"
    LINE_RANGE = "line_range"
    IMPORT_SECTION = "import_section"
    FILE_START = "file_start"
    FILE_END = "file_end"
    JSON_PATH = "json_path"
    UNKNOWN = "unknown"


# =============================================================================
# PLAN COMPONENTS
# =============================================================================

@dataclass
class ExistingPattern:
    """An existing pattern found in the codebase."""
    pattern: str
    location: str
    reuse: bool
    rationale: str


@dataclass
class PlanAnalysis:
    """Analysis and reasoning for the plan."""
    summary: str
    reasoning: str
    existing_patterns: list[ExistingPattern] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)


@dataclass
class DesignDecision:
    """A design decision."""
    decision: str
    rationale: str


@dataclass
class Conventions:
    """Coding conventions to follow."""
    naming: str
    error_handling: str
    logging: str
    other: list[str] = field(default_factory=list)


@dataclass
class PlanDesign:
    """Design decisions section of the plan."""
    decisions: list[DesignDecision] = field(default_factory=list)
    conventions: Optional[Conventions] = None


@dataclass
class Contract:
    """An interface contract (function, type, etc.)."""
    name: str
    type: ContractType
    defined_in: str
    is_new: bool
    signature: str
    implementation: Optional[str] = None
    usage_example: str = ""
    used_by: list[str] = field(default_factory=list)
    notes: Optional[str] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "type": self.type.value if isinstance(self.type, ContractType) else self.type,
            "defined_in": self.defined_in,
            "is_new": self.is_new,
            "signature": self.signature,
            "implementation": self.implementation,
            "usage_example": self.usage_example,
            "used_by": self.used_by,
            "notes": self.notes,
        }


@dataclass
class ExecutionPhase:
    """An execution phase."""
    phase: int
    description: str
    tasks: list[str]  # Task IDs
    parallel: bool = True
    wait_for_completion: bool = True


@dataclass
class ChangeLocation:
    """Location of a change in a file."""
    type: LocationType
    target: str  # Function name, class name, or line range


@dataclass
class TaskChange:
    """A single change within a task."""
    location: ChangeLocation
    change_type: ChangeType
    description: str
    before: Optional[str] = None
    after: str = ""
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "location": {
                "type": self.location.type.value if isinstance(self.location.type, LocationType) else self.location.type,
                "target": self.location.target,
            },
            "change_type": self.change_type.value if isinstance(self.change_type, ChangeType) else self.change_type,
            "description": self.description,
            "before": self.before,
            "after": self.after,
        }


@dataclass
class TaskContext:
    """Context for a task."""
    read_files: list[str] = field(default_factory=list)
    relevant_symbols: list[str] = field(default_factory=list)
    notes: Optional[str] = None


@dataclass
class TaskValidation:
    """Validation requirements for a task."""
    must_compile: bool = True
    must_pass_lint: bool = True
    test_files: list[str] = field(default_factory=list)


@dataclass
class Task:
    """A task for an implementation agent."""
    id: str
    phase: int
    file: str
    service: str
    language: str
    action: TaskAction
    description: str
    changes: list[TaskChange] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    uses_contracts: list[str] = field(default_factory=list)
    defines_contracts: list[str] = field(default_factory=list)
    context: Optional[TaskContext] = None
    validation: Optional[TaskValidation] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "phase": self.phase,
            "file": self.file,
            "service": self.service,
            "language": self.language,
            "action": self.action.value if isinstance(self.action, TaskAction) else self.action,
            "description": self.description,
            "changes": [c.to_dict() for c in self.changes],
            "depends_on": self.depends_on,
            "uses_contracts": self.uses_contracts,
            "defines_contracts": self.defines_contracts,
            "context": {
                "read_files": self.context.read_files if self.context else [],
                "relevant_symbols": self.context.relevant_symbols if self.context else [],
                "notes": self.context.notes if self.context else None,
            } if self.context else None,
            "validation": {
                "must_compile": self.validation.must_compile if self.validation else True,
                "must_pass_lint": self.validation.must_pass_lint if self.validation else True,
                "test_files": self.validation.test_files if self.validation else [],
            } if self.validation else None,
        }


@dataclass
class Plan:
    """
    The complete execution plan (plan.json).
    
    This is "The Ultimatum" - contains everything needed to implement
    the code changes without any additional context or decisions.
    """
    id: str
    created_at: float
    change_request: str
    version: str = "1.0"
    
    analysis: Optional[PlanAnalysis] = None
    design: Optional[PlanDesign] = None
    contracts: dict[str, Contract] = field(default_factory=dict)
    execution: list[ExecutionPhase] = field(default_factory=list)
    tasks: dict[str, Task] = field(default_factory=dict)
    
    @classmethod
    def create(cls, change_request: str) -> "Plan":
        """Create a new plan with generated ID."""
        return cls(
            id=f"plan-{uuid.uuid4().hex[:12]}",
            created_at=time.time(),
            change_request=change_request,
        )
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "created_at": self.created_at,
            "change_request": self.change_request,
            "version": self.version,
            "analysis": {
                "summary": self.analysis.summary if self.analysis else "",
                "reasoning": self.analysis.reasoning if self.analysis else "",
                "existing_patterns": [
                    {
                        "pattern": p.pattern,
                        "location": p.location,
                        "reuse": p.reuse,
                        "rationale": p.rationale,
                    }
                    for p in (self.analysis.existing_patterns if self.analysis else [])
                ],
                "risks": self.analysis.risks if self.analysis else [],
                "assumptions": self.analysis.assumptions if self.analysis else [],
            } if self.analysis else None,
            "design": {
                "decisions": [
                    {"decision": d.decision, "rationale": d.rationale}
                    for d in (self.design.decisions if self.design else [])
                ],
                "conventions": {
                    "naming": self.design.conventions.naming if self.design and self.design.conventions else "",
                    "error_handling": self.design.conventions.error_handling if self.design and self.design.conventions else "",
                    "logging": self.design.conventions.logging if self.design and self.design.conventions else "",
                    "other": self.design.conventions.other if self.design and self.design.conventions else [],
                } if self.design and self.design.conventions else None,
            } if self.design else None,
            "contracts": {
                name: contract.to_dict() 
                for name, contract in self.contracts.items()
            },
            "execution": [
                {
                    "phase": p.phase,
                    "description": p.description,
                    "tasks": p.tasks,
                    "parallel": p.parallel,
                    "wait_for_completion": p.wait_for_completion,
                }
                for p in self.execution
            ],
            "tasks": {
                task_id: task.to_dict()
                for task_id, task in self.tasks.items()
            },
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "Plan":
        """Create a Plan from a dictionary."""
        plan = cls(
            id=data.get("id", f"plan-{uuid.uuid4().hex[:12]}"),
            created_at=data.get("created_at", time.time()),
            change_request=data.get("change_request", ""),
            version=data.get("version", "1.0"),
        )
        
        # Parse analysis
        if data.get("analysis"):
            a = data["analysis"]
            plan.analysis = PlanAnalysis(
                summary=a.get("summary", ""),
                reasoning=a.get("reasoning", ""),
                existing_patterns=[
                    ExistingPattern(**p) for p in a.get("existing_patterns", [])
                ],
                risks=a.get("risks", []),
                assumptions=a.get("assumptions", []),
            )
        
        # Parse design
        if data.get("design"):
            d = data["design"]
            plan.design = PlanDesign(
                decisions=[
                    DesignDecision(**dec) for dec in d.get("decisions", [])
                ],
                conventions=Conventions(**d["conventions"]) if d.get("conventions") else None,
            )
        
        # Parse contracts
        for name, c in data.get("contracts", {}).items():
            # Parse contract type with fallback to UNKNOWN
            contract_type_str = c.get("type", "function")
            try:
                contract_type = ContractType(contract_type_str)
            except ValueError:
                contract_type = ContractType.UNKNOWN
            
            plan.contracts[name] = Contract(
                name=c.get("name", name),
                type=contract_type,
                defined_in=c.get("defined_in", ""),
                is_new=c.get("is_new", True),
                signature=c.get("signature", ""),
                implementation=c.get("implementation"),
                usage_example=c.get("usage_example", ""),
                used_by=c.get("used_by", []),
                notes=c.get("notes"),
            )
        
        # Parse execution phases
        for p in data.get("execution", []):
            plan.execution.append(ExecutionPhase(
                phase=p.get("phase", 0),
                description=p.get("description", ""),
                tasks=p.get("tasks", []),
                parallel=p.get("parallel", True),
                wait_for_completion=p.get("wait_for_completion", True),
            ))
        
        # Parse tasks
        for task_id, t in data.get("tasks", {}).items():
            changes = []
            for c in t.get("changes", []):
                loc = c.get("location", {})
                # Parse location type with fallback to UNKNOWN for unrecognized types
                loc_type_str = loc.get("type", "function")
                try:
                    loc_type = LocationType(loc_type_str)
                except ValueError:
                    loc_type = LocationType.UNKNOWN
                
                # Parse change type with fallback
                change_type_str = c.get("change_type", "modify")
                try:
                    change_type = ChangeType(change_type_str)
                except ValueError:
                    change_type = ChangeType.UNKNOWN
                
                changes.append(TaskChange(
                    location=ChangeLocation(
                        type=loc_type,
                        target=loc.get("target", ""),
                    ),
                    change_type=change_type,
                    description=c.get("description", ""),
                    before=c.get("before"),
                    after=c.get("after", ""),
                ))
            
            ctx = t.get("context")
            val = t.get("validation")
            
            # Parse task action with fallback
            action_str = t.get("action", "modify")
            try:
                task_action = TaskAction(action_str)
            except ValueError:
                task_action = TaskAction.MODIFY
            
            plan.tasks[task_id] = Task(
                id=t.get("id", task_id),
                phase=t.get("phase", 0),
                file=t.get("file", ""),
                service=t.get("service", ""),
                language=t.get("language", "javascript"),
                action=task_action,
                description=t.get("description", ""),
                changes=changes,
                depends_on=t.get("depends_on", []),
                uses_contracts=t.get("uses_contracts", []),
                defines_contracts=t.get("defines_contracts", []),
                context=TaskContext(
                    read_files=ctx.get("read_files", []) if ctx else [],
                    relevant_symbols=ctx.get("relevant_symbols", []) if ctx else [],
                    notes=ctx.get("notes") if ctx else None,
                ) if ctx else None,
                validation=TaskValidation(
                    must_compile=val.get("must_compile", True) if val else True,
                    must_pass_lint=val.get("must_pass_lint", True) if val else True,
                    test_files=val.get("test_files", []) if val else [],
                ) if val else None,
            )
        
        return plan


# =============================================================================
# TASK FILE (Input for Implementation Agent)
# =============================================================================

@dataclass
class TaskFile:
    """
    Input for a single implementation agent.
    
    Derived from plan.json by the Coordinator.
    Contains everything the agent needs to produce a diff.
    """
    task_id: str
    file: str
    language: str
    action: TaskAction
    
    # Current file content (for modify/delete)
    current_content: Optional[str] = None
    
    # What to change
    changes: list[TaskChange] = field(default_factory=list)
    
    # ALL interface contracts (same for all agents)
    contracts: dict[str, dict] = field(default_factory=dict)
    
    # Contracts this task uses
    uses_contracts: list[str] = field(default_factory=list)
    
    # Contracts this task defines
    defines_contracts: list[str] = field(default_factory=list)
    
    # Read-only context files
    context_files: dict[str, str] = field(default_factory=dict)
    
    # Design decisions to follow
    design_decisions: list[str] = field(default_factory=list)
    
    # Coding conventions
    conventions: Optional[dict] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "task_id": self.task_id,
            "file": self.file,
            "language": self.language,
            "action": self.action.value if isinstance(self.action, TaskAction) else self.action,
            "current_content": self.current_content,
            "changes": [c.to_dict() for c in self.changes],
            "contracts": self.contracts,
            "uses_contracts": self.uses_contracts,
            "defines_contracts": self.defines_contracts,
            "context_files": self.context_files,
            "design_decisions": self.design_decisions,
            "conventions": self.conventions,
        }


# =============================================================================
# AGENT OUTPUT
# =============================================================================

@dataclass
class AgentOutput:
    """Output from an implementation agent."""
    task_id: str
    file: str
    diff: str
    status: str  # "success" or "error"
    error_message: Optional[str] = None
    usage: Optional[dict] = None  # Token usage
    metadata: Optional[dict] = None  # Extra metadata (model, complexity, etc.)
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "task_id": self.task_id,
            "file": self.file,
            "diff": self.diff,
            "status": self.status,
            "error_message": self.error_message,
            "usage": self.usage,
            "metadata": self.metadata,
        }


# =============================================================================
# VERIFICATION
# =============================================================================

@dataclass
class VerificationIssue:
    """An issue found during verification."""
    file: str
    severity: str  # "error" or "warning"
    issue: str
    suggestion: Optional[str] = None
    line: Optional[int] = None
    # Task compliance fields
    task_id: Optional[str] = None
    category: Optional[str] = None  # wrong_file, missing_change, contract_mismatch, etc.
    expected: Optional[str] = None  # What was expected
    actual: Optional[str] = None    # What was found
    fix_instruction: Optional[str] = None  # Actionable fix instruction


@dataclass
class VerificationResult:
    """Result of verification."""
    passed: bool
    tool_results: dict = field(default_factory=dict)  # lint, test results
    llm_results: Optional[dict] = None  # Contract compliance check
    issues: list[VerificationIssue] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "passed": self.passed,
            "tool_results": self.tool_results,
            "llm_results": self.llm_results,
            "issues": [
                {
                    "file": i.file,
                    "severity": i.severity,
                    "issue": i.issue,
                    "suggestion": i.suggestion,
                    "line": i.line,
                    "task_id": i.task_id,
                    "category": i.category,
                    "expected": i.expected,
                    "actual": i.actual,
                    "fix_instruction": i.fix_instruction,
                }
                for i in self.issues
            ],
        }


# =============================================================================
# CODE GENERATION RESULT
# =============================================================================

@dataclass
class CodeGenResult:
    """Final result of code generation."""
    success: bool
    plan: Optional[Plan] = None
    diffs: list[AgentOutput] = field(default_factory=list)
    verification: Optional[VerificationResult] = None
    error: Optional[str] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "plan": self.plan.to_dict() if self.plan else None,
            "diffs": [d.to_dict() for d in self.diffs],
            "verification": self.verification.to_dict() if self.verification else None,
            "error": self.error,
        }


# =============================================================================
# CODE GENERATION STATE (for pipeline tracking)
# =============================================================================

@dataclass
class CodeGenState:
    """State of the code generation pipeline."""
    id: str
    stage: CodeGenStage
    created_at: float
    updated_at: float
    
    # Input
    impact_report: Optional[dict] = None
    
    # From Design Agent
    plan: Optional[Plan] = None
    
    # From Implementation Agents
    diffs: list[AgentOutput] = field(default_factory=list)
    
    # From Verification
    verification: Optional[VerificationResult] = None
    
    # Retry tracking
    iteration: int = 1
    max_iterations: int = 3
    failed_tasks: list[str] = field(default_factory=list)
    
    # Activity log
    activity_log: list[dict] = field(default_factory=list)
    
    # Error
    error: Optional[str] = None
    
    @classmethod
    def create(cls, impact_report: dict) -> "CodeGenState":
        """Create a new state."""
        now = time.time()
        return cls(
            id=str(uuid.uuid4()),
            stage=CodeGenStage.PENDING,
            created_at=now,
            updated_at=now,
            impact_report=impact_report,
        )
    
    def log(self, message: str, level: str = "info"):
        """Add to activity log."""
        self.activity_log.append({
            "time": time.time(),
            "message": message,
            "level": level,
        })
        self.updated_at = time.time()
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "stage": self.stage.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "impact_report": self.impact_report,
            "plan": self.plan.to_dict() if self.plan else None,
            "diffs": [d.to_dict() for d in self.diffs],
            "verification": self.verification.to_dict() if self.verification else None,
            "iteration": self.iteration,
            "max_iterations": self.max_iterations,
            "failed_tasks": self.failed_tasks,
            "activity_log": self.activity_log,
            "error": self.error,
        }
