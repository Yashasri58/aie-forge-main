"""
Coordinator Agent.

An intelligent agent that validates plans and prepares task files.
Has deterministic tools to inspect the codebase and validate the plan.

Unlike pure Python validation, the agent can:
- Reason about edge cases
- Detect subtle issues (race conditions, import conflicts)
- Adapt to scenarios we haven't explicitly coded for
"""

import os
import re
import json
import subprocess
from pathlib import Path
from typing import Optional

from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from .schemas import (
    Plan,
    Task,
    TaskFile,
    TaskAction,
    ExecutionPhase,
)
from .prompts import COORDINATOR_AGENT_SYSTEM_PROMPT
from .llm_router import select_model, ModelTier
from .logging_config import coordinator_logger as logger


# =============================================================================
# TOOL IMPLEMENTATIONS
# =============================================================================

class CoordinatorTools:
    """Deterministic tools for the Coordinator Agent."""
    
    def __init__(self, services_path: str):
        self._services_path = Path(services_path)
    
    def check_file_exists(self, path: str) -> dict:
        """
        Check if a file exists in the services directory.
        
        Args:
            path: Relative path from services directory
            
        Returns:
            {exists, is_file, is_dir, size (if file)}
        """
        full_path = self._services_path / path
        
        if not full_path.exists():
            return {"exists": False, "is_file": False, "is_dir": False}
        
        result = {
            "exists": True,
            "is_file": full_path.is_file(),
            "is_dir": full_path.is_dir(),
        }
        
        if full_path.is_file():
            result["size"] = full_path.stat().st_size
        
        return result
    
    def check_directory_exists(self, path: str) -> dict:
        """
        Check if a directory exists and list its contents.
        
        Args:
            path: Relative path from services directory
            
        Returns:
            {exists, files, subdirs}
        """
        full_path = self._services_path / path
        
        if not full_path.exists():
            return {"exists": False}
        
        if not full_path.is_dir():
            return {"exists": True, "is_dir": False, "error": "Path is a file, not directory"}
        
        files = []
        subdirs = []
        
        for item in full_path.iterdir():
            if item.name.startswith('.') or item.name == 'node_modules':
                continue
            if item.is_file():
                files.append(item.name)
            elif item.is_dir():
                subdirs.append(item.name)
        
        return {
            "exists": True,
            "is_dir": True,
            "files": sorted(files),
            "subdirs": sorted(subdirs),
        }
    
    def parse_imports(self, file_path: str) -> dict:
        """
        Extract imports/requires from a JavaScript/TypeScript file.
        
        Args:
            file_path: Relative path to the file
            
        Returns:
            {imports: [{module, path, is_relative, line}]}
        """
        full_path = self._services_path / file_path
        
        if not full_path.exists():
            return {"error": f"File not found: {file_path}"}
        
        try:
            content = full_path.read_text(encoding='utf-8')
        except Exception as e:
            return {"error": str(e)}
        
        imports = []
        lines = content.splitlines()
        
        # Match: require('...'), require("...")
        require_pattern = re.compile(r'''require\s*\(\s*['"]([^'"]+)['"]\s*\)''')
        
        # Match: import ... from '...', import ... from "..."
        import_pattern = re.compile(r'''import\s+.*?\s+from\s+['"]([^'"]+)['"]''')
        
        # Match: import '...' (side-effect imports)
        import_side_pattern = re.compile(r'''import\s+['"]([^'"]+)['"]''')
        
        for i, line in enumerate(lines, 1):
            for pattern in [require_pattern, import_pattern, import_side_pattern]:
                for match in pattern.finditer(line):
                    module_path = match.group(1)
                    imports.append({
                        "module": module_path,
                        "path": module_path,
                        "is_relative": module_path.startswith('.'),
                        "line": i,
                    })
        
        return {"imports": imports, "count": len(imports)}
    
    def validate_json_syntax(self, content: str) -> dict:
        """
        Check if JSON content is valid.
        
        Args:
            content: JSON string to validate
            
        Returns:
            {valid, error (if invalid), parsed (if valid)}
        """
        try:
            parsed = json.loads(content)
            return {"valid": True, "parsed": parsed}
        except json.JSONDecodeError as e:
            return {"valid": False, "error": str(e), "line": e.lineno, "column": e.colno}
    
    def validate_js_syntax(self, content: str) -> dict:
        """
        Check if JavaScript syntax is valid using Node.js.
        
        Args:
            content: JavaScript code to validate
            
        Returns:
            {valid, errors (if invalid)}
        """
        import tempfile
        import os
        
        try:
            # Write to temp file - node --check requires a file, can't use -e
            with tempfile.NamedTemporaryFile(
                mode='w',
                suffix='.js',
                delete=False,
                encoding='utf-8'
            ) as f:
                f.write(content)
                temp_path = f.name
            
            try:
                result = subprocess.run(
                    ['node', '--check', temp_path],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                
                if result.returncode == 0:
                    return {"valid": True}
                else:
                    # Parse error message, remove temp file path
                    error_msg = result.stderr.strip()
                    error_msg = error_msg.replace(temp_path, '<code>')
                    return {"valid": False, "error": error_msg}
            finally:
                os.unlink(temp_path)
                
        except subprocess.TimeoutExpired:
            return {"valid": False, "error": "Syntax check timed out"}
        except FileNotFoundError:
            # Node.js not available, try basic regex check
            return self._basic_js_syntax_check(content)
    
    def _basic_js_syntax_check(self, content: str) -> dict:
        """Basic syntax check without Node.js."""
        errors = []
        
        # Check for unclosed brackets
        brackets = {'(': ')', '[': ']', '{': '}'}
        stack = []
        
        for i, char in enumerate(content):
            if char in brackets:
                stack.append((char, i))
            elif char in brackets.values():
                if not stack:
                    errors.append(f"Unexpected closing bracket '{char}' at position {i}")
                else:
                    open_bracket, _ = stack.pop()
                    if brackets[open_bracket] != char:
                        errors.append(f"Mismatched bracket '{char}' at position {i}")
        
        if stack:
            for bracket, pos in stack:
                errors.append(f"Unclosed bracket '{bracket}' at position {pos}")
        
        return {"valid": len(errors) == 0, "errors": errors}
    
    def detect_circular_deps(self, tasks: dict) -> dict:
        """
        Detect circular dependencies in task graph.
        
        Args:
            tasks: Dict of task_id -> {depends_on: [task_ids]}
            
        Returns:
            {has_cycle, cycle (if found)}
        """
        # Build adjacency list
        graph = {}
        for task_id, task_data in tasks.items():
            deps = task_data.get('depends_on', [])
            if isinstance(deps, list):
                graph[task_id] = deps
            else:
                graph[task_id] = []
        
        # DFS to find cycle
        visited = set()
        rec_stack = set()
        path = []
        
        def dfs(node: str) -> list:
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
                cycle = dfs(task_id)
                if cycle:
                    return {"has_cycle": True, "cycle": cycle}
        
        return {"has_cycle": False}
    
    def find_symbol_in_file(self, file_path: str, symbol: str) -> dict:
        """
        Check if a symbol (function, class, variable) exists in a file.
        
        Args:
            file_path: Relative path to file
            symbol: Symbol name to find
            
        Returns:
            {found, line, kind, context}
        """
        full_path = self._services_path / file_path
        
        if not full_path.exists():
            return {"found": False, "error": f"File not found: {file_path}"}
        
        try:
            content = full_path.read_text(encoding='utf-8')
        except Exception as e:
            return {"found": False, "error": str(e)}
        
        lines = content.splitlines()
        
        # Patterns for different kinds
        patterns = [
            (r'function\s+' + re.escape(symbol) + r'\s*\(', 'function'),
            (r'const\s+' + re.escape(symbol) + r'\s*=', 'const'),
            (r'let\s+' + re.escape(symbol) + r'\s*=', 'let'),
            (r'var\s+' + re.escape(symbol) + r'\s*=', 'var'),
            (r'class\s+' + re.escape(symbol) + r'\s*[{\s]', 'class'),
            (r'async\s+function\s+' + re.escape(symbol) + r'\s*\(', 'async function'),
            (re.escape(symbol) + r'\s*:\s*function', 'method'),
            (re.escape(symbol) + r'\s*\([^)]*\)\s*{', 'method'),
        ]
        
        for i, line in enumerate(lines, 1):
            for pattern, kind in patterns:
                if re.search(pattern, line):
                    return {
                        "found": True,
                        "line": i,
                        "kind": kind,
                        "context": line.strip(),
                    }
        
        # Check exports
        export_pattern = re.compile(r'module\.exports\s*=.*' + re.escape(symbol))
        export_pattern2 = re.compile(r'exports\.' + re.escape(symbol))
        
        for i, line in enumerate(lines, 1):
            if export_pattern.search(line) or export_pattern2.search(line):
                return {
                    "found": True,
                    "line": i,
                    "kind": "export",
                    "context": line.strip(),
                }
        
        return {"found": False}
    
    def get_file_exports(self, file_path: str) -> dict:
        """
        Get all exports from a JavaScript file.
        
        Args:
            file_path: Relative path to file
            
        Returns:
            {exports: [{name, kind, line}]}
        """
        full_path = self._services_path / file_path
        
        if not full_path.exists():
            return {"error": f"File not found: {file_path}"}
        
        try:
            content = full_path.read_text(encoding='utf-8')
        except Exception as e:
            return {"error": str(e)}
        
        exports = []
        lines = content.splitlines()
        
        for i, line in enumerate(lines, 1):
            # module.exports = { name1, name2 }
            match = re.search(r'module\.exports\s*=\s*\{([^}]+)\}', line)
            if match:
                names = [n.strip().split(':')[0].strip() for n in match.group(1).split(',')]
                for name in names:
                    if name:
                        exports.append({"name": name, "kind": "named", "line": i})
            
            # module.exports = functionName
            match = re.search(r'module\.exports\s*=\s*(\w+)\s*;?$', line)
            if match:
                exports.append({"name": match.group(1), "kind": "default", "line": i})
            
            # exports.name = ...
            match = re.search(r'exports\.(\w+)\s*=', line)
            if match:
                exports.append({"name": match.group(1), "kind": "named", "line": i})
            
            # export function name
            match = re.search(r'export\s+(?:async\s+)?function\s+(\w+)', line)
            if match:
                exports.append({"name": match.group(1), "kind": "function", "line": i})
            
            # export const name
            match = re.search(r'export\s+const\s+(\w+)', line)
            if match:
                exports.append({"name": match.group(1), "kind": "const", "line": i})
        
        return {"exports": exports, "count": len(exports)}
    
    def resolve_import_path(self, from_file: str, import_path: str) -> dict:
        """
        Resolve a relative import path to absolute path.
        
        Args:
            from_file: The file containing the import
            import_path: The import path (e.g., '../utils/helper')
            
        Returns:
            {resolved, exists}
        """
        if not import_path.startswith('.'):
            # Node module, not a relative import
            return {"resolved": import_path, "exists": None, "is_node_module": True}
        
        services_resolved = self._services_path.resolve()
        from_dir = (services_resolved / from_file).parent
        resolved = (from_dir / import_path).resolve()
        
        # Try with extensions
        extensions = ['', '.js', '.ts', '.jsx', '.tsx', '/index.js', '/index.ts']
        
        for ext in extensions:
            check_path = Path(str(resolved) + ext)
            if check_path.exists():
                try:
                    rel_path = check_path.relative_to(services_resolved)
                    return {"resolved": str(rel_path), "exists": True}
                except ValueError:
                    return {"resolved": str(check_path), "exists": True, "outside_services": True}
        
        try:
            rel_path = resolved.relative_to(services_resolved)
            return {"resolved": str(rel_path), "exists": False}
        except ValueError:
            return {"resolved": str(resolved), "exists": False, "outside_services": True}
    
    def analyze_phase_parallelism(self, tasks: dict, phase_tasks: list) -> dict:
        """
        Analyze if tasks in a phase can safely run in parallel.
        
        Args:
            tasks: All tasks dict
            phase_tasks: List of task IDs in this phase
            
        Returns:
            {safe, conflicts}
        """
        conflicts = []
        
        # Get files modified by each task
        task_files = {}
        for task_id in phase_tasks:
            task = tasks.get(task_id, {})
            task_files[task_id] = task.get('file', '')
        
        # Check for same file conflicts
        files_seen = {}
        for task_id, file_path in task_files.items():
            if file_path in files_seen:
                conflicts.append({
                    "task1": files_seen[file_path],
                    "task2": task_id,
                    "reason": f"Both tasks modify the same file: {file_path}",
                })
            else:
                files_seen[file_path] = task_id
        
        # Check for import/export conflicts
        # If task A creates a file that task B imports, they can't be parallel
        creates = {}
        imports_from = {}
        
        for task_id in phase_tasks:
            task = tasks.get(task_id, {})
            if task.get('action') == 'create':
                creates[task_id] = task.get('file', '')
            
            # Check if task uses contracts that another task defines
            uses = task.get('uses_contracts', [])
            defines = task.get('defines_contracts', [])
            
            for other_id in phase_tasks:
                if other_id == task_id:
                    continue
                other_task = tasks.get(other_id, {})
                other_defines = other_task.get('defines_contracts', [])
                
                # If this task uses a contract that another task defines
                for contract in uses:
                    if contract in other_defines:
                        conflicts.append({
                            "task1": other_id,
                            "task2": task_id,
                            "reason": f"Task {task_id} uses contract '{contract}' defined by {other_id}",
                        })
        
        return {
            "safe": len(conflicts) == 0,
            "conflicts": conflicts,
        }
    
    def read_file_content(self, file_path: str) -> dict:
        """
        Read file content.
        
        Args:
            file_path: Relative path to file
            
        Returns:
            {content, lines, size} or {error}
        """
        full_path = self._services_path / file_path
        
        if not full_path.exists():
            return {"error": f"File not found: {file_path}"}
        
        try:
            content = full_path.read_text(encoding='utf-8')
            return {
                "content": content,
                "lines": len(content.splitlines()),
                "size": len(content),
            }
        except Exception as e:
            return {"error": str(e)}


# =============================================================================
# MODULE-LEVEL TOOL FUNCTIONS (for ADK)
# =============================================================================

_tools: Optional[CoordinatorTools] = None


def check_file_exists(path: str) -> dict:
    """Check if a file exists in the services directory."""
    return _tools.check_file_exists(path)


def check_directory_exists(path: str) -> dict:
    """Check if a directory exists and list its contents."""
    return _tools.check_directory_exists(path)


def parse_imports(file_path: str) -> dict:
    """Extract imports/requires from a JavaScript file."""
    return _tools.parse_imports(file_path)


def validate_json_syntax(content: str) -> dict:
    """Check if JSON content is valid."""
    return _tools.validate_json_syntax(content)


def validate_js_syntax(content: str) -> dict:
    """Check if JavaScript syntax is valid."""
    return _tools.validate_js_syntax(content)


def detect_circular_deps(tasks: str) -> dict:
    """Detect circular dependencies in task graph. Pass tasks as JSON string."""
    try:
        tasks_dict = json.loads(tasks) if isinstance(tasks, str) else tasks
        return _tools.detect_circular_deps(tasks_dict)
    except json.JSONDecodeError as e:
        return {"error": f"Invalid JSON: {e}"}


def find_symbol_in_file(file_path: str, symbol: str) -> dict:
    """Check if a symbol exists in a file."""
    return _tools.find_symbol_in_file(file_path, symbol)


def get_file_exports(file_path: str) -> dict:
    """Get all exports from a JavaScript file."""
    return _tools.get_file_exports(file_path)


def resolve_import_path(from_file: str, import_path: str) -> dict:
    """Resolve a relative import path to absolute path."""
    return _tools.resolve_import_path(from_file, import_path)


def analyze_phase_parallelism(tasks: str, phase_tasks: str) -> dict:
    """Analyze if tasks in a phase can safely run in parallel. Pass as JSON strings."""
    try:
        tasks_dict = json.loads(tasks) if isinstance(tasks, str) else tasks
        phase_list = json.loads(phase_tasks) if isinstance(phase_tasks, str) else phase_tasks
        return _tools.analyze_phase_parallelism(tasks_dict, phase_list)
    except json.JSONDecodeError as e:
        return {"error": f"Invalid JSON: {e}"}


def read_file_content(file_path: str) -> dict:
    """Read file content."""
    return _tools.read_file_content(file_path)


# =============================================================================
# COORDINATOR AGENT
# =============================================================================

class CoordinatorAgent:
    """
    Coordinator Agent - validates plans with intelligence.
    
    Unlike pure Python validation, this agent can:
    - Reason about edge cases
    - Detect subtle issues (race conditions, import conflicts)
    - Provide detailed explanations of problems
    - Suggest fixes for issues found
    
    Tools available:
    - check_file_exists: Verify target files exist
    - check_directory_exists: Check directory structure
    - parse_imports: Extract imports from files
    - validate_json_syntax: Check JSON validity
    - validate_js_syntax: Check JS syntax
    - detect_circular_deps: Find circular task dependencies
    - find_symbol_in_file: Locate symbols in files
    - get_file_exports: Get exports from files
    - resolve_import_path: Resolve relative imports
    - analyze_phase_parallelism: Check parallel task safety
    - read_file_content: Read file contents
    """
    
    def __init__(self, services_path: str):
        """
        Args:
            services_path: Path to the services directory
        """
        global _tools
        
        self._services_path = Path(services_path)
        _tools = CoordinatorTools(services_path)
        
        # Use balanced model for validation
        self._model = select_model(tier=ModelTier.MEDIUM)
        self._agent = self._create_agent()
        self._session_service = InMemorySessionService()
        self._session = None
        self._runner = None
    
    def _create_agent(self) -> Agent:
        """Create the ADK agent with tools."""
        return Agent(
            model=self._model,
            name="forge_coordinator_agent",
            instruction=COORDINATOR_AGENT_SYSTEM_PROMPT,
            description="Validates plans and prepares for implementation",
            tools=[
                check_file_exists,
                check_directory_exists,
                parse_imports,
                validate_json_syntax,
                validate_js_syntax,
                detect_circular_deps,
                find_symbol_in_file,
                get_file_exports,
                resolve_import_path,
                analyze_phase_parallelism,
                read_file_content,
            ],
        )
    
    async def _ensure_session(self):
        """Ensure we have an active session."""
        if self._session is None:
            self._session = await self._session_service.create_session(
                app_name="forge_coordinator",
                user_id="developer"
            )
            self._runner = Runner(
                agent=self._agent,
                app_name="forge_coordinator",
                session_service=self._session_service
            )
    
    async def validate(self, plan: Plan) -> dict:
        """
        Validate a plan using intelligent analysis.
        
        Args:
            plan: The plan to validate
            
        Returns:
            {
                valid: bool,
                errors: [{task, issue, severity, suggestion}],
                warnings: [{task, issue, suggestion}],
                summary: str
            }
        """
        logger.info("🔍 Coordinator Agent starting plan validation...")
        logger.info(f"   └─ Tasks to validate: {len(plan.tasks)}")
        logger.info(f"   └─ Contracts defined: {len(plan.contracts)}")
        logger.info(f"   └─ Execution phases: {len(plan.execution)}")
        
        await self._ensure_session()
        
        # Build prompt with plan details - use compact JSON to fit more content
        # Full plan is critical for validation, so we use minimal indentation
        plan_dict = plan.to_dict()

        # Strip before/after snippets from the plan before sending to LLM.
        # These are code fragments (intentionally incomplete) that the LLM
        # mis-identifies as syntax errors. The coordinator only needs to validate
        # structural properties (file targets, deps, contracts, phases).
        def _strip_snippets(d):
            if isinstance(d, dict):
                return {k: (_strip_snippets(v) if k not in ('before', 'after') else '<snippet omitted>')
                        for k, v in d.items()}
            if isinstance(d, list):
                return [_strip_snippets(i) for i in d]
            return d

        plan_dict_stripped = _strip_snippets(plan_dict)

        plan_json_compact = json.dumps(plan_dict_stripped, indent=None, separators=(',', ':'))
        plan_json_pretty = json.dumps(plan_dict_stripped, indent=2)
        
        # Use compact version if pretty exceeds reasonable size, otherwise use pretty
        # Gemini 2.5 Flash has 1M context, but we want to stay reasonable
        MAX_PLAN_CHARS = 30000
        if len(plan_json_pretty) <= MAX_PLAN_CHARS:
            plan_json_for_prompt = plan_json_pretty
        elif len(plan_json_compact) <= MAX_PLAN_CHARS:
            plan_json_for_prompt = plan_json_compact
            logger.info(f"   └─ Using compact JSON ({len(plan_json_compact)} chars)")
        else:
            # Still too large - truncate but warn
            plan_json_for_prompt = plan_json_compact[:MAX_PLAN_CHARS]
            logger.warning(f"   └─ Plan JSON truncated from {len(plan_json_compact)} to {MAX_PLAN_CHARS} chars")
        
        prompt = f"""Validate this code generation plan.

## PLAN
```json
{plan_json_for_prompt}
```

## VALIDATION CHECKLIST

Use the tools to verify:

1. **File Existence**
   - For MODIFY actions: check_file_exists() must return exists=true
   - For CREATE actions: parent directory should exist
   - For DELETE actions: file must exist

2. **Task Dependencies**
   - Use detect_circular_deps() to find cycles
   - Verify depends_on references exist

3. **Contract Validity**
   - If task uses_contracts, those contracts must be defined
   - If task defines_contracts, verify the signature is valid JS

4. **Phase Safety**
   - Use analyze_phase_parallelism() for each phase
   - Flag any parallel execution conflicts

5. **Import Resolution**
   - For tasks that import from other tasks' files, verify order is correct
   - Use resolve_import_path() to check imports will work

6. **Syntax Validity**
   - Use validate_js_syntax() on contract implementations

## OUTPUT FORMAT

Return JSON:
```json
{{
    "valid": boolean,
    "errors": [
        {{"task": "task-id", "issue": "description", "severity": "error", "suggestion": "how to fix"}}
    ],
    "warnings": [
        {{"task": "task-id", "issue": "description", "suggestion": "recommendation"}}
    ],
    "summary": "Overall assessment"
}}
```

Be thorough. Use the tools to verify everything. Don't assume - check.
"""
        
        content = types.Content(
            role='user',
            parts=[types.Part(text=prompt)]
        )
        
        response_text = ""
        tool_call_count = 0
        try:
            logger.info("   └─ Calling LLM for validation...")
            
            event_count = 0
            _tok_in = _tok_out = _tok_think = 0
            async for event in self._runner.run_async(
                user_id="developer",
                session_id=self._session.id,
                new_message=content
            ):
                event_count += 1
                _m = getattr(event, "usage_metadata", None)
                if _m:
                    _tok_in    = max(_tok_in,    getattr(_m, "prompt_token_count",     0) or 0)
                    _tok_out   = max(_tok_out,   getattr(_m, "candidates_token_count", 0) or 0)
                    _tok_think = max(_tok_think, getattr(_m, "thoughts_token_count",   0) or 0)
                if hasattr(event, 'tool_calls') and event.tool_calls:
                    for tc in event.tool_calls:
                        tool_call_count += 1
                        logger.info(f"   └─ TOOL #{tool_call_count}: {tc.name}({json.dumps(tc.args or {}, default=str)[:120]})")
                if hasattr(event, 'tool_results') and event.tool_results:
                    for tr in event.tool_results:
                        name = tr.name if hasattr(tr, 'name') else 'unknown'
                        result_preview = str(tr.result)[:120] if hasattr(tr, 'result') else str(tr)[:120]
                        logger.debug(f"   └─ TOOL RESULT: {name} → {result_preview}")
                if hasattr(event, 'content') and event.content:
                    logger.debug(f"   └─ Event {event_count}: has content, is_final={event.is_final_response()}")
                else:
                    logger.debug(f"   └─ Event {event_count}: no content, is_final={event.is_final_response()}")

                if event.is_final_response() and event.content and event.content.parts:
                    for part in event.content.parts:
                        if part.text:
                            response_text += part.text

            _pid = getattr(self, '_pipeline_id', '')
            if _pid and (_tok_in or _tok_out):
                try:
                    from modules.cache.token_tracker import get_tracker
                    get_tracker().record(pipeline_id=_pid, model=self._model,
                        input_tokens=_tok_in, output_tokens=_tok_out,
                        reasoning_tokens=_tok_think, call_label="CoordinatorAgent.validate")
                except Exception:
                    pass
            
            logger.info(f"   └─ Total events: {event_count}, tool calls: {tool_call_count}, response chars: {len(response_text)}")
            
            # Handle empty response - fallback to basic validation
            if not response_text.strip():
                logger.warning("   └─ Empty LLM response, using fallback validation")
                return self._fallback_validation(plan)
            
            # Parse response
            json_match = re.search(r'```json\s*([\s\S]*?)\s*```', response_text)
            if json_match:
                result = json.loads(json_match.group(1))
            else:
                # Try raw JSON
                result = json.loads(response_text)
            
            # Log results
            num_errors = len(result.get('errors', []))
            num_warnings = len(result.get('warnings', []))
            is_valid = result.get('valid', False)
            
            if is_valid:
                logger.info(f"✅ Coordinator validation PASSED ({num_warnings} warnings)")
            else:
                logger.warning(f"❌ Coordinator validation FAILED: {num_errors} errors, {num_warnings} warnings")
                for err in result.get('errors', [])[:5]:  # Log first 5 errors
                    logger.warning(f"   └─ [{err.get('task', '?')}] {err.get('issue', '')[:100]}")
            
            logger.debug(f"   └─ Summary: {result.get('summary', '')[:150]}")
            
            return result
            
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse LLM response: {e}")
            logger.info("   └─ Falling back to deterministic validation")
            return self._fallback_validation(plan)
            
        except Exception as e:
            logger.error(f"Coordinator validation failed: {e}")
            logger.info("   └─ Falling back to deterministic validation")
            return self._fallback_validation(plan)
    
    def _fallback_validation(self, plan: Plan) -> dict:
        """
        Fallback deterministic validation when LLM fails.
        Checks basic requirements without LLM.
        """
        logger.info("   └─ Running fallback deterministic validation...")
        errors = []
        warnings = []
        
        for task_id, task in plan.tasks.items():
            file_path = self._services_path / task.file
            
            # Check file existence based on action
            if task.action == TaskAction.MODIFY:
                if file_path.is_dir():
                    errors.append({
                        "task": task_id,
                        "issue": f"MODIFY target is a directory, not a file: {task.file}",
                        "severity": "error",
                        "suggestion": "Tasks must target files, not directories"
                    })
                elif not file_path.exists():
                    errors.append({
                        "task": task_id,
                        "issue": f"MODIFY target does not exist: {task.file}",
                        "severity": "error",
                        "suggestion": f"Verify the file path or change action to CREATE"
                    })
            elif task.action == TaskAction.CREATE:
                parent = file_path.parent
                if not parent.exists():
                    warnings.append({
                        "task": task_id,
                        "issue": f"Parent directory does not exist: {parent}",
                        "suggestion": "Directory will be created automatically"
                    })
                if file_path.exists():
                    warnings.append({
                        "task": task_id,
                        "issue": f"CREATE target already exists: {task.file}",
                        "suggestion": "File will be overwritten"
                    })
            
            # Check contract references
            for contract_name in task.uses_contracts:
                if contract_name not in plan.contracts:
                    errors.append({
                        "task": task_id,
                        "issue": f"References undefined contract: {contract_name}",
                        "severity": "error",
                        "suggestion": f"Define the contract or remove the reference"
                    })
            
            # Check dependencies exist
            for dep in task.depends_on:
                if dep not in plan.tasks:
                    errors.append({
                        "task": task_id,
                        "issue": f"Depends on non-existent task: {dep}",
                        "severity": "error",
                        "suggestion": f"Remove the dependency or add the task"
                    })
        
        is_valid = len(errors) == 0
        
        if is_valid:
            logger.info(f"✅ Fallback validation PASSED ({len(warnings)} warnings)")
        else:
            logger.warning(f"❌ Fallback validation FAILED: {len(errors)} errors")
        
        return {
            "valid": is_valid,
            "errors": errors,
            "warnings": warnings,
            "summary": f"Fallback validation: {len(errors)} errors, {len(warnings)} warnings"
        }
    
    def create_task_files(self, plan: Plan) -> dict[str, TaskFile]:
        """
        Create task files for implementation.
        
        This is deterministic - no LLM needed.
        """
        logger.info("📦 Coordinator creating task files for implementation...")
        
        # Convert contracts to dicts
        contracts_dict = {
            name: contract.to_dict()
            for name, contract in plan.contracts.items()
        }
        
        # Get design decisions
        design_decisions = []
        if plan.design and plan.design.decisions:
            design_decisions = [d.decision for d in plan.design.decisions]
        
        # Get conventions
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
            
            task_files[task_id] = task_file
            logger.debug(f"   └─ Created task file: {task_id} → {task.file} ({task.action.value})")
        
        logger.info(f"   └─ Created {len(task_files)} task files")
        return task_files
    
    def get_execution_order(self, plan: Plan) -> list[ExecutionPhase]:
        """
        Get execution order from plan.
        
        This is deterministic - no LLM needed.
        """
        if plan.execution:
            return sorted(plan.execution, key=lambda p: p.phase)
        
        # Compute from dependencies
        return self._compute_phases(plan)
    
    def _compute_phases(self, plan: Plan) -> list[ExecutionPhase]:
        """Compute execution phases from task dependencies."""
        in_degree = {task_id: 0 for task_id in plan.tasks}
        for task_id, task in plan.tasks.items():
            for dep in task.depends_on:
                if dep in in_degree:
                    in_degree[task_id] += 1
        
        phases = []
        remaining = set(plan.tasks.keys())
        phase_num = 0
        
        while remaining:
            ready = [t for t in remaining if in_degree[t] == 0]
            
            if not ready:
                ready = list(remaining)[:1]
            
            phase = ExecutionPhase(
                phase=phase_num,
                description=f"Phase {phase_num}",
                tasks=ready,
                parallel=len(ready) > 1,
                wait_for_completion=True,
            )
            phases.append(phase)
            
            for task_id in ready:
                remaining.remove(task_id)
                for other_id in remaining:
                    if task_id in plan.tasks[other_id].depends_on:
                        in_degree[other_id] -= 1
            
            phase_num += 1
        
        return phases
