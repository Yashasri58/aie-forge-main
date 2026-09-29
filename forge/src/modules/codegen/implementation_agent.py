"""
Implementation Agent.

The "Hands" of code generation. Receives a task file and produces a diff.
Simple, focused, follows the plan exactly.

Uses Gemini model selection based on task complexity:
- Simple changes â†’ gemini-2.5-flash-lite
- Standard changes â†’ gemini-2.5-flash
- Complex changes â†’ gemini-3.1-pro-preview-customtools
"""

import json
import re
import time
from pathlib import Path
from typing import Optional

from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from .schemas import TaskFile, AgentOutput, TaskAction
from .prompts import IMPLEMENTATION_AGENT_SYSTEM_PROMPT
from .llm_router import select_model, TaskComplexity
from .logging_config import (
    impl_logger as logger,
    log_task_start,
    log_task_complete,
    log_llm_call,
)


# =============================================================================
# MODULE-LEVEL TOOL (for ADK)
# =============================================================================

_services_path: Optional[Path] = None


def read_current_file(file_path: str) -> dict:
    """
    Read the current live content of a file before implementing changes.

    Use this when current_content in the task spec may be stale or incomplete.
    Always prefer the live file over the spec when generating diffs.

    Args:
        file_path: Relative path from services directory

    Returns:
        {content, lines, size} or {error}
    """
    if not _services_path:
        return {"error": "Services path not configured"}
    try:
        full_path = _services_path / file_path
        # Security: stay within services directory
        full_path.resolve().relative_to(_services_path.resolve())
        if not full_path.exists():
            return {"error": f"File not found: {file_path}", "tip": "This may be a CREATE task â€” file does not exist yet"}
        content = full_path.read_text(encoding="utf-8", errors="replace")
        return {
            "path": file_path,
            "content": content,
            "lines": len(content.splitlines()),
            "size": len(content),
        }
    except ValueError:
        return {"error": f"Path {file_path} is outside services directory"}
    except Exception as e:
        return {"error": str(e)}


# =============================================================================
# IMPLEMENTATION AGENT
# =============================================================================

