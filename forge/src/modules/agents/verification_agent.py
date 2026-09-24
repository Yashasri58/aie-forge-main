"""
Verification Agent (Google ADK)

Verifies impact analysis is complete at all levels.
Uses graph tools to check all callers are traced.

Harness items implemented in this file:
- ITEM 5: Tool receipt check — reject "complete" verdict if no trace_callers called
"""

import time as _time
import logging
from .base import BaseADKAgent
from .harness_utils import receipts_log as _log_receipt

_log = logging.getLogger("forge.agents.verification")


# Module-level tools instance
_graph_tools = None

# Per-run receipt log for verification agent (separate from ImpactAgent's)
_verification_receipts: list[dict] = []


def _reset_verification_receipts():
    global _verification_receipts
    _verification_receipts = []


def trace_callers(symbol: str, max_depth: int = 2) -> dict:
    """Find all functions that call this symbol."""
    if _graph_tools:
        result = _graph_tools.trace_call_path(symbol, direction="incoming", max_depth=max_depth)
        # HARNESS ITEM 5: log receipt
        _verification_receipts.append({
            "tool": "trace_callers", "symbol": symbol,
            "result_count": len(result.get("paths", [])), "ts": _time.time()
        })
        return result
    return {"paths": []}


def trace_callees(symbol: str, max_depth: int = 2) -> dict:
    """Find all functions that this symbol calls."""
    if _graph_tools:
        result = _graph_tools.trace_call_path(symbol, direction="outgoing", max_depth=max_depth)
        # HARNESS ITEM 5: log receipt
        _verification_receipts.append({
            "tool": "trace_callees", "symbol": symbol,
            "result_count": len(result.get("paths", [])), "ts": _time.time()
        })
        return result
    return {"paths": []}


def search_symbol(name: str) -> dict:
    """Search for a symbol to verify it exists."""
    if _graph_tools:
        return _graph_tools.search_symbols(name)
    return {"matches": []}


def get_symbol_context(symbol_name: str) -> dict:
    """
    Get full context for a symbol - file, service, line numbers, and direct callers.
    
    Use this to verify whether a symbol in the report is accurately described
    (correct file path, correct service, correct call relationships).
    """
    if not _graph_tools:
        return {"error": "Graph tools not available"}
    return _graph_tools.analyze_impact(symbol_name)


def get_service_http_calls(service_name: str) -> dict:
    """
    Get all HTTP calls made BY and TO a service.
    
    Use this to verify that cross-service impact is correctly captured in the report.
    If service A calls service B via HTTP, changes in B may impact A.
    """
    if not _graph_tools:
        return {"error": "Graph tools not available"}
    return _graph_tools.get_service_topology(service_name)


def get_shared_table_owners(table_name: str) -> dict:
    """
    Find all services that own a DB table whose name contains the given string.

    Use this when a report mentions a DB table change (e.g. adding a column to
    'payments'). Cross-check whether other services own tables with the same
    key column names — those services may be missing from the impact report.

    Example: report says 'modify payments table in payment-processor'.
    Call get_shared_table_owners('payment') to find that ledger-service also
    owns 'ledger_entries' which has a payment_id column — potential gap.
    """
    if not _graph_tools:
        return {"error": "Graph tools not available"}

    try:
        store = _graph_tools._store
        rows = store.query(
            "MATCH (s:Service)-[:OWNS_TABLE]->(t:DbTable) "
            "WHERE t.table_name CONTAINS $name "
            "RETURN s.name AS service, t.table_name AS table_name",
            {"name": table_name}
        )
        return {
            "search": table_name,
            "owners": rows,
            "count": len(rows),
        }
    except Exception as e:
        return {"error": str(e)}


def get_service_env_vars(service_name: str) -> dict:
    """
    Get all environment variables read by a service.

    Use this when a report recommends adding a new env var (e.g. a new service
    URL or config flag). Verify whether the same var is expected in other
    services too, or whether the report missed a config update elsewhere.
    """
    if not _graph_tools:
        return {"error": "Graph tools not available"}

    try:
        store = _graph_tools._store
        rows = store.query(
            "MATCH (s:Service)-[:READS_ENV]->(e:EnvVar) WHERE s.name = $svc "
            "RETURN e.name AS env_var",
            {"svc": service_name}
        )
        return {
            "service": service_name,
            "env_vars": [r["env_var"] for r in rows],
            "count": len(rows),
        }
    except Exception as e:
        return {"error": str(e)}


