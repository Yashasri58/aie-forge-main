"""
Coordinator.

Simple code (not LLM) that:
1. Validates plan.json
2. Creates task files for each implementation agent
3. Manages execution phases
"""

from pathlib import Path
from typing import Optional
import logging
_log = logging.getLogger("forge.codegen.coordinator")

from .schemas import (
    Plan,
    Task,
    TaskFile,
    TaskAction,
    Contract,
    ExecutionPhase,
)


class ValidationError(Exception):
    """Plan validation error."""
    pass


class Coordinator:
    """
    Coordinator - manages plan execution.
    
    Responsibilities:
    - Validate plan.json
    - Create task files
    - Detect circular dependencies
    - Manage execution phases
    
    Usage:
        coordinator = Coordinator(services_path)
        coordinator.validate(plan)
        task_files = coordinator.create_task_files(plan)
        phases = coordinator.get_execution_order(plan)
    """
    
    def __init__(self, services_path: str):
        _log.info(f"[COORD] __init__: services_path={services_path}")
        self._services_path = Path(services_path)
        _log.info(f"[COORD] _services_path set to {self._services_path}")
    
    def validate(self, plan: Plan) -> list[str]:
        """Validate a plan. Returns list of validation errors (empty if valid)."""
        _log.info(f"[COORD] validate(): tasks={len(plan.tasks)} contracts={len(plan.contracts)} phases={len(plan.execution)}")
        errors = []
        
        # Check required fields
        if not plan.change_request:
            _log.warning(f"[COORD] validate: missing change_request")
            errors.append("Missing change_request")
        
        if not plan.tasks:
            errors.append("No tasks defined")
        
        # Check for duplicate file assignments
        files_assigned = {}
        for task_id, task in plan.tasks.items():
            if task.file in files_assigned:
                errors.append(
                    f"File '{task.file}' assigned to multiple tasks: "
                    f"'{files_assigned[task.file]}' and '{task_id}'"
                )
            files_assigned[task.file] = task_id
        
        # Check task IDs match
        for task_id, task in plan.tasks.items():
            if task.id != task_id:
                errors.append(f"Task ID mismatch: key='{task_id}', task.id='{task.id}'")
        
        # Check dependencies exist
        all_task_ids = set(plan.tasks.keys())
        for task_id, task in plan.tasks.items():
            for dep in task.depends_on:
                if dep not in all_task_ids:
                    errors.append(f"Task '{task_id}' depends on non-existent task '{dep}'")
        
        # Check for circular dependencies
        circular = self._find_circular_dependencies(plan)
        if circular:
            errors.append(f"Circular dependency detected: {' -> '.join(circular)}")
        
        # Check contracts used exist
        all_contracts = set(plan.contracts.keys())
        for task_id, task in plan.tasks.items():
            for contract_name in task.uses_contracts:
                if contract_name not in all_contracts:
                    errors.append(
                        f"Task '{task_id}' uses non-existent contract '{contract_name}'"
                    )
        
        # Check execution phases
        tasks_in_phases = set()
        for phase in plan.execution:
            for task_id in phase.tasks:
                if task_id not in all_task_ids:
                    errors.append(
                        f"Phase {phase.phase} references non-existent task '{task_id}'"
                    )
                if task_id in tasks_in_phases:
                    errors.append(f"Task '{task_id}' appears in multiple phases")
                tasks_in_phases.add(task_id)
        
        # Check all tasks are in a phase
        for task_id in all_task_ids:
            if task_id not in tasks_in_phases:
                errors.append(f"Task '{task_id}' is not assigned to any phase")
        
        # Check file existence for modify/delete actions
        for task_id, task in plan.tasks.items():
            file_path = self._services_path / task.file
            if task.action == TaskAction.MODIFY:
                if not file_path.exists():
                    errors.append(
                        f"Task '{task_id}' targets non-existent file for MODIFY: '{task.file}'. "
                        f"Use action='create' for new files."
                    )
            elif task.action == TaskAction.DELETE:
                if not file_path.exists():
                    errors.append(
                        f"Task '{task_id}' targets non-existent file for DELETE: '{task.file}'"
                    )
            elif task.action == TaskAction.CREATE:
                if file_path.exists():
                    # Warning, not error - file already exists but we're creating
                    # This might be intentional (overwrite), so just log it
                    pass
        
        return errors
    
    def _find_circular_dependencies(self, plan: Plan) -> Optional[list[str]]:
        """
        Find circular dependencies in tasks.
        
        Returns:
            List of task IDs forming a cycle, or None if no cycle
        """
        # Build adjacency list
        graph = {task_id: task.depends_on for task_id, task in plan.tasks.items()}
        
        # DFS to find cycle
        visited = set()
        rec_stack = set()
        path = []
        
        def dfs(node: str) -> Optional[list[str]]:
            visited.add(node)
            rec_stack.add(node)
            path.append(node)
            
            for neighbor in graph.get(node, []):
                if neighbor not in visited:
                    result = dfs(neighbor)
                    if result:
                        return result
                elif neighbor in rec_stack:
                    # Found cycle
                    cycle_start = path.index(neighbor)
                    return path[cycle_start:] + [neighbor]
            
            path.pop()
            rec_stack.remove(node)
            return None
        
        for task_id in graph:
            if task_id not in visited:
                result = dfs(task_id)
                if result:
                    return result
        
        return None
    
    def create_task_files(self, plan: Plan) -> dict[str, TaskFile]:
        """Create task files for all tasks in the plan."""
        _log.info(f"[COORD] create_task_files(): tasks={len(plan.tasks)}")
        # Convert contracts to dicts for task files
        contracts_dict = {
            name: contract.to_dict()
            for name, contract in plan.contracts.items()
        }
        _log.info(f"[COORD] contracts_dict keys={list(contracts_dict.keys())}")
        
        # Get design decisions as list of strings
        design_decisions = []
        if plan.design and plan.design.decisions:
            design_decisions = [d.decision for d in plan.design.decisions]
        
        # Get conventions as dict
        conventions = None
        if plan.design and plan.design.conventions:
            conventions = {
                "naming": plan.design.conventions.naming,
                "error_handling": plan.design.conventions.error_handling,
                "logging": plan.design.conventions.logging,
            }
        
        task_files = {}
        
        for task_id, task in plan.tasks.items():
            # Read current file content if modifying
            current_content = None
            if task.action != TaskAction.CREATE:
                file_path = self._services_path / task.file
                if file_path.exists():
                    try:
                        current_content = file_path.read_text(encoding="utf-8")
                    except Exception:
                        pass
            
            # Read context files
            context_files = {}
            if task.context and task.context.read_files:
                for ctx_file in task.context.read_files:
                    ctx_path = self._services_path / ctx_file
                    if ctx_path.exists():
                        try:
                            context_files[ctx_file] = ctx_path.read_text(encoding="utf-8")
                        except Exception:
                            pass
            
            # Create task file
            _log.info(f"[COORD] creating TaskFile: task_id={task_id} file={task.file} action={task.action} current_content_len={len(current_content) if current_content else 0}")
            task_file = TaskFile(
                task_id=task_id,
                file=task.file,
                language=task.language,
                action=task.action,
                current_content=current_content,
                changes=task.changes,
                contracts=contracts_dict,
                uses_contracts=task.uses_contracts,
                defines_contracts=task.defines_contracts,
                context_files=context_files,
                design_decisions=design_decisions,
                conventions=conventions,
            )
            _log.info(f"[COORD] TaskFile created: task_id={task_id}")
            
            task_files[task_id] = task_file
            _log.info(f"[COORD] task_files now has {len(task_files)} entries")
        
        _log.info(f"[COORD] create_task_files done: {len(task_files)} task files: {list(task_files.keys())}")
        return task_files
    
    def get_execution_order(self, plan: Plan) -> list[ExecutionPhase]:
        """Get the execution order from the plan."""
        _log.info(f"[COORD] get_execution_order(): plan.execution has {len(plan.execution)} phases")
        if plan.execution:
            result = sorted(plan.execution, key=lambda p: p.phase)
            _log.info(f"[COORD] using explicit phases: {[(p.phase, p.description, p.tasks) for p in result]}")
            return result
        
        _log.info(f"[COORD] no explicit phases — computing from dependencies")
        result = self._compute_phases(plan)
        _log.info(f"[COORD] computed {len(result)} phases")
        return result
    
    def _compute_phases(self, plan: Plan) -> list[ExecutionPhase]:
        """Compute execution phases from task dependencies."""
        # Build dependency graph
        in_degree = {task_id: 0 for task_id in plan.tasks}
        for task_id, task in plan.tasks.items():
            for dep in task.depends_on:
                if dep in in_degree:
                    in_degree[task_id] += 1
        
        phases = []
        remaining = set(plan.tasks.keys())
        phase_num = 0
        
        while remaining:
            # Find tasks with no remaining dependencies
            ready = [
                task_id for task_id in remaining
                if in_degree[task_id] == 0
            ]
            
            if not ready:
                # Circular dependency (should have been caught by validation)
                ready = list(remaining)[:1]
            
            # Create phase
            phase = ExecutionPhase(
                phase=phase_num,
                description=f"Phase {phase_num}",
                tasks=ready,
                parallel=len(ready) > 1,
                wait_for_completion=True,
            )
            phases.append(phase)
            
            # Update for next iteration
            for task_id in ready:
                remaining.remove(task_id)
                # Reduce in-degree of dependents
                for other_id in remaining:
                    if task_id in plan.tasks[other_id].depends_on:
                        in_degree[other_id] -= 1
            
            phase_num += 1
        
        return phases
    
    def get_files_in_phase(self, plan: Plan, phase: int) -> list[str]:
        """Get list of files modified in a phase."""
        for p in plan.execution:
            if p.phase == phase:
                return [plan.tasks[task_id].file for task_id in p.tasks]
        return []
    
    def get_tasks_for_phase(self, plan: Plan, phase: int) -> list[Task]:
        """Get tasks for a specific phase."""
        for p in plan.execution:
            if p.phase == phase:
                return [plan.tasks[task_id] for task_id in p.tasks]
        return []
