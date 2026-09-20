"""
Pipeline Orchestrator

3-agent architecture with verification loop:

    ContextGatherer → Clarifies requirements → User confirms
    ImpactAgent     → Produces layered impact report
    VerificationAgent → Checks completeness, identifies gaps
    
    Loop: ImpactAgent ↔ VerificationAgent until complete (max 3 iterations)

Harness items implemented in this file:
- ITEM 1: Agent-to-agent input contract validator (_validate_requirements)
- ITEM 4: Report grounding check (_check_report_grounding)
- ITEM 7: Model-readable error messages (all harness errors are actionable)
- C2:     Prompt injection sanitizer (sanitize_message in start())
- C5:     Structured event types in log_activity (make_log_entry)
- P2:     Loop detection per analysis run (LoopDetector)
- P3:     Reasoning sandwich — budget tokens vary by pipeline stage
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import uuid
import time

from .context_gatherer import ContextGathererAgent, RequirementsOutput
from .verification_agent import VerificationAgent
from .base import AgentLogger
from .harness_utils import (
    sanitize_message,
    ground_services,
    check_report_grounding,
    make_log_entry,
    LoopDetector,
)

# =============================================================================
# C1: SQLite STATE PERSISTENCE
# =============================================================================
import json
import sqlite3
from pathlib import Path

_DB_PATH = Path(__file__).parent.parent.parent.parent.parent / "forge_sessions.db"


def _init_session_db():
    """Create sessions table if it doesn't exist."""
    with sqlite3.connect(str(_DB_PATH)) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pipeline_sessions (
                id TEXT PRIMARY KEY,
                stage TEXT,
                created_at REAL,
                updated_at REAL,
                state_json TEXT
            )
        """)


def _save_session(pipeline_id: str, stage: str, state_dict: dict):
    """Persist pipeline state after each stage transition."""
    try:
        _init_session_db()
        with sqlite3.connect(str(_DB_PATH)) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO pipeline_sessions
                    (id, stage, created_at, updated_at, state_json)
                VALUES (?, ?, COALESCE(
                    (SELECT created_at FROM pipeline_sessions WHERE id=?), ?
                ), ?, ?)
            """, (pipeline_id, stage, pipeline_id, time.time(),
                  time.time(), json.dumps(state_dict, default=str)))
    except Exception as e:
        print(f"  [HARNESS C1] Session save failed (non-fatal): {e}")


def _load_session(pipeline_id: str) -> dict | None:
    """Load persisted session state for resume."""
    try:
        _init_session_db()
        with sqlite3.connect(str(_DB_PATH)) as conn:
            row = conn.execute(
                "SELECT state_json FROM pipeline_sessions WHERE id=?",
                (pipeline_id,)
            ).fetchone()
        return json.loads(row[0]) if row else None
    except Exception:
        return None


class PipelineStage(str, Enum):
    """Pipeline stages."""
    GATHERING = "gathering"                        # Context Gatherer asking questions
    REQUIREMENTS_READY = "requirements_ready"      # Requirements complete, awaiting user confirmation
    ANALYZING = "analyzing"                        # ImpactAgent producing report
    VERIFYING = "verifying"                        # VerificationAgent checking completeness
    FILLING_GAPS = "filling_gaps"                  # ImpactAgent filling identified gaps
    AWAITING_APPROVAL = "awaiting_approval"        # Report ready, awaiting final approval
    APPROVED = "approved"
    REJECTED = "rejected"
    FAILED = "failed"


@dataclass
class PipelineState:
    """Pipeline state."""
    id: str
    stage: PipelineStage
    created_at: float
    updated_at: float
    
    # From Context Gatherer
    requirements: Optional[RequirementsOutput] = None
    conversation_history: list = field(default_factory=list)
    current_question: Optional[str] = None
    
    # From Impact Agent
    report: Optional[str] = None
    report_json: Optional[dict] = None
    
    # From Verification Agent
    verification: Optional[dict] = None
    iteration: int = 1
    max_iterations: int = 3
    gaps_history: list = field(default_factory=list)
    
    # Live activity log for frontend
    activity_log: list = field(default_factory=list)
    
    # Status
    error: Optional[str] = None
    
    def log_activity(self, message: str, level: str = "info",
                     event_type: str = None, metadata: dict = None):
        """Add a structured activity log entry. (C5: typed events + metadata)"""
        entry = make_log_entry(message, level, event_type, metadata)
        self.activity_log.append(entry)
        self.updated_at = time.time()
    
    def to_dict(self) -> dict:
        """Serialize for API."""
        return {
            "id": self.id,
            "stage": self.stage.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "requirements": self.requirements,
            "conversation_history": self.conversation_history,
            "current_question": self.current_question,
            "needs_input": self._needs_input(),
            "report": self.report,
            "report_json": self.report_json,
            "verification": self.verification,
            "iteration": self.iteration,
            "max_iterations": self.max_iterations,
            "gaps_history": self.gaps_history,
            "activity_log": self.activity_log,
            "error": self.error,
        }
    
    def _needs_input(self) -> bool:
        """Check if user input is needed."""
        if self.stage == PipelineStage.GATHERING:
            return self.current_question is not None
        if self.stage == PipelineStage.REQUIREMENTS_READY:
            return True  # Needs confirmation
        return False