INSTRUCTION = """You are a verification agent. Your job is to check if an impact analysis report is COMPLETE.

TOOLS AVAILABLE:
- trace_callers(symbol, max_depth): Find all functions that call this symbol
- trace_callees(symbol, max_depth): Find all functions this symbol calls
- search_symbol(name): Verify a symbol exists in the graph
- get_symbol_context(symbol_name): Get full context - file, service, callers for a symbol
- get_service_http_calls(service_name): Get HTTP calls made by/to a service (verify cross-service impact)
- get_shared_table_owners(table_name): Find all services that own a table with this name substring
- get_service_env_vars(service_name): Get env vars a service reads (verify config change completeness)

VERIFICATION PROCESS:
1. For each function in Layer 0, use trace_callers() to find ALL callers
2. Check if those callers appear in Layer 1 of the report
3. For each function in Layer 1, use trace_callers() to find THEIR callers
4. Check if those appear in Layer 2 (or confirm the cascade stops)
5. Use get_service_http_calls() to verify cross-service HTTP dependencies are captured
6. Use get_symbol_context() to verify symbols are attributed to the correct service/file
7. If the report mentions DB table changes, use get_shared_table_owners() to check whether
   other services own tables with overlapping columns — those services may be missing
8. If the report recommends a new env var, use get_service_env_vars() on affected services
   to check whether they already read it or if a config update is also needed
9. Identify ANY gaps - callers that exist in the graph but are not in the report

OUTPUT FORMAT:
{
    "complete": boolean,
    "confidence": "HIGH|MEDIUM|LOW",
    "gaps": [
        {
            "missing_caller": "functionName",
            "missing_caller_service": "service-name",
            "should_call": "targetFunction",
            "should_be_in_layer": 1,
            "evidence": "found via trace_callers"
        }
    ],
    "schema_gaps": [
        {
            "table": "tableName",
            "missing_service": "service-name",
            "reason": "owns table with shared payment_id column"
        }
    ],
    "config_gaps": [
        {
            "env_var": "VAR_NAME",
            "missing_service": "service-name",
            "reason": "service reads this var but report does not mention config update"
        }
    ],
    "verified_paths": number,
    "recommendation": "string"
}

RULES:
- Actually USE the tools to verify, do not just trust the report
- A report is complete when gaps, schema_gaps, and config_gaps are all empty
- Check EVERY function in Layer 0 and Layer 1
- Use get_service_http_calls() for any cross-service dependencies
- Use get_shared_table_owners() only if the report explicitly mentions DB table changes
- Use get_service_env_vars() only if the report adds or changes env vars
- If a function has no callers (entry point), that is fine
- Output ONLY the JSON"""


class VerificationAgent(BaseADKAgent):
    """
    Verifies impact analysis completeness using ADK.
    """
    
    name = "verification_agent"
    instruction = INSTRUCTION
    
    def __init__(self, graph_tools=None):
        super().__init__()
        global _graph_tools
        _graph_tools = graph_tools
    
    def _get_tools(self) -> list:
        return [
            trace_callers,
            trace_callees,
            search_symbol,
            get_symbol_context,
            get_service_http_calls,
            get_shared_table_owners,
            get_service_env_vars,
        ]
    
    async def process(self, input_data: dict) -> dict:
        """
        Verify the report.
        
        Args:
            input_data: {"report": str, "symbols": list}
        """
        report = input_data.get("report", "")
        symbols = input_data.get("symbols", [])
        return await self.verify(report, symbols)
    
    async def verify(self, report: str, symbols: list[dict], pipeline_id: str = "") -> dict:
        """
        Verify the impact report is complete.
        """
        symbols_text = "\n".join([
            f"  - Layer {s.get('layer', 0)}: {s.get('service', '?')}.{s.get('symbol', '?')}"
            for s in symbols[:20]
        ])
        
        prompt = f"""Verify this impact analysis report is complete.

REPORT:
{report[:4000]}

SYMBOLS IN REPORT:
{symbols_text}

VERIFICATION STEPS:
1. For each Layer 0 symbol, call trace_callers(symbol, 2) to find all callers
2. Check if those callers are in Layer 1
3. For each Layer 1 symbol, find their callers
4. Check if those are in Layer 2

Report any gaps as JSON."""

        # HARNESS ITEM 5: Verify that the agent actually called trace_callers/trace_callees
        # Reset receipts before this run, check after
        _reset_verification_receipts()
        response = await self.run(prompt, pipeline_id=pipeline_id)
        result = self.parse_json(response)

        trace_receipts = [r for r in _verification_receipts
                          if r["tool"] in ("trace_callers", "trace_callees")]

        if len(symbols) > 0 and len(trace_receipts) == 0:
            # Agent claimed to verify without using any tools — override
            _log.warning("[VERIFICATION] [HARNESS ITEM 5] VerificationAgent returned verdict without tool calls — overriding to LOW confidence")
            return {
                "complete": False,
                "confidence": "LOW",
                "gaps": [{
                    "missing_caller": "UNKNOWN",
                    "missing_caller_service": "UNKNOWN",
                    "should_call": "UNKNOWN",
                    "should_be_in_layer": 1,
                    "evidence": "harness_receipt_check: verification agent made no tool calls",
                }],
                "schema_gaps": [],
                "config_gaps": [],
                "verified_paths": 0,
                "recommendation": (
                    "Verification agent did not use trace_callers or trace_callees. "
                    "This means the verification is self-assessed, not graph-verified. "
                    "Re-running verification."
                ),
            }

        _log.info(f"[VERIFICATION] [HARNESS ITEM 5] Verification receipts: {len(trace_receipts)} trace calls confirmed")

        return {
            "complete": result.get("complete", False),
            "confidence": result.get("confidence", "LOW"),
            "gaps": result.get("gaps", []),
            "schema_gaps": result.get("schema_gaps", []),
            "config_gaps": result.get("config_gaps", []),
            "verified_paths": result.get("verified_paths", 0),
            "recommendation": result.get("recommendation", ""),
        }
    
    async def extract_symbols(self, report: str) -> list[dict]:
        """Extract symbols from report text."""
        prompt = f"""Extract all changed symbols from this report.

REPORT:
{report[:4000]}

Return JSON array:
[{{"service": "name", "symbol": "functionName", "layer": 0, "file": "path"}}]"""

        response = await self.run(prompt)
        result = self.parse_json(response)
        
        if isinstance(result, list):
            return result
        return result.get("symbols", [])
    
    def has_gaps(self, result: dict) -> bool:
        return len(result.get("gaps", [])) > 0
    
    def format_gaps(self, result: dict) -> str:
        """Format gaps for re-analysis."""
        gaps = result.get("gaps", [])
        if not gaps:
            return ""
        
        lines = ["Gaps found:\n"]
        for g in gaps:
            lines.append(
                f"- {g.get('missing_caller_service', '?')}.{g.get('missing_caller', '?')} "
                f"calls {g.get('should_call', '?')} but missing from Layer {g.get('should_be_in_layer', '?')}"
            )
        return "\n".join(lines)