class ImplementationAgent:
    """
    Implementation Agent - produces diffs from task files.
    
    Dynamically selects Gemini model based on task complexity:
    - Simple: single change, no contracts â†’ flash-lite
    - Medium: standard changes â†’ flash  
    - Complex: many changes, contracts â†’ pro
    
    Usage:
        agent = ImplementationAgent()
        output = await agent.implement(task_file)
    """
    
    def __init__(self, services_path: str = None):
        """Initialize the agent."""
        logger.info(f"[IMPL_INIT] ImplementationAgent.__init__() services_path={services_path}")
        global _services_path
        if services_path:
            _services_path = Path(services_path)
            logger.info(f"[IMPL_INIT] _services_path set to {_services_path}")
        else:
            logger.info(f"[IMPL_INIT] services_path not provided, _services_path unchanged={_services_path}")
        self._session_service = InMemorySessionService()
        logger.info(f"[IMPL_INIT] InMemorySessionService created")
        self._sessions: dict[str, tuple] = {}  # task_id -> (session, runner, agent)
        logger.info(f"[IMPL_INIT] _sessions dict initialized empty")
    
    def _assess_complexity(self, task_file: TaskFile) -> TaskComplexity:
        """Assess task complexity for model selection."""
        num_changes = len(task_file.changes)
        num_contracts = len(task_file.uses_contracts) if task_file.uses_contracts else 0
        content_size = len(task_file.current_content) if task_file.current_content else 0
        logger.info(f"[COMPLEXITY] task={task_file.task_id} num_changes={num_changes} num_contracts={num_contracts} content_size={content_size}")
        
        # Simple tasks
        if num_changes == 1 and num_contracts == 0 and content_size < 2000:
            logger.info(f"[COMPLEXITY] â†’ SIMPLE")
            return TaskComplexity.SIMPLE
        
        # Complex tasks
        if num_changes > 5 or num_contracts > 3 or content_size > 10000:
            logger.info(f"[COMPLEXITY] â†’ COMPLEX")
            return TaskComplexity.COMPLEX
        
        # Default to medium
        logger.info(f"[COMPLEXITY] â†’ MEDIUM (default)")
        return TaskComplexity.MEDIUM
    
    def _create_agent(self, model: str) -> Agent:
        """Create ADK agent with specified model."""
        logger.info(f"[CREATE_AGENT] creating Agent with model={model}")
        from modules.llm_registry import get_adk_model
        agent = Agent(
            model=get_adk_model(model),
            name="forge_implementation_agent",
            instruction=IMPLEMENTATION_AGENT_SYSTEM_PROMPT,
            description="Implements code changes from task files",
            tools=[read_current_file],
        )
        logger.info(f"[CREATE_AGENT] Agent created: name={agent.name}")
        return agent
    
    async def _get_session(self, task_id: str, model: str) -> tuple:
        """Get or create a session for a task with the appropriate model."""
        cache_key = f"{task_id}_{model}"
        logger.info(f"[GET_SESSION] cache_key={cache_key} already_cached={cache_key in self._sessions}")
        
        if cache_key not in self._sessions:
            logger.info(f"[GET_SESSION] cache miss â€” creating new agent+session for {cache_key}")
            agent = self._create_agent(model)
            logger.info(f"[GET_SESSION] calling session_service.create_session()")
            session = await self._session_service.create_session(
                app_name=f"forge_impl_{task_id}",
                user_id="developer"
            )
            logger.info(f"[GET_SESSION] session created: id={session.id}")
            logger.info(f"[GET_SESSION] creating Runner")
            runner = Runner(
                agent=agent,
                app_name=f"forge_impl_{task_id}",
                session_service=self._session_service
            )
            logger.info(f"[GET_SESSION] Runner created")
            self._sessions[cache_key] = (session, runner, agent)
            logger.info(f"[GET_SESSION] cached under key={cache_key} total_cached={len(self._sessions)}")
        else:
            logger.info(f"[GET_SESSION] cache hit for {cache_key}")
        
        return self._sessions[cache_key]
    
    async def implement(self, task_file: TaskFile, pipeline_id: str = "") -> AgentOutput:
        """
        Implement a task and return a diff.
        """
        logger.info(f"[IMPL] â–¶ï¸  implement() START: task_id={task_file.task_id} file={task_file.file} action={task_file.action} pipeline_id={pipeline_id}")
        start_time = time.time()
        logger.info(f"[IMPL] start_time={start_time}")
        
        # Assess complexity and select model
        logger.info(f"[IMPL] calling _assess_complexity()")
        complexity = self._assess_complexity(task_file)
        logger.info(f"[IMPL] complexity={complexity.value} num_changes={len(task_file.changes)} num_contracts={len(task_file.uses_contracts) if task_file.uses_contracts else 0} content_size={len(task_file.current_content) if task_file.current_content else 0}")
        logger.info(f"[IMPL] calling select_model(task_type='diff_generation', tier={complexity})")
        model = select_model(task_type="diff_generation", tier=complexity)
        logger.info(f"[IMPL] model selected={model}")
        
        log_task_start(logger, task_file.task_id, task_file.file, str(task_file.action))
        logger.info(f"   â””â”€ Complexity: {complexity.value}, Model: {model}")
        
        # Get session with appropriate model
        logger.info(f"[IMPL] calling _get_session(task_id={task_file.task_id}, model={model})")
        logger.debug(f"   â””â”€ Creating session for {task_file.task_id}")
        session, runner, _ = await self._get_session(task_file.task_id, model)
        logger.info(f"[IMPL] session obtained: session.id={session.id}")
        
        # Build the prompt
        logger.info(f"[IMPL] calling _build_prompt()")
        prompt = self._build_prompt(task_file)
        logger.info(f"[IMPL] prompt built: {len(prompt)} chars")
        logger.debug(f"   â””â”€ Prompt length: {len(prompt)} chars")
        log_llm_call(logger, model, prompt[:100])
        
        # Query the agent
        logger.info(f"[IMPL] building types.Content with prompt")
        content = types.Content(
            role='user',
            parts=[types.Part(text=prompt)]
        )
        logger.info(f"[IMPL] types.Content created")
        
        response_text = ""
        logger.info(f"[IMPL] response_text initialized empty")
        tool_call_count = 0
        logger.info(f"[IMPL] tool_call_count=0")
        _tok_in = _tok_out = _tok_think = 0
        logger.info(f"[IMPL] token counters initialized: in=0 out=0 think=0")
        try:
            logger.info(f"[IMPL] entering runner.run_async() loop")
            logger.info(f"   â””â”€ Calling LLM ({model}), prompt={len(prompt)} chars...")
            event_count = 0
            async for event in runner.run_async(
                user_id="developer",
                session_id=session.id,
                new_message=content
            ):
                event_count += 1
                logger.info(f"[IMPL] event #{event_count}: type={type(event).__name__} is_final={event.is_final_response() if hasattr(event,'is_final_response') else 'n/a'}")
                _m = getattr(event, "usage_metadata", None)
                if _m:
                    logger.info(f"[IMPL] usage_metadata found on event #{event_count}")
                    _tok_in    = max(_tok_in,    getattr(_m, "prompt_token_count",     0) or 0)
                    _tok_out   = max(_tok_out,   getattr(_m, "candidates_token_count", 0) or 0)
                    _tok_think = max(_tok_think, getattr(_m, "thoughts_token_count",   0) or 0)
                    logger.info(f"[IMPL] tokens so far: in={_tok_in} out={_tok_out} think={_tok_think}")
                if hasattr(event, 'tool_calls') and event.tool_calls:
                    for tc in event.tool_calls:
                        tool_call_count += 1
                        logger.info(f"[IMPL] TOOL CALL #{tool_call_count}: name={tc.name} args={json.dumps(tc.args or {}, default=str)[:200]}")
                        logger.info(f"   â””â”€ TOOL #{tool_call_count}: {tc.name}({json.dumps(tc.args or {}, default=str)[:120]})")
                if hasattr(event, 'tool_results') and event.tool_results:
                    for tr in event.tool_results:
                        name = tr.name if hasattr(tr, 'name') else 'unknown'
                        result_preview = str(tr.result)[:200] if hasattr(tr, 'result') else str(tr)[:200]
                        logger.info(f"[IMPL] TOOL RESULT: name={name} result_preview={result_preview}")
                        logger.debug(f"   â””â”€ TOOL RESULT: {name} â†’ {result_preview}")
                if event.is_final_response() and event.content and event.content.parts:
                    logger.info(f"[IMPL] final response event: parts={len(event.content.parts)}")
                    for pi, part in enumerate(event.content.parts):
                        logger.info(f"[IMPL] part[{pi}]: has_text={bool(part.text)} len={len(part.text) if part.text else 0}")
                        if part.text:
                            response_text += part.text
                            logger.info(f"[IMPL] response_text accumulated: {len(response_text)} chars total")

            logger.info(f"[IMPL] runner.run_async() loop done: event_count={event_count} tool_calls={tool_call_count} response_text_len={len(response_text)}")

            if pipeline_id and (_tok_in or _tok_out):
                logger.info(f"[IMPL] recording tokens: pipeline_id={pipeline_id} in={_tok_in} out={_tok_out} think={_tok_think}")
                try:
                    from modules.cache.token_tracker import get_tracker
                    get_tracker().record(pipeline_id=pipeline_id, model=model,
                        input_tokens=_tok_in, output_tokens=_tok_out,
                        reasoning_tokens=_tok_think, call_label=f"ImplAgent.{task_file.task_id}")
                    logger.info(f"[IMPL] token tracking recorded")
                except Exception as te:
                    logger.warning(f"[IMPL] token tracking failed (non-fatal): {te}")
            else:
                logger.info(f"[IMPL] skipping token tracking: pipeline_id={bool(pipeline_id)} has_tokens={bool(_tok_in or _tok_out)}")

            # Extract diff from response
            logger.info(f"[IMPL] calling _extract_diff()")
            diff = self._extract_diff(response_text, task_file)
            logger.info(f"[IMPL] diff extracted: {len(diff)} chars, first_line='{diff.splitlines()[0] if diff else 'EMPTY'}'")
            
            duration_ms = int((time.time() - start_time) * 1000)
            logger.info(f"[IMPL] duration={duration_ms}ms")
            log_task_complete(logger, task_file.task_id, "success", duration_ms)
            logger.info(f"   â””â”€ LLM done: {tool_call_count} tool calls, response={len(response_text)} chars, diff={len(diff)} chars")
            
            logger.info(f"[IMPL] building AgentOutput: task_id={task_file.task_id} file={task_file.file} status=success")
            output = AgentOutput(
                task_id=task_file.task_id,
                file=task_file.file,
                diff=diff,
                status="success",
                metadata={"model": model, "complexity": complexity.value}
            )
            logger.info(f"[IMPL] âœ… implement() returning SUCCESS: diff_len={len(diff)}")
            return output
            
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(f"[IMPL] âŒ EXCEPTION in implement(): {type(e).__name__}: {e}", exc_info=True)
            logger.info(f"[IMPL] duration at exception: {duration_ms}ms")
            log_task_complete(logger, task_file.task_id, f"error: {e}", duration_ms)
            logger.error(f"   â””â”€ Exception: {e}", exc_info=True)
            logger.info(f"[IMPL] building error AgentOutput")
            output = AgentOutput(
                task_id=task_file.task_id,
                file=task_file.file,
                diff="",
                status="error",
                error_message=str(e),
            )
            logger.info(f"[IMPL] âŒ implement() returning ERROR: {str(e)}")
            return output
    
    def _build_prompt(self, task_file: TaskFile) -> str:
        """Build the prompt for the implementation agent."""
        # Format contracts
        contracts_text = ""
        if task_file.contracts:
            contracts_text = "## CONTRACTS (use exactly as specified)\n\n"
            for name, contract in task_file.contracts.items():
                contracts_text += f"### {name}\n"
                contracts_text += f"Signature: `{contract.get('signature', '')}`\n"
                if contract.get('implementation'):
                    contracts_text += f"Implementation:\n```\n{contract['implementation']}\n```\n"
                if contract.get('usage_example'):
                    contracts_text += f"Usage: `{contract['usage_example']}`\n"
                contracts_text += "\n"
        
        # Format changes
        changes_text = "## CHANGES TO MAKE\n\n"
        for i, change in enumerate(task_file.changes, 1):
            change_dict = change.to_dict() if hasattr(change, 'to_dict') else change
            changes_text += f"### Change {i}\n"
            changes_text += f"Location: {change_dict['location']}\n"
            changes_text += f"Type: {change_dict['change_type']}\n"
            changes_text += f"Description: {change_dict['description']}\n"
            if change_dict.get('before'):
                changes_text += f"Before:\n```\n{change_dict['before']}\n```\n"
            if change_dict.get('after'):
                changes_text += f"After:\n```\n{change_dict['after']}\n```\n"
            changes_text += "\n"
        
        # Format design decisions
        decisions_text = ""
        if task_file.design_decisions:
            decisions_text = "## DESIGN DECISIONS (follow these rules)\n\n"
            for decision in task_file.design_decisions:
                decisions_text += f"- {decision}\n"
            decisions_text += "\n"
        
        # Format conventions
        conventions_text = ""
        if task_file.conventions:
            conventions_text = "## CONVENTIONS\n\n"
            for key, value in task_file.conventions.items():
                conventions_text += f"- {key}: {value}\n"
            conventions_text += "\n"
        
        # Build the full prompt
        prompt = f"""Implement the following task and return a unified diff.

## TASK
- Task ID: {task_file.task_id}
- File: {task_file.file}
- Language: {task_file.language}
- Action: {task_file.action.value if isinstance(task_file.action, TaskAction) else task_file.action}

{contracts_text}
{changes_text}
{decisions_text}
{conventions_text}
"""
        
        # Add current content for modify/delete
        if task_file.current_content and task_file.action != TaskAction.CREATE:
            prompt += f"""## CURRENT FILE CONTENT
```{task_file.language}
{task_file.current_content}
```

"""
        
        prompt += """## OUTPUT
Return ONLY a unified diff. No explanation.

For MODIFY:
```diff
--- a/{file}
+++ b/{file}
@@ -start,count +start,count @@
 context
-old line
+new line
 context
```

For CREATE:
```diff
diff --git a/{file} b/{file}
new file mode 100644
--- /dev/null
+++ b/{file}
@@ -0,0 +1,N @@
+line 1
+line 2
```
"""
        
        return prompt
    
    def _extract_diff(self, response: str, task_file: TaskFile) -> str:
        """Extract the diff from the agent's response."""
        logger.info(f"[EXTRACT_DIFF] task={task_file.task_id} response_len={len(response)} action={task_file.action}")
        logger.info(f"[EXTRACT_DIFF] response preview: {response[:200]!r}")
        
        # Try to find diff block
        diff_patterns = [
            r'```diff\s*([\s\S]*?)\s*```',
            r'```\s*([\s\S]*?)\s*```',
        ]
        
        for pi, pattern in enumerate(diff_patterns):
            logger.info(f"[EXTRACT_DIFF] trying pattern[{pi}]: {pattern[:40]}")
            match = re.search(pattern, response)
            if match:
                diff = match.group(1).strip()
                logger.info(f"[EXTRACT_DIFF] pattern[{pi}] matched: diff_len={len(diff)} starts_with='{diff[:30]}'")
                if diff.startswith('---') or diff.startswith('diff'):
                    logger.info(f"[EXTRACT_DIFF] valid diff header found via pattern[{pi}] â€” returning")
                    return diff
                else:
                    logger.info(f"[EXTRACT_DIFF] pattern[{pi}] matched but not a diff header â€” continuing")
            else:
                logger.info(f"[EXTRACT_DIFF] pattern[{pi}] no match")
        
        # If response looks like a diff already
        logger.info(f"[EXTRACT_DIFF] checking if response itself is a diff")
        if response.strip().startswith('---') or response.strip().startswith('diff'):
            logger.info(f"[EXTRACT_DIFF] response IS a raw diff â€” returning directly, len={len(response.strip())}")
            return response.strip()
        logger.info(f"[EXTRACT_DIFF] response is NOT a raw diff")
        
        # For CREATE actions, generate diff from content
        logger.info(f"[EXTRACT_DIFF] action={task_file.action} checking CREATE fallback")
        if task_file.action == TaskAction.CREATE:
            logger.info(f"[EXTRACT_DIFF] CREATE action â€” trying code block extraction")
            # Try to extract code block
            code_match = re.search(r'```\w*\s*([\s\S]*?)\s*```', response)
            if code_match:
                content = code_match.group(1)
                logger.info(f"[EXTRACT_DIFF] code block found for CREATE: {len(content)} chars â€” converting to diff")
                return self._content_to_diff(task_file.file, content)
            else:
                logger.info(f"[EXTRACT_DIFF] no code block found for CREATE action")
        
        # Return empty diff if nothing found
        logger.warning(f"[EXTRACT_DIFF] âš ï¸ could not extract diff â€” returning EMPTY for task={task_file.task_id}")
        return ""
    
    def _content_to_diff(self, file_path: str, content: str) -> str:
        """Convert file content to a unified diff (for CREATE actions)."""
        lines = content.splitlines()
        diff_lines = [
            f"diff --git a/{file_path} b/{file_path}",
            f"new file mode 100644",
            f"--- /dev/null",
            f"+++ b/{file_path}",
            f"@@ -0,0 +1,{len(lines)} @@",
        ]
        for line in lines:
            diff_lines.append(f"+{line}")
        return "\n".join(diff_lines)
    
    async def fix_diff(
        self, 
        task_file: TaskFile, 
        previous_diff: str, 
        errors: list[dict | str]
    ) -> AgentOutput:
        """Fix a diff based on verification errors."""
        logger.info(f"[FIX_DIFF] â–¶ï¸  fix_diff() START: task_id={task_file.task_id} file={task_file.file} previous_diff_len={len(previous_diff)} errors={len(errors)}")
        for i, e in enumerate(errors):
            logger.info(f"[FIX_DIFF]   error[{i}]: {e}")

        # Use balanced model for fixes - needs context awareness
        logger.info(f"[FIX_DIFF] selecting model: TaskComplexity.MEDIUM")
        model = select_model(tier=TaskComplexity.MEDIUM)
        logger.info(f"[FIX_DIFF] model={model}")
        logger.info(f"[FIX_DIFF] calling _get_session(task_id={task_file.task_id}_fix, model={model})")
        session, runner, _ = await self._get_session(f"{task_file.task_id}_fix", model)
        logger.info(f"[FIX_DIFF] session obtained: session.id={session.id}")
        
        # Format errors - handle both string and dict formats
        error_lines = []
        logger.info(f"[FIX_DIFF] formatting {len(errors)} errors")
        for ei, e in enumerate(errors):
            logger.info(f"[FIX_DIFF]   formatting error[{ei}]: type={type(e).__name__}")
            if isinstance(e, dict):
                # Structured feedback from Verifier Agent
                line = f"- [{e.get('category', 'error')}] {e.get('issue', 'Unknown error')}"
                if e.get('expected'):
                    line += f"\n  Expected: {e['expected']}"
                if e.get('actual'):
                    line += f"\n  Actual: {e['actual']}"
                if e.get('fix_instruction'):
                    line += f"\n  FIX: {e['fix_instruction']}"
                elif e.get('suggestion'):
                    line += f"\n  Suggestion: {e['suggestion']}"
                if e.get('line'):
                    line += f"\n  Line: {e['line']}"
                logger.info(f"[FIX_DIFF]   formatted dict error: {line[:150]}")
                error_lines.append(line)
            else:
                # Plain string error
                logger.info(f"[FIX_DIFF]   plain string error: {str(e)[:150]}")
                error_lines.append(f"- {e}")
        logger.info(f"[FIX_DIFF] error_lines assembled: {len(error_lines)} lines")
        
        logger.info(f"[FIX_DIFF] building fix prompt")
        prompt = f"""Fix the errors in this diff.

## TASK SPECIFICATION
{json.dumps(task_file.to_dict(), indent=2)}

## PREVIOUS DIFF (has errors)
```diff
{previous_diff}
```

## VERIFICATION ERRORS
{chr(10).join(error_lines)}

## INSTRUCTIONS
1. Fix EACH error listed above
2. Follow the fix instructions exactly if provided
3. Ensure the diff targets the correct file: {task_file.file}
4. Match all contract signatures exactly
5. Keep the rest of the diff unchanged

Return ONLY the corrected unified diff, no explanation.
"""
        logger.info(f"[FIX_DIFF] prompt built: {len(prompt)} chars")
        
        logger.info(f"[FIX_DIFF] building types.Content")
        content = types.Content(
            role='user',
            parts=[types.Part(text=prompt)]
        )
        logger.info(f"[FIX_DIFF] types.Content created")
        
        response_text = ""
        logger.info(f"[FIX_DIFF] response_text initialized empty")
        try:
            logger.info(f"[FIX_DIFF] entering runner.run_async() loop")
            event_count = 0
            async for event in runner.run_async(
                user_id="developer",
                session_id=session.id,
                new_message=content
            ):
                event_count += 1
                logger.info(f"[FIX_DIFF] event #{event_count}: type={type(event).__name__} is_final={event.is_final_response() if hasattr(event,'is_final_response') else 'n/a'}")
                if event.is_final_response() and event.content and event.content.parts:
                    logger.info(f"[FIX_DIFF] final response event: parts={len(event.content.parts)}")
                    for pi, part in enumerate(event.content.parts):
                        logger.info(f"[FIX_DIFF] part[{pi}]: has_text={bool(part.text)} len={len(part.text) if part.text else 0}")
                        if part.text:
                            response_text += part.text
                            logger.info(f"[FIX_DIFF] response_text now {len(response_text)} chars")
            logger.info(f"[FIX_DIFF] runner loop done: event_count={event_count} response_text_len={len(response_text)}")
            
            logger.info(f"[FIX_DIFF] calling _extract_diff()")
            diff = self._extract_diff(response_text, task_file)
            logger.info(f"[FIX_DIFF] diff extracted: {len(diff)} chars first_line='{diff.splitlines()[0] if diff else 'EMPTY'}'")
            
            logger.info(f"[FIX_DIFF] building success AgentOutput")
            output = AgentOutput(
                task_id=task_file.task_id,
                file=task_file.file,
                diff=diff,
                status="success",
            )
            logger.info(f"[FIX_DIFF] âœ… fix_diff() returning SUCCESS diff_len={len(diff)}")
            return output
            
        except Exception as e:
            logger.error(f"[FIX_DIFF] âŒ EXCEPTION: {type(e).__name__}: {e}", exc_info=True)
            logger.error(f"   â””â”€ fix_diff FAILED for {task_file.task_id}: {e}", exc_info=True)
            logger.info(f"[FIX_DIFF] returning original previous_diff as fallback, len={len(previous_diff)}")
            # Return as error status â€” orchestrator's stale-error detection will
            # catch that this issue repeats and stop retrying
            output = AgentOutput(
                task_id=task_file.task_id,
                file=task_file.file,
                diff=previous_diff,  # Return original so harness can re-check it
                status="error",
                error_message=f"Fix failed: {e}",
            )
            logger.info(f"[FIX_DIFF] âŒ fix_diff() returning ERROR: {str(e)}")
            return output
