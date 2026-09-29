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
import os
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


def _sync_enabled() -> bool:
    """Return True if SYNC_GRAPH_ON_APPROVE=true in the environment."""
    return os.getenv("SYNC_GRAPH_ON_APPROVE", "false").lower() in ("true", "1", "yes")


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
        logger.info(f"[ORCH_INIT] CodeGenOrchestrator.__init__() services_path={services_path}")
        self._graph_store = graph_store
        logger.info(f"[ORCH_INIT] graph_store assigned: {type(graph_store).__name__}")
        self._services_path = services_path
        logger.info(f"[ORCH_INIT] services_path assigned")
        
        # Initialize components
        logger.info(f"[ORCH_INIT] creating DesignAgent")
        self._design_agent = DesignAgent(graph_store, services_path)
        logger.info(f"[ORCH_INIT] DesignAgent created")
        logger.info(f"[ORCH_INIT] creating CoordinatorAgent")
        self._coordinator = CoordinatorAgent(services_path)
        logger.info(f"[ORCH_INIT] CoordinatorAgent created")
        logger.info(f"[ORCH_INIT] creating VerifierAgent")
        self._verifier = VerifierAgent(services_path)
        logger.info(f"[ORCH_INIT] VerifierAgent created")
        
        # State storage
        self._states: dict[str, CodeGenState] = {}

        # Graph rebuilder — injected by main.py after startup
        self._graph_rebuilder = None
        logger.info(f"[ORCH_INIT] _states dict initialized empty")
        logger.info(f"[ORCH_INIT] ✅ CodeGenOrchestrator ready")
    
    async def start(self, impact_report: dict) -> CodeGenState:
        """
        Start code generation from an approved impact report.
        """
        logger.info(f"[START] ▶️  start() called")
        logger.info(f"[START] impact_report keys={list(impact_report.keys())}")
        logger.info(f"[START] change_request='{impact_report.get('change_request','')[:80]}'")
        logger.info(f"[START] services={impact_report.get('requirements', {}).get('services', []) if isinstance(impact_report.get('requirements'), dict) else 'n/a'}")

        # Create state
        logger.info(f"[START] calling CodeGenState.create()")
        state = CodeGenState.create(impact_report)
        logger.info(f"[START] state created: id={state.id} stage={state.stage}")
        self._states[state.id] = state
        logger.info(f"[START] state stored in _states, total states={len(self._states)}")

        state.log(f"Starting code generation: {impact_report.get('change_request', '')[:100]}")
        logger.info(f"[START] activity log entry added")

        # Run the pipeline
        logger.info(f"[START] calling _run_pipeline(state={state.id})")
        try:
            state = await self._run_pipeline(state)
            logger.info(f"[START] _run_pipeline returned: stage={state.stage} error={state.error}")
        except Exception as e:
            logger.error(f"[START] _run_pipeline RAISED UNHANDLED: {e}", exc_info=True)
            state.stage = CodeGenStage.FAILED
            logger.info(f"[START] stage → FAILED due to exception")
            state.error = str(e)
            logger.info(f"[START] state.error = '{state.error}'")
            state.log(f"Pipeline failed: {e}", "error")
            logger.info(f"[START] activity log entry added for failure")

        logger.info(f"[START] ✅ start() returning: stage={state.stage}")
        return state
    
    async def _run_pipeline(self, state: CodeGenState) -> CodeGenState:
        """Run the full code generation pipeline."""
        logger.info(f"[PIPELINE] ▶️  _run_pipeline START — state.id={state.id} stage={state.stage}")

        # === PHASE 1: DESIGN ===
        log_stage_change(logger, "PENDING", "DESIGNING")
        state.stage = CodeGenStage.DESIGNING
        logger.info(f"[PIPELINE] 📍 stage → DESIGNING (state={state.id})")
        state.log("Starting Design Agent...")
        logger.info("🎨 Design Agent starting plan creation...")
        
        try:
            logger.info(f"[PIPELINE][DESIGN] calling create_plan, impact_report keys={list((state.impact_report or {}).keys())}")
            self._design_agent._pipeline_id = state.id  # token tracking
            plan = await self._design_agent.create_plan(state.impact_report)
            logger.info(f"[PIPELINE][DESIGN] create_plan returned — tasks={len(plan.tasks)} contracts={len(plan.contracts)}")
            state.plan = plan
            state.log(f"Plan created: {len(plan.tasks)} tasks, {len(plan.contracts)} contracts", "success")
            logger.info(f"✅ Design Agent completed: {len(plan.tasks)} tasks, {len(plan.contracts)} contracts")
            for task_id, task in plan.tasks.items():
                logger.debug(f"   └─ Task {task_id}: {task.action} {task.file}")
        except Exception as e:
            logger.error(f"[PIPELINE][DESIGN] create_plan RAISED: {e}", exc_info=True)
            state.stage = CodeGenStage.FAILED
            state.error = f"Design failed: {e}"
            state.log(f"Design Agent failed: {e}", "error")
            logger.error(f"❌ Design Agent failed: {e}", exc_info=True)
            return state
        logger.info(f"[PIPELINE] ✅ DESIGN complete — moving to DISTRIBUTING")
        
        # === PHASE 2: VALIDATE & DISTRIBUTE ===
        log_stage_change(logger, "DESIGNING", "DISTRIBUTING")
        state.stage = CodeGenStage.DISTRIBUTING
        logger.info(f"[PIPELINE] 📍 stage → DISTRIBUTING (state={state.id})")
        state.log("Validating plan...")
        logger.info("📋 Validating plan...")
        
        # Use Coordinator Agent for intelligent validation
        logger.info(f"[PIPELINE][COORDINATOR] calling validate(), tasks={len(plan.tasks)}")
        self._coordinator._pipeline_id = state.id  # for token tracking
        validation_result = await self._coordinator.validate(plan)
        logger.info(f"[PIPELINE][COORDINATOR] validate() returned: valid={validation_result.get('valid')} errors={len(validation_result.get('errors',[]))} warnings={len(validation_result.get('warnings',[]))}")
        
        if not validation_result.get("valid", False):
            errors = validation_result.get("errors", [])
            error_msgs = [e.get("issue", str(e)) for e in errors]
            logger.error(f"[PIPELINE][COORDINATOR] VALIDATION FAILED: {error_msgs}")
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
        logger.info(f"[PIPELINE][COORDINATOR] calling create_task_files()")
        task_files = self._coordinator.create_task_files(plan)
        logger.info(f"[PIPELINE][COORDINATOR] create_task_files() → {len(task_files)} files: {list(task_files.keys())}")
        state.log(f"Created {len(task_files)} task files")
        logger.info(f"📁 Created {len(task_files)} task files")
        for task_id, tf in task_files.items():
            logger.debug(f"   └─ {task_id}: {tf.file} ({tf.action})")
        
        # Get execution order
        logger.info(f"[PIPELINE][COORDINATOR] calling get_execution_order()")
        phases = self._coordinator.get_execution_order(plan)
        logger.info(f"[PIPELINE][COORDINATOR] get_execution_order() → {len(phases)} phases: {[(p.phase, p.description, len(p.tasks)) for p in phases]}")
        state.log(f"Execution order: {len(phases)} phases")
        logger.info(f"📊 Execution order: {len(phases)} phases")
        
        # === PHASE 3: IMPLEMENT ===
        log_stage_change(logger, "DISTRIBUTING", "IMPLEMENTING")
        state.stage = CodeGenStage.IMPLEMENTING
        logger.info(f"[PIPELINE] 📍 stage → IMPLEMENTING (state={state.id})")
        state.log("Starting implementation...")
        logger.info("🔨 Starting implementation...")
        
        all_diffs = []
        logger.info(f"[PIPELINE][IMPL] Starting phase loop — {len(phases)} phases total")
        
        for phase in phases:
            logger.info(f"[PIPELINE][IMPL] ▶️  Phase {phase.phase} START: '{phase.description}' tasks={phase.tasks} parallel={phase.parallel}")
            state.log(f"Phase {phase.phase}: {phase.description}")
            logger.info(f"📌 Phase {phase.phase}: {phase.description} ({len(phase.tasks)} tasks)")
            
            # Get tasks for this phase
            phase_task_files = [task_files[task_id] for task_id in phase.tasks]
            logger.info(f"[PIPELINE][IMPL] Phase {phase.phase} task files: {[tf.file for tf in phase_task_files]}")
            
            # Run tasks
            if phase.parallel and len(phase_task_files) > 1:
                logger.info(f"[PIPELINE][IMPL] Phase {phase.phase} → running PARALLEL ({len(phase_task_files)} tasks)")
                logger.info(f"   └─ Running {len(phase_task_files)} tasks in parallel")
                diffs = await self._run_parallel(phase_task_files, pipeline_id=state.id)
            else:
                logger.info(f"[PIPELINE][IMPL] Phase {phase.phase} → running SEQUENTIAL ({len(phase_task_files)} tasks)")
                logger.info(f"   └─ Running {len(phase_task_files)} tasks sequentially")
                diffs = await self._run_sequential(phase_task_files, pipeline_id=state.id)
            
            logger.info(f"[PIPELINE][IMPL] Phase {phase.phase} returned {len(diffs)} diffs")
            for d in diffs:
                logger.info(f"[PIPELINE][IMPL]   diff task_id={d.task_id} file={d.file} status={d.status} diff_len={len(d.diff or '')} error={d.error_message or ''}")
            all_diffs.extend(diffs)
            logger.info(f"[PIPELINE][IMPL] all_diffs accumulated: {len(all_diffs)} total")
            
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
            logger.info(f"[PIPELINE][IMPL] Phase {phase.phase} failures={len(failures)} wait_for_completion={phase.wait_for_completion}")
            if failures and phase.wait_for_completion:
                state.failed_tasks.extend([d.task_id for d in failures])
                state.log(f"Phase {phase.phase} had failures", "warning")
                logger.warning(f"⚠️ Phase {phase.phase} had {len(failures)} failures")
            
            logger.info(f"[PIPELINE][IMPL] ✅ Phase {phase.phase} END")
        
        state.diffs = all_diffs
        logger.info(f"[PIPELINE][IMPL] All phases done — total diffs={len(all_diffs)} successful={sum(1 for d in all_diffs if d.status=='success')}")
        
        # === PHASE 4: VERIFY ===
        log_stage_change(logger, "IMPLEMENTING", "VERIFYING")
        state.stage = CodeGenStage.VERIFYING
        logger.info(f"[PIPELINE] 📍 stage → VERIFYING (state={state.id})")
        state.log("Starting verification...")
        logger.info("🔍 Starting verification...")
        
        successful_diffs = [d for d in all_diffs if d.status == "success"]
        logger.info(f"[PIPELINE][VERIFY] successful_diffs={len(successful_diffs)} of {len(all_diffs)} total")
        for d in successful_diffs:
            logger.info(f"[PIPELINE][VERIFY]   → {d.task_id} file={d.file} diff_len={len(d.diff or '')}")
        
        try:
            logger.info(f"[PIPELINE][VERIFY] calling verifier.verify() plan_tasks={len(plan.tasks)} diffs={len(successful_diffs)}")
            # Use Verifier Agent for intelligent verification
            self._verifier._pipeline_id = state.id  # token tracking
            verification = await self._verifier.verify(
                plan=plan,
                diffs=successful_diffs,
            )
            logger.info(f"[PIPELINE][VERIFY] verify() returned: passed={verification.passed} issues={len(verification.issues)}")
            for iss in verification.issues:
                logger.info(f"[PIPELINE][VERIFY]   issue severity={iss.severity} file={iss.file} issue='{iss.issue}'")
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
            logger.error(f"[PIPELINE][VERIFY] verifier.verify() RAISED: {e}", exc_info=True)
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
        logger.info(f"[PIPELINE] 📍 Checking retry: verification.passed={state.verification.passed} iteration={state.iteration} max={state.max_iterations}")
        if not state.verification.passed and state.iteration < state.max_iterations:
            logger.info(f"[PIPELINE][RETRY] verification failed and iteration budget remains — checking for stale errors")
            # Check if all errors are identical to previous iteration (stale — won't improve)
            current_error_set = frozenset(
                i.issue for i in state.verification.issues if i.severity == "error"
            )
            logger.info(f"[PIPELINE][RETRY] current_error_set size={len(current_error_set)}: {current_error_set}")
            prev_error_set = getattr(state, '_prev_error_set', None)
            logger.info(f"[PIPELINE][RETRY] prev_error_set={prev_error_set}")
            
            if prev_error_set is not None and current_error_set == prev_error_set:
                logger.warning(
                    f"⏭ Errors identical to previous iteration — skipping retry "
                    f"(same {len(current_error_set)} errors, retrying won't help)"
                )
                logger.warning(f"[PIPELINE][RETRY] STALE — skipping retry, proceeding to approval")
                state.log(
                    f"Errors unchanged after retry — skipping further retries", "warning"
                )
            else:
                logger.info(f"[PIPELINE][RETRY] errors changed or first retry — recording and retrying")
                state._prev_error_set = current_error_set
                logger.info(f"[PIPELINE][RETRY] calling _retry_failed()")
                state = await self._retry_failed(state, task_files)
                logger.info(f"[PIPELINE][RETRY] _retry_failed returned: stage={state.stage} verification.passed={state.verification.passed if state.verification else 'None'}")
        else:
            logger.info(f"[PIPELINE] no retry needed: passed={state.verification.passed} iteration={state.iteration}/{state.max_iterations}")
        
        # === PHASE 6: READY FOR APPROVAL ===
        logger.info(f"[PIPELINE] 📍 stage → AWAITING_APPROVAL (state={state.id})")
        state.stage = CodeGenStage.AWAITING_APPROVAL
        state.log("Code generation complete - awaiting approval", "success")
        logger.info(f"[PIPELINE] ✅ _run_pipeline END — final stage={state.stage}")
        
        return state
    
    async def _run_parallel(self, task_files: list[TaskFile], pipeline_id: str = "") -> list[AgentOutput]:
        """Run implementation agents in parallel with concurrency limit."""
        logger.info(f"[PARALLEL] ▶️  _run_parallel called: {len(task_files)} tasks pipeline_id={pipeline_id}")
        for i, tf in enumerate(task_files):
            logger.info(f"[PARALLEL]   task[{i}]: id={tf.task_id} file={tf.file} action={tf.action}")
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_AGENTS)
        logger.info(f"[PARALLEL] semaphore created MAX_CONCURRENT_AGENTS={MAX_CONCURRENT_AGENTS}")
        
        async def run_with_limit(task_file: TaskFile) -> AgentOutput:
            logger.info(f"[PARALLEL][SLOT] waiting for semaphore: task={task_file.task_id}")
            async with semaphore:
                logger.info(f"[PARALLEL][SLOT] semaphore acquired: task={task_file.task_id}")
                agent = ImplementationAgent(self._services_path)
                logger.info(f"[PARALLEL][SLOT] ImplementationAgent created for task={task_file.task_id}")
                result = await agent.implement(task_file, pipeline_id=pipeline_id)
                logger.info(f"[PARALLEL][SLOT] implement() returned: task={task_file.task_id} status={result.status} diff_len={len(result.diff or '')}")
                return result
        
        logger.info(f"[PARALLEL] launching asyncio.gather for {len(task_files)} tasks")
        results = await asyncio.gather(*[
            run_with_limit(tf) for tf in task_files
        ])
        logger.info(f"[PARALLEL] asyncio.gather done: {len(results)} results")
        for r in results:
            logger.info(f"[PARALLEL]   result: task={r.task_id} file={r.file} status={r.status} error={r.error_message or ''}")
        return list(results)
    
    async def _run_sequential(self, task_files: list[TaskFile], pipeline_id: str = "") -> list[AgentOutput]:
        """Run implementation agents sequentially."""
        logger.info(f"[SEQUENTIAL] ▶️  _run_sequential called: {len(task_files)} tasks pipeline_id={pipeline_id}")
        for i, tf in enumerate(task_files):
            logger.info(f"[SEQUENTIAL]   task[{i}]: id={tf.task_id} file={tf.file} action={tf.action}")
        results = []
        logger.info(f"[SEQUENTIAL] results list initialized empty")
        for idx, task_file in enumerate(task_files):
            logger.info(f"[SEQUENTIAL] ▶️  task {idx+1}/{len(task_files)}: id={task_file.task_id} file={task_file.file}")
            agent = ImplementationAgent(self._services_path)
            logger.info(f"[SEQUENTIAL] ImplementationAgent instance created")
            result = await agent.implement(task_file, pipeline_id=pipeline_id)
            logger.info(f"[SEQUENTIAL] implement() returned: status={result.status} diff_len={len(result.diff or '')} error={result.error_message or ''}")
            results.append(result)
            logger.info(f"[SEQUENTIAL] results now has {len(results)} items")
        logger.info(f"[SEQUENTIAL] ✅ done: {len(results)} total results")
        return results
    
    async def _retry_failed(
        self, 
        state: CodeGenState, 
        task_files: dict[str, TaskFile]
    ) -> CodeGenState:
        """Retry failed tasks based on verification errors."""
        logger.info(f"[RETRY] ▶️  _retry_failed START: state={state.id} iteration={state.iteration} max={state.max_iterations}")
        state.stage = CodeGenStage.FIXING
        logger.info(f"[RETRY] stage → FIXING")
        state.iteration += 1
        logger.info(f"[RETRY] iteration incremented → {state.iteration}")
        state.log(f"Retry iteration {state.iteration}: fixing issues...")
        logger.info(f"🔄 Starting retry iteration {state.iteration}/{state.max_iterations}")
        
        # Group errors by task_id (preferred) or file
        errors_by_task = {}
        logger.info(f"[RETRY] building errors_by_task from {len(state.verification.issues)} issues")
        for issue in state.verification.issues:
            logger.info(f"[RETRY]   issue: severity={issue.severity} task_id={issue.task_id} file={issue.file} issue='{issue.issue}'")
            if issue.severity == "error":
                # Prefer task_id if available
                key = issue.task_id or issue.file
                logger.info(f"[RETRY]   → key={key}")
                if key not in errors_by_task:
                    errors_by_task[key] = []
                    logger.info(f"[RETRY]   new key '{key}' added to errors_by_task")
                
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
                logger.info(f"[RETRY]   feedback built: {feedback}")
                errors_by_task[key].append(feedback)
                logger.info(f"[RETRY]   errors_by_task['{key}'] now has {len(errors_by_task[key])} entries")
        
        logger.info(f"[RETRY] errors_by_task keys={list(errors_by_task.keys())}")
        logger.info(f"   └─ Tasks with errors: {len(errors_by_task)}")
        for task_key, errors in errors_by_task.items():
            logger.debug(f"      └─ {task_key}: {len(errors)} errors")
        
        # Retry failed tasks
        new_diffs = []
        logger.info(f"[RETRY] new_diffs list initialized empty")
        logger.info(f"[RETRY] iterating over {len(task_files)} task_files")
        for task_id, task_file in task_files.items():
            logger.info(f"[RETRY] checking task_id={task_id} file={task_file.file}")
            # Check if this task has errors (by task_id or file)
            task_errors = errors_by_task.get(task_id) or errors_by_task.get(task_file.file)
            logger.info(f"[RETRY]   task_errors for '{task_id}': {len(task_errors) if task_errors else 0} errors")
            
            if task_errors:
                logger.info(f"[RETRY]   → task HAS errors, attempting fix")
                # Find the original diff
                original_diff = next(
                    (d for d in state.diffs if d.task_id == task_id),
                    None
                )
                logger.info(f"[RETRY]   original_diff found={original_diff is not None} diff_len={len(original_diff.diff) if original_diff and original_diff.diff else 0}")
                
                if original_diff and original_diff.diff:
                    logger.info(f"[RETRY]   calling fix_diff for {task_file.file}")
                    state.log(f"Fixing {task_file.file} ({len(task_errors)} errors)...")
                    
                    agent = ImplementationAgent(self._services_path)
                    logger.info(f"[RETRY]   ImplementationAgent created for fix")
                    fixed = await agent.fix_diff(
                        task_file,
                        original_diff.diff,
                        task_errors  # Pass structured feedback
                    )
                    logger.info(f"[RETRY]   fix_diff returned: status={fixed.status} diff_len={len(fixed.diff or '')} error={fixed.error_message or ''}")
                    new_diffs.append(fixed)
                    logger.info(f"[RETRY]   fixed diff appended, new_diffs={len(new_diffs)}")
                else:
                    logger.info(f"[RETRY]   no original diff — re-running implement() from scratch")
                    # Re-run from scratch
                    agent = ImplementationAgent(self._services_path)
                    result = await agent.implement(task_file, pipeline_id=state.id)
                    logger.info(f"[RETRY]   implement() from scratch returned: status={result.status} diff_len={len(result.diff or '')}")
                    new_diffs.append(result)
                    logger.info(f"[RETRY]   new_diffs={len(new_diffs)}")
            else:
                logger.info(f"[RETRY]   → task has NO errors, keeping original diff")
                # Keep original
                original = next(
                    (d for d in state.diffs if d.task_id == task_id),
                    None
                )
                logger.info(f"[RETRY]   original found={original is not None}")
                if original:
                    new_diffs.append(original)
                    logger.info(f"[RETRY]   kept original diff, new_diffs={len(new_diffs)}")
        
        logger.info(f"[RETRY] new_diffs assembled: {len(new_diffs)} total")
        for d in new_diffs:
            logger.info(f"[RETRY]   diff: task={d.task_id} file={d.file} status={d.status} diff_len={len(d.diff or '')}")
        state.diffs = new_diffs
        logger.info(f"[RETRY] state.diffs updated")
        
        # Re-verify
        state.stage = CodeGenStage.VERIFYING
        logger.info(f"[RETRY] stage → VERIFYING for re-verify")
        state.log("Re-verifying...")
        
        successful_diffs = [d for d in new_diffs if d.status == "success"]
        logger.info(f"[RETRY] successful_diffs for re-verify: {len(successful_diffs)} of {len(new_diffs)}")
        
        try:
            logger.info(f"[RETRY] calling verifier.verify() plan_tasks={len(state.plan.tasks)} diffs={len(successful_diffs)}")
            self._verifier._pipeline_id = state.id  # token tracking
            verification = await self._verifier.verify(
                plan=state.plan,
                diffs=successful_diffs,
            )
            logger.info(f"[RETRY] verify() returned: passed={verification.passed} issues={len(verification.issues)}")
            for iss in verification.issues:
                logger.info(f"[RETRY]   issue: severity={iss.severity} file={iss.file} issue='{iss.issue}'")
            state.verification = verification
            logger.info(f"[RETRY] state.verification updated")
            
            if verification.passed:
                state.log("Verification passed after fixes!", "success")
                logger.info("✅ Verification passed after retry")
            else:
                error_count = sum(1 for i in verification.issues if i.severity == "error")
                logger.info(f"[RETRY] still failing: error_count={error_count}")
                state.log(f"Still {error_count} errors after retry", "warning")
                logger.warning(f"⚠️ Still {error_count} errors after retry {state.iteration}")
                
                # Check for stale errors before recursing
                current_error_set = frozenset(
                    i.issue for i in verification.issues if i.severity == "error"
                )
                logger.info(f"[RETRY] current_error_set={current_error_set}")
                prev_error_set = getattr(state, '_prev_error_set', None)
                logger.info(f"[RETRY] prev_error_set={prev_error_set}")
                
                if prev_error_set is not None and current_error_set == prev_error_set:
                    logger.warning(
                        f"⏭ Errors identical to previous retry — stopping "
                        f"(same {len(current_error_set)} errors, further retries won't help)"
                    )
                    logger.warning(f"[RETRY] STALE errors — stopping retry loop")
                    state.log("Errors unchanged — stopping retry loop", "warning")
                elif state.iteration < state.max_iterations:
                    logger.info(f"[RETRY] errors changed AND iteration budget remains ({state.iteration}<{state.max_iterations}) — recursing")
                    # Still have budget and new errors — continue
                    state._prev_error_set = current_error_set
                    logger.info(f"[RETRY] _prev_error_set updated, calling _retry_failed recursively")
                    return await self._retry_failed(state, task_files)
                else:
                    logger.info(f"[RETRY] max iterations reached ({state.max_iterations}) — stopping")
                    logger.info(f"[RETRY] Max iterations ({state.max_iterations}) reached")
                    
        except Exception as e:
            logger.error(f"[RETRY] verifier.verify() RAISED: {e}", exc_info=True)
            state.log(f"Verification error during retry: {e}", "warning")
        
        logger.info(f"[RETRY] ✅ _retry_failed END: stage={state.stage} verification.passed={state.verification.passed if state.verification else 'None'}")
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
        
        # ── POST-APPROVAL SYNC: apply diffs + git commit + rebuild graph ─────
        if _sync_enabled():
            asyncio.create_task(self._post_approval_sync(state))

        return state

    async def _post_approval_sync(self, state: CodeGenState) -> None:
        """
        Background task: apply diffs to disk, git commit, rebuild graph.
        Runs after approve() returns. Never raises — all errors logged.
        """
        from pathlib import Path as _Path

        # _services_path is already the services/ directory
        services_root = _Path(self._services_path)

        state.sync_status = "applying"
        n_diffs = len([d for d in state.diffs if getattr(d, "status", "") == "success"])
        state.log(f"Applying diffs to disk ({n_diffs} files)...")

        # 1. Apply diffs
        try:
            from modules.codegen.diff_applier import DiffApplier
            applier = DiffApplier(services_root)
            apply_result = applier.apply(state.diffs)
        except Exception as e:
            state.sync_error = f"Diff apply crashed: {e}"
            state.sync_status = "failed"
            state.log(f"Diff apply failed: {e}", "error")
            return

        if not apply_result.success:
            reason = str(apply_result.failure_reasons)
            state.sync_error = f"Diff apply failed: {reason}"
            state.sync_status = "failed"
            state.log(f"Diff apply failed: {reason}", "error")
            return

        state.log(f"Diffs applied successfully ({len(apply_result.files_written)} files)")

        # 2. Git commit
        state.sync_status = "committing"
        state.log("Creating git commit...")
        try:
            from modules.codegen.version_manager import VersionManager
            vm = VersionManager(services_root)
            if not vm.is_git_repo():
                state.log("services/ is not a git repo — skipping commit", "warning")
            else:
                commit_result = vm.commit(apply_result.files_written, state)
                if commit_result.success:
                    state.git_commit_hash = commit_result.commit_hash
                    state.log(f"Git commit created: {commit_result.commit_hash[:8]}")
                else:
                    state.log(f"Git commit failed: {commit_result.error}", "error")
        except Exception as e:
            state.log(f"Git commit failed: {e}", "error")

        # 3. Rebuild graph
        state.sync_status = "rebuilding"
        state.log("Rebuilding code graph (incremental)...")
        rebuilder = getattr(self, "_graph_rebuilder", None)
        if rebuilder is None:
            state.log("GraphRebuilder not wired — skipping graph rebuild", "warning")
            state.sync_status = "complete"
            return

        try:
            rebuild_result = await rebuilder.rebuild(state)
            if rebuild_result.success:
                state.log(f"Graph rebuild complete — {rebuild_result.symbol_count} symbols loaded")
                state.sync_status = "complete"
            else:
                state.log(f"Graph rebuild failed: {rebuild_result.error}", "error")
                state.sync_error = rebuild_result.error
                state.sync_status = "failed"
        except Exception as e:
            state.log(f"Graph rebuild failed: {e}", "error")
            state.sync_error = str(e)
            state.sync_status = "failed"

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
        
        # ── DEMO CACHE: save rejected runs so they appear in history ─────────
        if _CACHE_AVAILABLE and state.diffs:
            try:
                impact = state.impact_report or {}
                change_req = impact.get("change_request", "Code generation")[:60]
                services = impact.get("requirements", {}).get("services", []) if isinstance(impact.get("requirements"), dict) else []
                label_base = f"{change_req} [{', '.join(services[:2])}]" if services else change_req
                label = f"[REJECTED] {label_base}"  # tag it as rejected
                cache_input = {
                    "change_request": impact.get("change_request", ""),
                    "services": services,
                    "rejection_reason": reason or "Rejected by user",
                }
                token_usage = {}
                try:
                    from modules.cache.token_tracker import get_tracker
                    _tracker = get_tracker()
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
                        "rejected": True,
                        "rejection_reason": reason or "Rejected by user",
                    },
                    token_usage=token_usage,
                )
                logger.info(f"[CACHE] CodeGen rejected run saved: id={state.id!r} label={label!r}")
            except Exception as _ce:
                logger.warning(f"[CACHE] Save rejected run failed (non-fatal): {_ce}")
        
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
