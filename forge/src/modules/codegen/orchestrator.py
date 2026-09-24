"""
Code Generation Orchestrator.

The main entry point that orchestrates the entire code generation pipeline:

1. Design Agent creates plan.json
2. Coordinator validates and distributes tasks
3. Implementation Agents run in parallel (within phases)
4. Verification checks the results
5. Retry loop for failures
6. User approval

Usage:
    orchestrator = CodeGenOrchestrator(graph_store, services_path)
    state = await orchestrator.start(impact_report)
    # ... poll state until complete ...
    state = await orchestrator.approve(state.id)
"""

import asyncio
import time
import uuid
from typing import Optional

from .schemas import (
    Plan,
    TaskFile,
    AgentOutput,
    VerificationResult,
    VerificationIssue,
    CodeGenResult,
    CodeGenStage,
    CodeGenState,
)
from .design_agent import DesignAgent
from .implementation_agent import ImplementationAgent
from .coordinator_agent import CoordinatorAgent
from .verifier_agent import VerifierAgent
from .logging_config import (
    orchestrator_logger as logger,
    log_stage_change,
    log_task_start,
    log_task_complete,
    log_diff_preview,
)

# Demo cache — lazy import
try:
    from modules.cache.demo_cache import get_cache as _get_cache
    _CACHE_AVAILABLE = True
except ImportError:
    _CACHE_AVAILABLE = False


# Maximum concurrent implementation agents
MAX_CONCURRENT_AGENTS = 5