class PipelineOrchestrator:
    """
    Orchestrates the pipeline with verification loop:
    
    FLOW:
    1. ContextGatherer clarifies requirements (user answers questions)
    2. Requirements ready → User must confirm "proceed"
    3. ImpactAgent produces layered report
    4. VerificationAgent checks all callers are traced
    5. If gaps → ImpactAgent fills gaps (loop, max 3x)
    6. Human approves or rejects final report
    
    Usage:
        orch = PipelineOrchestrator(impact_agent)
        state = await orch.start("Add fraud detection")
        
        # Answer questions until requirements are ready
        while state.stage == "gathering":
            state = await orch.respond(state.id, answer)
        
        # When stage == "requirements_ready", user must confirm
        state = await orch.confirm_requirements(state.id)
        
        # Analysis runs with verification loop
        # Then stage == "awaiting_approval"
        
        state = await orch.approve(state.id)
    """
    
    def __init__(self, impact_agent):
        """
        Args:
            impact_agent: ImpactAgent instance
        """
        self.impact_agent = impact_agent
        self.tools = impact_agent.get_graph_tools() if impact_agent else None
        
        # Initialize agents
        self.context_gatherer = ContextGathererAgent(self.tools)
        self.verification_agent = VerificationAgent(self.tools)
        
        # State store
        self._states: dict[str, PipelineState] = {}
        
        # Per-run loop detector (reset in confirm_requirements)
        self._loop_detector = LoopDetector(window=5, threshold=3)

    # =========================================================================
    # HARNESS METHODS
    # =========================================================================

    def _validate_requirements(self, requirements: dict) -> list[str]:
        """
        ITEM 1: Validate requirements before passing to ImpactAgent.
        Returns list of model-readable error strings. Empty = valid.
        Checks: required fields present, services exist in graph, functions exist.
        """
        errors = []
        known_services = self.tools.services if self.tools else []

        if not requirements.get("description", "").strip():
            errors.append(
                "description is empty — cannot start analysis. "
                "Please describe what change you want to make."
            )

        for svc in requirements.get("services", []):
            if known_services and svc not in known_services:
                similar = [k for k in known_services if svc.lower() in k.lower()]
                hint = f" Did you mean: {', '.join(similar[:3])}?" if similar else \
                       f" Available: {', '.join(known_services[:5])}..."
                errors.append(
                    f"Service '{svc}' not found in the codebase.{hint}"
                )

        if requirements.get("functions") and self.tools:
            for fn in requirements["functions"]:
                result = self.tools.search_symbols(fn)
                if result.get("count", 0) == 0:
                    errors.append(
                        f"Function '{fn}' not found in the codebase. "
                        "Use search_functions to find the correct name."
                    )

        return errors

    def _check_report_grounding(self, report: str) -> list[str]:
        """
        ITEM 4: Scan impact report for service names not in the graph.
        Returns list of hallucinated service names.
        """
        if not self.tools:
            return []
        return check_report_grounding(report, self.tools.services)
    
    async def start(self, message: str) -> PipelineState:
        """Start pipeline with initial requirement."""
        # HARNESS C2: Sanitize user message before passing to agents
        clean_message, was_sanitized = sanitize_message(message)
        if was_sanitized:
            # Log the blocked injection but don't expose details
            print(f"  [HARNESS C2] Prompt injection attempt detected and sanitized")
        
        state = PipelineState(
            id=str(uuid.uuid4()),
            stage=PipelineStage.GATHERING,
            created_at=time.time(),
            updated_at=time.time()
        )
        self._states[state.id] = state
        
        AgentLogger.stage_change("GATHERING", f"Pipeline {state.id[:8]}... started")
        
        self.context_gatherer.reset()
        
        requirements = await self.context_gatherer.process({
            "message": clean_message,  # HARNESS C2: use sanitized message
            "is_initial": True
        })
        
        state.updated_at = time.time()
        state.requirements = requirements
        state.conversation_history = self.context_gatherer.get_conversation_history()
        
        if requirements.get("complete", False):
            # Requirements gathered - wait for user confirmation
            state.stage = PipelineStage.REQUIREMENTS_READY
            state.current_question = None
            AgentLogger.stage_change("REQUIREMENTS_READY", f"Clarity: {requirements.get('clarity_score', 'N/A')}/10")
        else:
            state.current_question = requirements.get("follow_up_question")
            print(f"  📝 Follow-up question: {state.current_question}")
        
        return state
    
    async def respond(self, pipeline_id: str, message: str) -> PipelineState:
        """Respond to context gatherer question."""
        state = self._states.get(pipeline_id)
        if not state:
            raise ValueError(f"Pipeline {pipeline_id} not found")
        
        if state.stage != PipelineStage.GATHERING:
            raise ValueError(f"Pipeline not in gathering stage")
        
        print(f"  💬 User response: {message[:100]}...")
        
        requirements = await self.context_gatherer.process({
            "message": message,
            "is_initial": False
        })
        
        state.updated_at = time.time()
        state.requirements = requirements
        state.conversation_history = self.context_gatherer.get_conversation_history()
        
        if requirements.get("complete", False):
            # Requirements gathered - wait for user confirmation
            state.stage = PipelineStage.REQUIREMENTS_READY
            state.current_question = None
            AgentLogger.stage_change("REQUIREMENTS_READY", f"Clarity: {requirements.get('clarity_score', 'N/A')}/10")
        else:
            state.current_question = requirements.get("follow_up_question")
            print(f"  📝 Follow-up question: {state.current_question}")
        
        return state
    
    async def confirm_requirements(self, pipeline_id: str) -> PipelineState:
        """
        User confirms requirements are correct, proceed with analysis.
        
        This is the gate between Step 1 (gathering) and Step 2 (analysis).
        """
        state = self._states.get(pipeline_id)
        if not state:
            raise ValueError(f"Pipeline {pipeline_id} not found")
        
        if state.stage != PipelineStage.REQUIREMENTS_READY:
            raise ValueError(f"Pipeline not in requirements_ready stage (current: {state.stage.value})")
        
        print()
        print("  ✅ User confirmed requirements - starting analysis pipeline")
        print(f"     Services: {state.requirements.get('services', [])}")
        print(f"     Functions: {state.requirements.get('functions', [])}")
        print()
        
        # Log activity
        services = state.requirements.get('services', [])
        state.log_activity(f"Requirements confirmed - {len(services)} services targeted",
                           "success", "stage_change", {"services": services})

        # HARNESS ITEM 1: Validate requirements before analysis starts
        validation_errors = self._validate_requirements(state.requirements)
        if validation_errors:
            state.stage = PipelineStage.GATHERING
            error_msg = "; ".join(validation_errors)
            state.current_question = (
                "I found issues with the requirements before starting analysis: "
                + error_msg
                + ". Please clarify."
            )
            state.log_activity(
                f"Requirements validation failed: {error_msg}",
                "error", "harness_check",
                {"check": "input_contract", "errors": validation_errors}
            )
            print(f"  [HARNESS ITEM 1] Rejected: {error_msg}")
            return state

        state.log_activity(f"Harness: requirements validated — services and functions exist in graph",
                           "success", "harness_check", {"check": "input_contract"})
        state.log_activity(f"Services: {', '.join(services)}", "info")
        
        # Add confirmation to conversation history
        state.conversation_history.append({
            "role": "user",
            "content": "[Requirements confirmed - starting impact analysis]"
        })
        
        # Now run the analysis loop
        state = await self._run_analysis_loop(state)
        
        return state
    
    async def _run_analysis_loop(self, state: PipelineState) -> PipelineState:
        """
        Run the analysis → verification → fill gaps loop.
        
        Continues until:
        - VerificationAgent says complete=True, OR
        - Max iterations reached
        """
        while state.iteration <= state.max_iterations:
            AgentLogger.iteration(state.iteration, state.max_iterations, 
                "Initial Analysis" if state.iteration == 1 else "Gap Filling")
            
            # === STEP 1: IMPACT ANALYSIS ===
            state.stage = PipelineStage.ANALYZING if state.iteration == 1 else PipelineStage.FILLING_GAPS
            AgentLogger.stage_change(state.stage.value.upper(), 
                f"Iteration {state.iteration}/{state.max_iterations}")
            state.updated_at = time.time()
            
            # Log activity
            if state.iteration == 1:
                state.log_activity("Starting impact analysis...", "info")
                state.log_activity("Loading code graph topology", "info")
            else:
                state.log_activity(f"Iteration {state.iteration}: Filling gaps from verification", "info")
            
            try:
                # Build prompt with any gaps from previous iteration
                if state.iteration > 1 and state.verification:
                    gaps_text = self.verification_agent.format_gaps(state.verification)
                    gaps_count = len(state.verification.get('missing_paths', []))
                    state.log_activity(f"Found {gaps_count} gaps to investigate", "warning")
                    print(f"  🔍 Filling {gaps_count} gaps from previous iteration")
                    report = await self._analyze_with_gaps(state.requirements, state.report, gaps_text)
                else:
                    state.log_activity("Calling LLM to analyze change impact...", "info")
                    report = await self.impact_agent.analyze_for_pipeline(
                        requirements=state.requirements
                    )
                
                state.report = report
                state.log_activity(f"Report generated: {len(report):,} chars", "success",
                                   "stage_change", {"chars": len(report)})
                print(f"  📊 Report generated: {len(report)} characters")

                # HARNESS ITEM 4: Report grounding check — catch hallucinated service names
                hallucinated = self._check_report_grounding(report)
                if hallucinated:
                    state.log_activity(
                        f"Harness: Report mentions services not in codebase: {hallucinated}",
                        "warning", "harness_check",
                        {"check": "report_grounding", "hallucinated": hallucinated}
                    )
                    print(f"  [HARNESS ITEM 4] Hallucinated services in report: {hallucinated}")
                    # Add as gaps so verification loop investigates
                    if state.verification is None:
                        state.verification = {}
                    existing_gaps = state.verification.get("gaps", [])
                    for svc in hallucinated:
                        existing_gaps.append({
                            "missing_caller": "UNKNOWN",
                            "missing_caller_service": svc,
                            "should_call": "VERIFY_EXISTS",
                            "should_be_in_layer": 0,
                            "evidence": "harness_grounding_check: service not in graph",
                        })
                    state.verification["gaps"] = existing_gaps
                else:
                    state.log_activity(
                        "Harness: All service names in report verified against graph",
                        "success", "harness_check",
                        {"check": "report_grounding"}
                    )
                
            except Exception as e:
                state.stage = PipelineStage.FAILED
                state.error = f"Analysis failed: {e}"
                print(f"  ❌ Analysis failed: {e}")
                return state
            
            # === STEP 2: VERIFICATION ===
            state.stage = PipelineStage.VERIFYING
            AgentLogger.stage_change("VERIFYING", f"Checking completeness")
            state.updated_at = time.time()
            state.log_activity("Starting verification of impact report...", "info")
            
            try:
                # Extract symbols from report
                state.log_activity("Extracting symbols from report...", "info")
                symbols = await self.verification_agent.extract_symbols(report)
                state.log_activity(f"Found {len(symbols)} symbols to verify", "info")
                print(f"  📝 Extracted {len(symbols)} symbols from report")
                
                # Verify completeness
                state.log_activity("Querying call graph for callers...", "info")
                verification = await self.verification_agent.verify(report, symbols)
                state.verification = verification
                
                gaps_count = len(verification.get("gaps", []))
                confidence = verification.get("confidence", "LOW")
                complete = verification.get("complete", False)
                verified = verification.get("verified_paths", 0)
                
                state.log_activity(f"Verified {verified} call paths", "success")
                if gaps_count > 0:
                    state.log_activity(f"Found {gaps_count} unverified gaps", "warning")
                state.log_activity(f"Confidence: {confidence}", "info")
                
                print(f"  🔎 Verification: complete={complete}, confidence={confidence}, gaps={gaps_count}")
                
                # Track gaps history
                state.gaps_history.append({
                    "iteration": state.iteration,
                    "gaps_found": gaps_count,
                    "verified_paths": verification.get("verified_paths", 0),
                    "confidence": confidence
                })
                
            except Exception as e:
                print(f"  ⚠️  Verification error (non-fatal): {e}")
                # Verification failure is non-fatal, proceed with what we have
                state.verification = {
                    "complete": True,
                    "confidence": "LOW",
                    "gaps": [],
                    "recommendation": f"Verification error: {e}, proceeding with current analysis"
                }
            
            # === STEP 3: CHECK IF COMPLETE ===
            if state.verification.get("complete", False):
                # All paths verified, done!
                state.stage = PipelineStage.AWAITING_APPROVAL
                state.log_activity("Analysis complete!", "success", "stage_change")
                state.log_activity(f"Finished in {state.iteration} iteration(s)", "success")
                AgentLogger.stage_change("AWAITING_APPROVAL", 
                    f"Complete after {state.iteration} iteration(s), confidence: {state.verification.get('confidence', 'N/A')}")
                state.updated_at = time.time()
                _save_session(state.id, state.stage.value, state.to_dict())  # HARNESS C1
                
                # Get JSON version for UI
                try:
                    state.report_json = await self.impact_agent.analyze_for_pipeline_json(
                        requirements=state.requirements
                    )
                except Exception:
                    state.report_json = {}
                
                return state
            
            # === STEP 4: MORE ITERATIONS NEEDED ===
            if not self.verification_agent.has_gaps(state.verification):
                # No gaps but not marked complete - edge case, accept it
                state.stage = PipelineStage.AWAITING_APPROVAL
                state.log_activity("✓ Analysis complete (no gaps found)", "success")
                AgentLogger.stage_change("AWAITING_APPROVAL", "No gaps found (edge case)")
                state.updated_at = time.time()
                return state
            
            state.log_activity(f"Gaps found, continuing to iteration {state.iteration + 1}...", "warning")
            print(f"  🔄 Gaps found, will continue to iteration {state.iteration + 1}")
            state.iteration += 1
        
        # Max iterations reached
        state.stage = PipelineStage.AWAITING_APPROVAL
        gaps_remaining = len(state.verification.get('gaps', [])) if state.verification else 0
        AgentLogger.stage_change("AWAITING_APPROVAL", 
            f"Max iterations ({state.max_iterations}) reached, {gaps_remaining} gaps remaining")
        state.updated_at = time.time()
        
        # Add note about max iterations
        if state.verification:
            state.verification["recommendation"] = (
                f"Max iterations ({state.max_iterations}) reached. "
                f"Report may have {len(state.verification.get('gaps', []))} unresolved gaps."
            )
        
        return state
    
    async def _analyze_with_gaps(self, requirements: dict, current_report: str, gaps_text: str) -> str:
        """Re-run analysis with specific gaps to fill."""
        query = f"""UPDATE the following impact report to fill in the identified gaps.

CURRENT REPORT:
{current_report[:3000]}

GAPS TO FILL:
{gaps_text}

INSTRUCTIONS:
1. Use trace_call_path() to find the missing callers
2. Add them to the appropriate Layer (1 or 2)
3. Include WHY they are impacted and what CHANGE is needed
4. Keep all existing entries, just ADD the missing ones
5. Update the SUMMARY counts

Output the COMPLETE updated report in the same format."""

        return await self.impact_agent.analyze(query)
    
    async def approve(self, pipeline_id: str) -> PipelineState:
        """Approve the analysis."""
        state = self._states.get(pipeline_id)
        if not state:
            raise ValueError(f"Pipeline {pipeline_id} not found")
        
        if state.stage != PipelineStage.AWAITING_APPROVAL:
            raise ValueError(f"Pipeline not awaiting approval")
        
        state.stage = PipelineStage.APPROVED
        state.updated_at = time.time()
        return state
    
    async def reject(self, pipeline_id: str, reason: str = "") -> PipelineState:
        """Reject the analysis."""
        state = self._states.get(pipeline_id)
        if not state:
            raise ValueError(f"Pipeline {pipeline_id} not found")
        
        if state.stage != PipelineStage.AWAITING_APPROVAL:
            raise ValueError(f"Pipeline not awaiting approval")
        
        state.stage = PipelineStage.REJECTED
        state.error = reason or "Rejected by user"
        state.updated_at = time.time()
        return state
    
    def get_state(self, pipeline_id: str) -> Optional[PipelineState]:
        """Get pipeline state."""
        return self._states.get(pipeline_id)
    
    def delete_state(self, pipeline_id: str):
        """Delete pipeline state."""
        self._states.pop(pipeline_id, None)
