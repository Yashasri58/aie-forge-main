"""
Implementation Agent.

The "Hands" of code generation. Receives a task file and produces a diff.
Simple, focused, follows the plan exactly.

Uses Gemini model selection based on task complexity:
- Simple changes → gemini-2.5-flash-lite
- Standard changes → gemini-2.5-flash
- Complex changes → gemini-2.5-pro
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
            return {"error": f"File not found: {file_path}", "tip": "This may be a CREATE task — file does not exist yet"}
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
    - Simple: single change, no contracts → flash-lite
    - Medium: standard changes → flash  
    - Complex: many changes, contracts → pro
    
    Usage:
        agent = ImplementationAgent()
        output = await agent.implement(task_file)
    """
    
    def __init__(self, services_path: str = None):
        """Initialize the agent."""
        global _services_path
        if services_path:
            _services_path = Path(services_path)
        self._session_service = InMemorySessionService()
        self._sessions: dict[str, tuple] = {}  # task_id -> (session, runner, agent)
    
    def _assess_complexity(self, task_file: TaskFile) -> TaskComplexity:
        """
        Assess task complexity for model selection.
        
        Simple:
        - Single change
        - No contracts needed
        - Small file
        
        Medium:
        - Multiple changes in same file
        - Uses some contracts
        - Standard refactoring
        
        Complex:
        - Uses many contracts
        - Large file modifications
        - Architecture-level changes
        """
        num_changes = len(task_file.changes)
        num_contracts = len(task_file.uses_contracts) if task_file.uses_contracts else 0
        content_size = len(task_file.current_content) if task_file.current_content else 0
        
        # Simple tasks
        if num_changes == 1 and num_contracts == 0 and content_size < 2000:
            return TaskComplexity.SIMPLE
        
        # Complex tasks
        if num_changes > 5 or num_contracts > 3 or content_size > 10000:
            return TaskComplexity.COMPLEX
        
        # Default to medium
        return TaskComplexity.MEDIUM
    
    def _create_agent(self, model: str) -> Agent:
        """Create ADK agent with specified model."""
        return Agent(
            model=model,
            name="forge_implementation_agent",
            instruction=IMPLEMENTATION_AGENT_SYSTEM_PROMPT,
            description="Implements code changes from task files",
            tools=[read_current_file],
        )
    
    async def _get_session(self, task_id: str, model: str) -> tuple:
        """Get or create a session for a task with the appropriate model."""
        cache_key = f"{task_id}_{model}"
        
        if cache_key not in self._sessions:
            agent = self._create_agent(model)
            session = await self._session_service.create_session(
                app_name=f"forge_impl_{task_id}",
                user_id="developer"
            )
            runner = Runner(
                agent=agent,
                app_name=f"forge_impl_{task_id}",
                session_service=self._session_service
            )
            self._sessions[cache_key] = (session, runner, agent)
        
        return self._sessions[cache_key]
    
    async def implement(self, task_file: TaskFile) -> AgentOutput:
        """
        Implement a task and return a diff.
        
        Args:
            task_file: The task to implement
            
        Returns:
            AgentOutput with the diff
        """
        start_time = time.time()
        
        # Assess complexity and select model
        complexity = self._assess_complexity(task_file)
        model = select_model(task_type="diff_generation", tier=complexity)
        
        log_task_start(logger, task_file.task_id, task_file.file, str(task_file.action))
        logger.info(f"   └─ Complexity: {complexity.value}, Model: {model}")
        
        # Get session with appropriate model
        logger.debug(f"   └─ Creating session for {task_file.task_id}")
        session, runner, _ = await self._get_session(task_file.task_id, model)
        
        # Build the prompt
        prompt = self._build_prompt(task_file)
        logger.debug(f"   └─ Prompt length: {len(prompt)} chars")
        log_llm_call(logger, model, prompt[:100])
        
        # Query the agent
        content = types.Content(
            role='user',
            parts=[types.Part(text=prompt)]
        )
        
        response_text = ""
        tool_call_count = 0
        try:
            logger.info(f"   └─ Calling LLM ({model}), prompt={len(prompt)} chars...")
            async for event in runner.run_async(
                user_id="developer",
                session_id=session.id,
                new_message=content
            ):
                if hasattr(event, 'tool_calls') and event.tool_calls:
                    for tc in event.tool_calls:
                        tool_call_count += 1
                        logger.info(f"   └─ TOOL #{tool_call_count}: {tc.name}({json.dumps(tc.args or {}, default=str)[:120]})")
                if hasattr(event, 'tool_results') and event.tool_results:
                    for tr in event.tool_results:
                        name = tr.name if hasattr(tr, 'name') else 'unknown'
                        result_preview = str(tr.result)[:120] if hasattr(tr, 'result') else str(tr)[:120]
                        logger.debug(f"   └─ TOOL RESULT: {name} → {result_preview}")
                if event.is_final_response() and event.content and event.content.parts:
                    for part in event.content.parts:
                        if part.text:
                            response_text += part.text
            
            # Extract diff from response
            diff = self._extract_diff(response_text, task_file)
            
            duration_ms = int((time.time() - start_time) * 1000)
            log_task_complete(logger, task_file.task_id, "success", duration_ms)
            logger.info(f"   └─ LLM done: {tool_call_count} tool calls, response={len(response_text)} chars, diff={len(diff)} chars")
            
            return AgentOutput(
                task_id=task_file.task_id,
                file=task_file.file,
                diff=diff,
                status="success",
                metadata={"model": model, "complexity": complexity.value}
            )
            
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            log_task_complete(logger, task_file.task_id, f"error: {e}", duration_ms)
            logger.error(f"   └─ Exception: {e}", exc_info=True)
            return AgentOutput(
                task_id=task_file.task_id,
                file=task_file.file,
                diff="",
                status="error",
                error_message=str(e),
            )
    
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
        # Try to find diff block
        diff_patterns = [
            r'```diff\s*([\s\S]*?)\s*```',
            r'```\s*([\s\S]*?)\s*```',
        ]
        
        for pattern in diff_patterns:
            match = re.search(pattern, response)
            if match:
                diff = match.group(1).strip()
                if diff.startswith('---') or diff.startswith('diff'):
                    return diff
        
        # If response looks like a diff already
        if response.strip().startswith('---') or response.strip().startswith('diff'):
            return response.strip()
        
        # For CREATE actions, generate diff from content
        if task_file.action == TaskAction.CREATE:
            # Try to extract code block
            code_match = re.search(r'```\w*\s*([\s\S]*?)\s*```', response)
            if code_match:
                content = code_match.group(1)
                return self._content_to_diff(task_file.file, content)
        
        # Return empty diff if nothing found
        return ""
    
    def _content_to_diff(self, file_path: str, content: str) -> str:
        """Convert file content to a unified diff (for CREATE actions)."""
        lines = content.splitlines()
        diff_lines = [
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
        """
        Fix a diff based on verification errors.
        
        Args:
            task_file: The original task
            previous_diff: The diff that had errors
            errors: List of error messages or structured feedback dicts
            
        Returns:
            Fixed AgentOutput
        """
        # Use balanced model for fixes - needs context awareness
        model = select_model(tier=TaskComplexity.MEDIUM)
        session, runner, _ = await self._get_session(f"{task_file.task_id}_fix", model)
        
        # Format errors - handle both string and dict formats
        error_lines = []
        for e in errors:
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
                error_lines.append(line)
            else:
                # Plain string error
                error_lines.append(f"- {e}")
        
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
        
        content = types.Content(
            role='user',
            parts=[types.Part(text=prompt)]
        )
        
        response_text = ""
        try:
            async for event in runner.run_async(
                user_id="developer",
                session_id=session.id,
                new_message=content
            ):
                if event.is_final_response() and event.content and event.content.parts:
                    for part in event.content.parts:
                        if part.text:
                            response_text += part.text
            
            diff = self._extract_diff(response_text, task_file)
            
            return AgentOutput(
                task_id=task_file.task_id,
                file=task_file.file,
                diff=diff,
                status="success",
            )
            
        except Exception as e:
            logger.error(f"   └─ fix_diff FAILED for {task_file.task_id}: {e}", exc_info=True)
            # Return as error status — orchestrator's stale-error detection will
            # catch that this issue repeats and stop retrying
            return AgentOutput(
                task_id=task_file.task_id,
                file=task_file.file,
                diff=previous_diff,  # Return original so harness can re-check it
                status="error",
                error_message=f"Fix failed: {e}",
            )