class CodeGenOrchestrator:
    """
    Main orchestrator for code generation.
    
    Manages the full pipeline:
    - Design Agent → plan.json
    - Coordinator → task files
    - Implementation Agents → diffs
    - Verification → pass/fail
    - Retry loop → fixes
    - User approval
    
    Usage:
        orchestrator = CodeGenOrchestrator(graph_store, services_path)
        
        # Start generation from approved impact report
        state = await orchestrator.start(impact_report)
        
        # Poll for completion
        while state.stage not in [CodeGenStage.AWAITING_APPROVAL, CodeGenStage.FAILED]:
            await asyncio.sleep(1)
            state = orchestrator.get_state(state.id)
        
        # Approve
        state = await orchestrator.approve(state.id)
    """
    
    def __init__(self, graph_store, services_path: str):
        """
        Args:
            graph_store: KuzuGraphStore instance
            services_path: Path to the services directory
        """
        self._graph_store = graph_store
        self._services_path = services_path
        
        # Initialize components
        self._design_agent = DesignAgent(graph_store, services_path)
        self._coordinator = CoordinatorAgent(services_path)
        self._verifier = VerifierAgent(services_path)
        
        # State storage
        self._states: dict[str, CodeGenState] = {}
    
    async def start(self, impact_report: dict) -> CodeGenState:
        """
        Start code generation from an approved impact report.
        
        Args:
            impact_report: The approved impact report containing:
                - change_request: Original user request
                - report: The layered impact report text
                - requirements: Original requirements
                
        Returns:
            CodeGenState tracking the pipeline
        """
        # Create state
        state = CodeGenState.create(impact_report)
        self._states[state.id] = state
        
        state.log(f"Starting code generation: {impact_report.get('change_request', '')[:100]}")
        
        # Run the pipeline
        try:
            state = await self._run_pipeline(state)
        except Exception as e:
            state.stage = CodeGenStage.FAILED
            state.error = str(e)
            state.log(f"Pipeline failed: {e}", "error")
        
        return state
    
    async def _run_pipeline(self, state: CodeGenState) -> CodeGenState:
        """Run the full code generation pipeline."""
        
        # === PHASE 1: DESIGN ===
        log_stage_change(logger, "PENDING", "DESIGNING")
        state.stage = CodeGenStage.DESIGNING
        state.log("Starting Design Agent...")
        logger.info("🎨 Design Agent starting plan creation...")
        
        try:
            self._design_agent._pipeline_id = state.id  # token tracking
            plan = await self._design_agent.create_plan(state.impact_report)
            state.plan = plan
            state.log(f"Plan created: {len(plan.tasks)} tasks, {len(plan.contracts)} contracts", "success")
            logger.info(f"✅ Design Agent completed: {len(plan.tasks)} tasks, {len(plan.contracts)} contracts")
            for task_id, task in plan.tasks.items():
                logger.debug(f"   └─ Task {task_id}: {task.action} {task.file}")
        except Exception as e:
            state.stage = CodeGenStage.FAILED
            state.error = f"Design failed: {e}"
            state.log(f"Design Agent failed: {e}", "error")
            logger.error(f"❌ Design Agent failed: {e}", exc_info=True)
            return state
        
        # === PHASE 2: VALIDATE & DISTRIBUTE ===
        log_stage_change(logger, "DESIGNING", "DISTRIBUTING")
        state.stage = CodeGenStage.DISTRIBUTING
        state.log("Validating plan...")
        logger.info("📋 Validating plan...")
        
        # Use Coordinator Agent for intelligent validation
        self._coordinator._pipeline_id = state.id  # for token tracking
        validation_result = await self._coordinator.validate(plan)
        
        if not validation_result.get("valid", False):
            errors = validation_result.get("errors", [])
            error_msgs = [e.get("issue", str(e)) for e in errors]
            state.stage = CodeGenStage.FAILED
            state.error = f"Plan validation failed: {error_msgs}"
            state.log(f"Validation errors: {error_msgs}", "error")
            logger.error(f"❌ Plan validation failed: {error_msgs}")
            return state
        
        # Log warnings if any
        warnings = validation_result.get("warnings", [])
        if warnings:
            for w in warnings:
                state.log(f"Warning: {w.get('issue', str(w))}", "warning")
                logger.warning(f"⚠️ {w.get('issue', str(w))}")
        
        state.log("Plan validated successfully", "success")
        logger.info("✅ Plan validated successfully")
        
        # Create task files
        task_files = self._coordinator.create_task_files(plan)
        state.log(f"Created {len(task_files)} task files")
        logger.info(f"📁 Created {len(task_files)} task files")
        for task_id, tf in task_files.items():
            logger.debug(f"   └─ {task_id}: {tf.file} ({tf.action})")
        
        # Get execution order
        phases = self._coordinator.get_execution_order(plan)
        state.log(f"Execution order: {len(phases)} phases")
        logger.info(f"📊 Execution order: {len(phases)} phases")
        
        # === PHASE 3: IMPLEMENT ===
        log_stage_change(logger, "DISTRIBUTING", "IMPLEMENTING")
        state.stage = CodeGenStage.IMPLEMENTING
        state.log("Starting implementation...")
        logger.info("🔨 Starting implementation...")
        
        all_diffs = []
        
        for phase in phases:
            state.log(f"Phase {phase.phase}: {phase.description}")
            logger.info(f"📌 Phase {phase.phase}: {phase.description} ({len(phase.tasks)} tasks)")
            
            # Get tasks for this phase
            phase_task_files = [task_files[task_id] for task_id in phase.tasks]
            
            # Run tasks
            if phase.parallel and len(phase_task_files) > 1:
                logger.info(f"   └─ Running {len(phase_task_files)} tasks in parallel")
                diffs = await self._run_parallel(phase_task_files)
            else:
                logger.info(f"   └─ Running {len(phase_task_files)} tasks sequentially")
                diffs = await self._run_sequential(phase_task_files)
            
            all_diffs.extend(diffs)
            
            # Log results
            success_count = sum(1 for d in diffs if d.status == "success")
            state.log(f"Phase {phase.phase}: {success_count}/{len(diffs)} tasks succeeded")
            logger.info(f"   └─ Phase {phase.phase} complete: {success_count}/{len(diffs)} succeeded")
            
            # Log individual diffs
            for diff in diffs:
                if diff.status == "success":
                    log_diff_preview(logger, diff.task_id, diff.diff)
                else:
                    logger.error(f"   └─ Task {diff.task_id} failed: {diff.error_message}")
            
            # Check for failures
            failures = [d for d in diffs if d.status != "success"]
            if failures and phase.wait_for_completion:
                state.failed_tasks.extend([d.task_id for d in failures])
                state.log(f"Phase {phase.phase} had failures", "warning")
                logger.warning(f"⚠️ Phase {phase.phase} had {len(failures)} failures")
        
        state.diffs = all_diffs
        
        # === PHASE 4: VERIFY ===
        log_stage_change(logger, "IMPLEMENTING", "VERIFYING")
        state.stage = CodeGenStage.VERIFYING
        state.log("Starting verification...")
        logger.info("🔍 Starting verification...")
        
        successful_diffs = [d for d in all_diffs if d.status == "success"]
        
        try:
            # Use Verifier Agent for intelligent verification
            self._verifier._pipeline_id = state.id  # token tracking
            verification = await self._verifier.verify(
                plan=plan,
                diffs=successful_diffs,
            )
            state.verification = verification
            
            if verification.passed:
                state.log("Verification passed!", "success")
                logger.info("✅ Verification passed!")
            else:
                error_count = sum(1 for i in verification.issues if i.severity == "error")
                state.log(f"Verification found {error_count} errors", "warning")
                logger.warning(f"⚠️ Verification found {error_count} errors")
                for issue in verification.issues:
                    logger.warning(f"   └─ [{issue.severity}] {issue.file}: {issue.issue}")
        except Exception as e:
            state.log(f"Verification error: {e}", "warning")
            logger.error(f"❌ Verification error: {e}", exc_info=True)
            # Non-fatal but mark as NOT passed so human sees it at approval
            state.verification = VerificationResult(
                passed=False,
                issues=[VerificationIssue(
                    file="harness",
                    severity="warning",
                    issue=f"Verification harness crashed: {e}",
                    category="harness_error",
                    suggestion="Review server logs for the full traceback",
                    fix_instruction="",
                )]
            )
        
        # === PHASE 5: RETRY (if needed) ===
        if not state.verification.passed and state.iteration < state.max_iterations:
            # Check if all errors are identical to previous iteration (stale — won't improve)
            current_error_set = frozenset(
                i.issue for i in state.verification.issues if i.severity == "error"
            )
            prev_error_set = getattr(state, '_prev_error_set', None)
            
            if prev_error_set is not None and current_error_set == prev_error_set:
                logger.warning(
                    f"⏭ Errors identical to previous iteration — skipping retry "
                    f"(same {len(current_error_set)} errors, retrying won't help)"
                )
                state.log(
                    f"Errors unchanged after retry — skipping further retries", "warning"
                )
            else:
                state._prev_error_set = current_error_set
                state = await self._retry_failed(state, task_files)
        
        # === PHASE 6: READY FOR APPROVAL ===
        state.stage = CodeGenStage.AWAITING_APPROVAL
        state.log("Code generation complete - awaiting approval", "success")
        
        return state
    
    async def _run_parallel(self, task_files: list[TaskFile]) -> list[AgentOutput]:
        """Run implementation agents in parallel with concurrency limit."""
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_AGENTS)
        
        async def run_with_limit(task_file: TaskFile) -> AgentOutput:
            async with semaphore:
                agent = ImplementationAgent(self._services_path)
                return await agent.implement(task_file)
        
        return await asyncio.gather(*[
            run_with_limit(tf) for tf in task_files
        ])
    
    async def _run_sequential(self, task_files: list[TaskFile]) -> list[AgentOutput]:
        """Run implementation agents sequentially."""
        results = []
        for task_file in task_files:
            agent = ImplementationAgent(self._services_path)
            result = await agent.implement(task_file)
            results.append(result)
        return results
    
    async def _retry_failed(
        self, 
        state: CodeGenState, 
        task_files: dict[str, TaskFile]
    ) -> CodeGenState:
        """Retry failed tasks based on verification errors."""
        state.stage = CodeGenStage.FIXING
        state.iteration += 1
        state.log(f"Retry iteration {state.iteration}: fixing issues...")
        logger.info(f"🔄 Starting retry iteration {state.iteration}/{state.max_iterations}")
        
        # Group errors by task_id (preferred) or file
        errors_by_task = {}
        for issue in state.verification.issues:
            if issue.severity == "error":
                # Prefer task_id if available
                key = issue.task_id or issue.file
                if key not in errors_by_task:
                    errors_by_task[key] = []
                
                # Build structured feedback
                feedback = {
                    "issue": issue.issue,
                    "category": issue.category,
                    "suggestion": issue.suggestion,
                    "fix_instruction": issue.fix_instruction,
                    "expected": issue.expected,
                    "actual": issue.actual,
                    "line": issue.line,
                }
                errors_by_task[key].append(feedback)
        
        logger.info(f"   └─ Tasks with errors: {len(errors_by_task)}")
        for task_key, errors in errors_by_task.items():
            logger.debug(f"      └─ {task_key}: {len(errors)} errors")
        
        # Retry failed tasks
        new_diffs = []
        for task_id, task_file in task_files.items():
            # Check if this task has errors (by task_id or file)
            task_errors = errors_by_task.get(task_id) or errors_by_task.get(task_file.file)
            
            if task_errors:
                # Find the original diff
                original_diff = next(
                    (d for d in state.diffs if d.task_id == task_id),
                    None
                )
                
                if original_diff and original_diff.diff:
                    state.log(f"Fixing {task_file.file} ({len(task_errors)} errors)...")
                    
                    agent = ImplementationAgent(self._services_path)
                    fixed = await agent.fix_diff(
                        task_file,
                        original_diff.diff,
                        task_errors  # Pass structured feedback
                    )
                    new_diffs.append(fixed)
                else:
                    # Re-run from scratch
                    agent = ImplementationAgent(self._services_path)
                    new_diffs.append(await agent.implement(task_file))
            else:
                # Keep original
                original = next(
                    (d for d in state.diffs if d.task_id == task_id),
                    None
                )
                if original:
                    new_diffs.append(original)
        
        state.diffs = new_diffs
        
        # Re-verify
        state.stage = CodeGenStage.VERIFYING
        state.log("Re-verifying...")
        
        successful_diffs = [d for d in new_diffs if d.status == "success"]
        
        try:
            self._verifier._pipeline_id = state.id  # token tracking
            verification = await self._verifier.verify(
                plan=state.plan,
                diffs=successful_diffs,
            )
            state.verification = verification
            
            if verification.passed:
                state.log("Verification passed after fixes!", "success")
                logger.info("✅ Verification passed after retry")
            else:
                error_count = sum(1 for i in verification.issues if i.severity == "error")
                state.log(f"Still {error_count} errors after retry", "warning")
                logger.warning(f"⚠️ Still {error_count} errors after retry {state.iteration}")
                
                # Check for stale errors before recursing
                current_error_set = frozenset(
                    i.issue for i in verification.issues if i.severity == "error"
                )
                prev_error_set = getattr(state, '_prev_error_set', None)
                
                if prev_error_set is not None and current_error_set == prev_error_set:
                    logger.warning(
                        f"⏭ Errors identical to previous retry — stopping "
                        f"(same {len(current_error_set)} errors, further retries won't help)"
                    )
                    state.log("Errors unchanged — stopping retry loop", "warning")
                elif state.iteration < state.max_iterations:
                    # Still have budget and new errors — continue
                    state._prev_error_set = current_error_set
                    return await self._retry_failed(state, task_files)
                else:
                    logger.info(f"[RETRY] Max iterations ({state.max_iterations}) reached")
                    
        except Exception as e:
            state.log(f"Verification error during retry: {e}", "warning")
        
        return state
    
    async def approve(self, state_id: str) -> CodeGenState:
        """
        Approve the generated code changes.
        
        Args:
            state_id: The state ID
            
        Returns:
            Updated state
        """
        state = self._states.get(state_id)
        if not state:
            raise ValueError(f"State {state_id} not found")
        
        if state.stage != CodeGenStage.AWAITING_APPROVAL:
            raise ValueError(f"Cannot approve in stage {state.stage}")
        
        state.stage = CodeGenStage.APPROVED
        state.log("Changes approved by user", "success")
        state.updated_at = time.time()
        
        # ── DEMO CACHE: save after human approves ────────────────────────────
        if _CACHE_AVAILABLE and state.diffs:
            try:
                impact = state.impact_report or {}
                change_req = impact.get("change_request", "Code generation")[:60]
                services = impact.get("requirements", {}).get("services", []) if isinstance(impact.get("requirements"), dict) else []
                label = f"{change_req} [{', '.join(services[:2])}]" if services else change_req
                cache_input = {
                    "change_request": impact.get("change_request", ""),
                    "services": services,
                }
                # Grab token usage — codegen uses the pipeline_id from the impact report
                token_usage = {}
                try:
                    from modules.cache.token_tracker import get_tracker
                    _tracker = get_tracker()
                    # Try both the codegen state ID and the originating pipeline ID
                    token_usage = _tracker.snapshot(state.id)
                    pipeline_id_src = impact.get("pipeline_id", "")
                    if not token_usage and pipeline_id_src:
                        token_usage = _tracker.snapshot(pipeline_id_src)
                    _tracker.clear(state.id)
                    if pipeline_id_src:
                        _tracker.clear(pipeline_id_src)
                except Exception:
                    pass
                _get_cache().save(
                    cache_id=state.id,
                    pipeline_type="codegen",
                    label=label,
                    input_data=cache_input,
                    output_data={
                        "diffs": [d.__dict__ if hasattr(d, '__dict__') else d for d in state.diffs],
                        "plan":  state.plan.to_dict() if state.plan else {},
                    },
                    token_usage=token_usage,
                )
                logger.info(f"[CACHE] CodeGen saved: id={state.id!r} label={label!r}")
            except Exception as _ce:
                logger.warning(f"[CACHE] Save failed (non-fatal): {_ce}")
        
        return state
    
    async def reject(self, state_id: str, reason: str = "") -> CodeGenState:
        """
        Reject the generated code changes.
        
        Args:
            state_id: The state ID
            reason: Rejection reason
            
        Returns:
            Updated state
        """
        state = self._states.get(state_id)
        if not state:
            raise ValueError(f"State {state_id} not found")
        
        if state.stage != CodeGenStage.AWAITING_APPROVAL:
            raise ValueError(f"Cannot reject in stage {state.stage}")
        
        state.stage = CodeGenStage.REJECTED
        state.error = reason or "Rejected by user"
        state.log(f"Changes rejected: {reason}", "warning")
        state.updated_at = time.time()
        
        return state
    
    async def refine_plan(self, state_id: str, feedback: str) -> CodeGenState:
        """
        Refine the plan based on user feedback and re-run implementation.
        
        Args:
            state_id: The state ID
            feedback: User's feedback on the plan
            
        Returns:
            Updated state
        """
        state = self._states.get(state_id)
        if not state:
            raise ValueError(f"State {state_id} not found")
        
        if state.stage != CodeGenStage.AWAITING_APPROVAL:
            raise ValueError(f"Cannot refine in stage {state.stage}")
        
        if not state.plan:
            raise ValueError("No plan to refine")
        
        state.log(f"Refining plan based on feedback: {feedback[:100]}...")
        state.stage = CodeGenStage.DESIGNING
        
        # Refine the plan
        try:
            state.plan = await self._design_agent.refine_plan(state.plan, feedback)
            state.log("Plan refined", "success")
        except Exception as e:
            state.log(f"Failed to refine plan: {e}", "error")
            state.stage = CodeGenStage.AWAITING_APPROVAL
            return state
        
        # Re-run implementation with new plan
        state.diffs = []
        state.iteration = 1
        state.failed_tasks = []
        
        state = await self._run_pipeline(state)
        
        return state
    
    def get_state(self, state_id: str) -> Optional[CodeGenState]:
        """Get a state by ID."""
        return self._states.get(state_id)
    
    def get_state_by_pipeline(self, pipeline_id: str) -> Optional[CodeGenState]:
        """Get a state by pipeline ID."""
        for state in self._states.values():
            if state.impact_report and state.impact_report.get("pipeline_id") == pipeline_id:
                return state
        return None
    
    def get_result(self, state_id: str) -> Optional[CodeGenResult]:
        """
        Get the final result.
        
        Args:
            state_id: The state ID
            
        Returns:
            CodeGenResult or None if not complete
        """
        state = self._states.get(state_id)
        if not state:
            return None
        
        if state.stage not in [CodeGenStage.APPROVED, CodeGenStage.REJECTED, CodeGenStage.FAILED]:
            return None
        
        return CodeGenResult(
            success=state.stage == CodeGenStage.APPROVED,
            plan=state.plan,
            diffs=state.diffs,
            verification=state.verification,
            error=state.error,
        )
    
    def delete_state(self, state_id: str):
        """Delete a state."""
        self._states.pop(state_id, None)
