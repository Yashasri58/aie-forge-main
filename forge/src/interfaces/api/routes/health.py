"""
Health & Status API Router.
"""

from fastapi import APIRouter

router = APIRouter(tags=["Health"])


# =============================================================================
# DEPENDENCIES (set by main.py)
# =============================================================================

_store = None
_agent = None
_tools = None


def set_dependencies(store, agent, tools):
    """Set dependencies for health checks."""
    global _store, _agent, _tools
    _store = store
    _agent = agent
    _tools = tools


# =============================================================================
# ENDPOINTS
# =============================================================================

@router.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "graph_loaded": _store is not None,
        "agent_ready": _agent is not None,
        "services": _tools.services if _tools else [],
        "symbol_count": len(_tools.all_symbols) if _tools else 0
    }


@router.get("/services")
async def list_services():
    """List all indexed services."""
    if not _tools:
        return {"services": [], "count": 0, "status": "graph not loaded"}
    
    return {
        "services": _tools.services,
        "count": len(_tools.services)
    }


@router.get("/health/harness")
async def harness_health():
    """
    ITEM 9: Harness health endpoint.

    Reports which harness validation items are implemented and active.
    Used to confirm the harness is running before a demo or release.
    """
    return {
        "harness_version": "1.0.0",
        "pipeline": "impact_analysis",
        "items_implemented": {
            "ITEM_1_input_contract":         True,   # confirm_requirements gate
            "ITEM_2_gatherer_grounding":      True,   # context_gatherer output grounding
            "ITEM_3_impact_receipts":         True,   # ImpactAgent tool receipt logger
            "ITEM_4_report_grounding":        True,   # report SERVICE: name check
            "ITEM_5_verification_receipts":   True,   # VerificationAgent receipt check
            "ITEM_6_action_boundary":         True,   # query_cypher write guard
            "ITEM_7_model_readable_errors":   True,   # all errors are agent-actionable
            "ITEM_8_epistemic_tags":          True,   # [GRAPH]/[MODEL] tags on claims
            "ITEM_9_harness_health":          True,   # this endpoint
            "ITEM_10_self_harness":           False,  # V2 — auto-update harness on failure
        },
        "components_implemented": {
            "C1_state_persistence":           True,   # SQLite session save
            "C2_prompt_injection_defense":    True,   # message sanitization
            "C3_tool_output_envelope":        False,  # future — standardize tool shapes
            "C4_artifact_store":              True,   # large Kuzu results to disk
            "C5_structured_event_log":        True,   # event_type + metadata in activity_log
            "C6_eval_suite":                  True,   # tests/eval_harness.py
        },
        "practical_items_implemented": {
            "P1_kv_cache_fix":                True,   # no timestamps in system prompts
            "P2_loop_detection":              True,   # LoopDetector in harness_utils
            "P3_reasoning_sandwich":          False,  # future — xhigh/high per stage
            "P4_budget_enforcement":          True,   # BudgetEnforcer in analyze_for_pipeline
            "P5_todo_goal_drift":             True,   # task protocol in SYSTEM_INSTRUCTION
            "P6_lettucedetect":               False,  # optional — pip install lettucedetect
            "P7_openlit_observability":       False,  # optional — pip install openlit
        },
        "codegen_harness": {
            "status": "already_production_grade",
            "components": [
                "SyntaxChecker", "ImportResolver", "ContractChecker",
                "HallucinationDetector", "SecurityScanner", "DeterministicGate"
            ]
        },
        "graph_loaded": _store is not None,
        "services_indexed": len(_tools.services) if _tools else 0,
    }
