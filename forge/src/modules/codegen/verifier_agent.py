"""
Verifier Agent.

An intelligent agent that verifies generated diffs are correct and safe.
Has deterministic tools to analyze code, apply diffs, and run checks.

Unlike pure Python verification, the agent can:
- Reason about code quality
- Detect subtle bugs and issues
- Understand context and intent
- Provide actionable feedback
"""

import os
import re
import json
import subprocess
import tempfile
import shutil
from pathlib import Path
from typing import Optional

from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from .schemas import (
    Plan,
    AgentOutput,
    VerificationResult,
    VerificationIssue,
)
from .prompts import VERIFIER_AGENT_SYSTEM_PROMPT
from .llm_router import select_model, ModelTier
from .logging_config import verify_logger as logger

# Import the harness system
from .harness import (
    DeterministicGate,
    FileDiff,
    HarnessResult,
    ViolationSeverity,
)
from .harness.gate import GateConfig


# =============================================================================
# TOOL IMPLEMENTATIONS
# =============================================================================

class VerifierTools:
    """Deterministic tools for the Verifier Agent."""
    
    def __init__(self, services_path: str):
        self._services_path = Path(services_path)
        self._temp_dir = None
    
    def parse_diff(self, diff_text: str) -> dict:
        """
        Parse a unified diff into structured data.
        
        Args:
            diff_text: Unified diff string
            
        Returns:
            {old_file, new_file, hunks: [{old_start, old_count, new_start, new_count, lines}]}
        """
        result = {
            "old_file": None,
            "new_file": None,
            "hunks": [],
            "additions": 0,
            "deletions": 0,
        }
        
        lines = diff_text.strip().splitlines()
        current_hunk = None
        
        for line in lines:
            if line.startswith('---'):
                # Remove 'a/' prefix if present
                path = line[4:].strip().split('\t')[0]
                if path.startswith('a/'):
                    path = path[2:]
                result["old_file"] = path
            elif line.startswith('+++'):
                path = line[4:].strip().split('\t')[0]
                if path.startswith('b/'):
                    path = path[2:]
                result["new_file"] = path
            elif line.startswith('@@'):
                match = re.match(r'@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@', line)
                if match:
                    current_hunk = {
                        "old_start": int(match.group(1)),
                        "old_count": int(match.group(2) or 1),
                        "new_start": int(match.group(3)),
                        "new_count": int(match.group(4) or 1),
                        "lines": [],
                    }
                    result["hunks"].append(current_hunk)
            elif current_hunk is not None:
                if line.startswith('-'):
                    current_hunk["lines"].append(('-', line[1:]))
                    result["deletions"] += 1
                elif line.startswith('+'):
                    current_hunk["lines"].append(('+', line[1:]))
                    result["additions"] += 1
                elif line.startswith(' ') or line == '':
                    current_hunk["lines"].append((' ', line[1:] if line else ''))
        
        return result
    
    def validate_diff_syntax(self, diff_text: str) -> dict:
        """
        Check if diff format is valid.
        
        Args:
            diff_text: Unified diff string
            
        Returns:
            {valid, errors}
        """
        errors = []
        
        if not diff_text.strip():
            return {"valid": False, "errors": ["Empty diff"]}
        
        lines = diff_text.strip().splitlines()
        
        has_old_file = False
        has_new_file = False
        has_hunk = False
        
        for i, line in enumerate(lines):
            if line.startswith('---'):
                has_old_file = True
            elif line.startswith('+++'):
                has_new_file = True
            elif line.startswith('@@'):
                has_hunk = True
                # Validate hunk header
                if not re.match(r'@@ -\d+(?:,\d+)? \+\d+(?:,\d+)? @@', line):
                    errors.append(f"Line {i+1}: Invalid hunk header format")
        
        if not has_old_file:
            errors.append("Missing '---' header for old file")
        if not has_new_file:
            errors.append("Missing '+++' header for new file")
        if not has_hunk:
            errors.append("No hunks found (missing @@ markers)")
        
        return {"valid": len(errors) == 0, "errors": errors}
    
    def apply_diff_to_content(self, original_content: str, diff_text: str) -> dict:
        """
        Apply a diff to content and return result.
        
        Args:
            original_content: Original file content (empty string for new files)
            diff_text: Unified diff to apply
            
        Returns:
            {success, result, error}
        """
        try:
            diff = self.parse_diff(diff_text)
            
            # Handle new file (--- /dev/null)
            if diff["old_file"] in ["/dev/null", "dev/null", None] or not original_content:
                lines = []
                for hunk in diff["hunks"]:
                    for line_type, line in hunk["lines"]:
                        if line_type == '+':
                            lines.append(line)
                return {"success": True, "result": '\n'.join(lines)}
            
            # Apply hunks to existing content
            original_lines = original_content.splitlines()
            result_lines = []
            current_line = 0
            
            for hunk in diff["hunks"]:
                old_start = hunk["old_start"] - 1  # 0-indexed
                
                # Copy lines before this hunk
                while current_line < old_start:
                    if current_line < len(original_lines):
                        result_lines.append(original_lines[current_line])
                    current_line += 1
                
                # Apply hunk
                for line_type, line in hunk["lines"]:
                    if line_type == ' ':
                        if current_line < len(original_lines):
                            result_lines.append(original_lines[current_line])
                        current_line += 1
                    elif line_type == '-':
                        current_line += 1
                    elif line_type == '+':
                        result_lines.append(line)
            
            # Copy remaining lines
            while current_line < len(original_lines):
                result_lines.append(original_lines[current_line])
                current_line += 1
            
            return {"success": True, "result": '\n'.join(result_lines)}
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def check_js_syntax(self, code: str) -> dict:
        """
        Check JavaScript syntax using Node.js.
        
        Args:
            code: JavaScript code to check
            
        Returns:
            {valid, errors}
        """
        try:
            result = subprocess.run(
                ['node', '--check', '-e', code],
                capture_output=True,
                text=True,
                timeout=5,
            )
            
            if result.returncode == 0:
                return {"valid": True, "errors": []}
            else:
                error = result.stderr.strip()
                # Parse line number from error
                match = re.search(r':(\d+)', error)
                line = int(match.group(1)) if match else None
                return {
                    "valid": False,
                    "errors": [{"line": line, "message": error}]
                }
                
        except subprocess.TimeoutExpired:
            return {"valid": False, "errors": [{"message": "Syntax check timed out"}]}
        except FileNotFoundError:
            return {"valid": None, "errors": [{"message": "Node.js not available"}]}
    
    def run_eslint(self, code: str, filename: str = "temp.js") -> dict:
        """
        Run ESLint on code.
        
        Args:
            code: Code to lint
            filename: Filename for ESLint context
            
        Returns:
            {passed, errors}
        """
        try:
            # Write to temp file
            with tempfile.NamedTemporaryFile(
                mode='w', 
                suffix='.js', 
                delete=False,
                encoding='utf-8'
            ) as f:
                f.write(code)
                temp_path = f.name
            
            try:
                result = subprocess.run(
                    ['eslint', temp_path, '--format', 'json', '--no-eslintrc'],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                
                if result.returncode == 0:
                    return {"passed": True, "errors": []}
                
                try:
                    lint_output = json.loads(result.stdout)
                    errors = []
                    for file_result in lint_output:
                        for msg in file_result.get('messages', []):
                            if msg.get('severity', 0) >= 2:
                                errors.append({
                                    "line": msg.get('line'),
                                    "rule": msg.get('ruleId'),
                                    "message": msg.get('message'),
                                })
                    return {"passed": len(errors) == 0, "errors": errors}
                except json.JSONDecodeError:
                    return {"passed": False, "errors": [{"message": result.stderr or result.stdout}]}
                    
            finally:
                os.unlink(temp_path)
                
        except subprocess.TimeoutExpired:
            return {"passed": False, "errors": [{"message": "ESLint timed out"}]}
        except FileNotFoundError:
            return {"passed": None, "errors": [{"message": "ESLint not available"}]}
    
    def find_undefined_references(self, code: str) -> dict:
        """
        Find variables that are used but not defined.
        
        Args:
            code: JavaScript code
            
        Returns:
            {undefined: [{name, line}]}
        """
        # Simple heuristic-based detection
        # A proper implementation would use an AST parser
        
        undefined = []
        lines = code.splitlines()
        
        # Track defined variables
        defined = set(['require', 'module', 'exports', 'console', 'process',
                       'Buffer', 'setTimeout', 'setInterval', 'clearTimeout',
                       'clearInterval', 'Promise', 'JSON', 'Math', 'Date',
                       'Array', 'Object', 'String', 'Number', 'Boolean',
                       'Error', 'TypeError', 'RangeError', 'undefined', 'null',
                       'true', 'false', 'this', 'async', 'await', 'fetch'])
        
        # Find definitions
        def_patterns = [
            r'(?:const|let|var)\s+(\w+)',
            r'function\s+(\w+)',
            r'class\s+(\w+)',
            r'(\w+)\s*=\s*(?:function|async)',
        ]
        
        for line in lines:
            for pattern in def_patterns:
                for match in re.finditer(pattern, line):
                    defined.add(match.group(1))
        
        # Find usages (simplified)
        usage_pattern = re.compile(r'\b([A-Za-z_]\w*)\b')
        keywords = {'if', 'else', 'for', 'while', 'do', 'switch', 'case',
                    'break', 'continue', 'return', 'throw', 'try', 'catch',
                    'finally', 'new', 'typeof', 'instanceof', 'in', 'of',
                    'import', 'export', 'from', 'default', 'const', 'let',
                    'var', 'function', 'class', 'extends', 'async', 'await'}
        
        for i, line in enumerate(lines, 1):
            # Skip comments
            if line.strip().startswith('//') or line.strip().startswith('*'):
                continue
            
            for match in usage_pattern.finditer(line):
                name = match.group(1)
                if name not in defined and name not in keywords:
                    # Check if it's a property access (likely okay)
                    pos = match.start()
                    if pos > 0 and line[pos-1] == '.':
                        continue
                    undefined.append({"name": name, "line": i})
        
        return {"undefined": undefined}
    
    def check_imports_resolve(self, code: str, base_file: str) -> dict:
        """
        Check if all imports in code can resolve.
        
        Args:
            code: JavaScript code
            base_file: The file this code will be in
            
        Returns:
            {all_resolve, missing}
        """
        missing = []
        base_dir = (self._services_path / base_file).parent
        
        # Find imports
        require_pattern = re.compile(r'''require\s*\(\s*['"]([^'"]+)['"]\s*\)''')
        import_pattern = re.compile(r'''import\s+.*?\s+from\s+['"]([^'"]+)['"]''')
        
        lines = code.splitlines()
        
        for i, line in enumerate(lines, 1):
            for pattern in [require_pattern, import_pattern]:
                for match in pattern.finditer(line):
                    module_path = match.group(1)
                    
                    # Skip node modules
                    if not module_path.startswith('.'):
                        continue
                    
                    # Resolve path
                    resolved = (base_dir / module_path).resolve()
                    
                    # Check with extensions
                    exists = False
                    for ext in ['', '.js', '.ts', '.json', '/index.js', '/index.ts']:
                        if Path(str(resolved) + ext).exists():
                            exists = True
                            break
                    
                    if not exists:
                        missing.append({
                            "import": module_path,
                            "line": i,
                            "resolved_to": str(resolved),
                        })
        
        return {"all_resolve": len(missing) == 0, "missing": missing}
    
    def compare_signature(self, code: str, contract_signature: str) -> dict:
        """
        Compare a function in code to its contract signature.
        
        Args:
            code: Code containing the function
            contract_signature: Expected signature from contract
            
        Returns:
            {matches, actual, expected, diff}
        """
        # Extract function name from contract
        name_match = re.search(r'(?:async\s+)?function\s+(\w+)|(\w+)\s*=\s*(?:async\s+)?(?:function|\()', contract_signature)
        if not name_match:
            return {"matches": None, "error": "Could not parse contract signature"}
        
        func_name = name_match.group(1) or name_match.group(2)
        
        # Find function in code
        patterns = [
            rf'(?:async\s+)?function\s+{re.escape(func_name)}\s*\([^)]*\)',
            rf'(?:const|let|var)\s+{re.escape(func_name)}\s*=\s*(?:async\s+)?(?:function\s*)?\([^)]*\)',
            rf'{re.escape(func_name)}\s*:\s*(?:async\s+)?function\s*\([^)]*\)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, code)
            if match:
                actual = match.group(0)
                
                # Normalize for comparison
                def normalize(s):
                    return re.sub(r'\s+', ' ', s).strip()
                
                norm_actual = normalize(actual)
                norm_expected = normalize(contract_signature.split('{')[0])
                
                return {
                    "matches": norm_actual == norm_expected or func_name in actual,
                    "actual": actual,
                    "expected": contract_signature.split('{')[0].strip(),
                }
        
        return {"matches": False, "error": f"Function '{func_name}' not found in code"}
    
    def extract_functions(self, code: str) -> dict:
        """
        Extract all function definitions from code.
        
        Args:
            code: JavaScript code
            
        Returns:
            {functions: [{name, params, line, async, kind}]}
        """
        functions = []
        lines = code.splitlines()
        
        patterns = [
            (r'async\s+function\s+(\w+)\s*\(([^)]*)\)', 'async function'),
            (r'function\s+(\w+)\s*\(([^)]*)\)', 'function'),
            (r'(?:const|let|var)\s+(\w+)\s*=\s*async\s*\(([^)]*)\)\s*=>', 'async arrow'),
            (r'(?:const|let|var)\s+(\w+)\s*=\s*\(([^)]*)\)\s*=>', 'arrow'),
            (r'(?:const|let|var)\s+(\w+)\s*=\s*async\s+function\s*\(([^)]*)\)', 'async expr'),
            (r'(?:const|let|var)\s+(\w+)\s*=\s*function\s*\(([^)]*)\)', 'function expr'),
            (r'(\w+)\s*\(([^)]*)\)\s*{', 'method'),
        ]
        
        for i, line in enumerate(lines, 1):
            for pattern, kind in patterns:
                match = re.search(pattern, line)
                if match:
                    name = match.group(1)
                    params = match.group(2).strip()
                    functions.append({
                        "name": name,
                        "params": params,
                        "line": i,
                        "async": 'async' in kind,
                        "kind": kind,
                    })
                    break
        
        return {"functions": functions, "count": len(functions)}
    
    def check_error_handling(self, code: str) -> dict:
        """
        Check if async functions have proper error handling.
        
        Args:
            code: JavaScript code
            
        Returns:
            {has_handling, unhandled}
        """
        unhandled = []
        
        # Find async functions
        async_pattern = re.compile(r'async\s+function\s+(\w+)|(\w+)\s*=\s*async')
        
        lines = code.splitlines()
        in_async = False
        current_func = None
        brace_count = 0
        has_try = False
        func_start_line = 0
        
        for i, line in enumerate(lines, 1):
            match = async_pattern.search(line)
            if match:
                # Save previous function if it had no try
                if in_async and current_func and not has_try:
                    unhandled.append({"function": current_func, "line": func_start_line})
                
                in_async = True
                current_func = match.group(1) or match.group(2)
                has_try = False
                brace_count = 0
                func_start_line = i
            
            if in_async:
                brace_count += line.count('{') - line.count('}')
                if 'try' in line and '{' in line:
                    has_try = True
                if '.catch(' in line:
                    has_try = True
                
                if brace_count <= 0 and current_func:
                    if not has_try:
                        unhandled.append({"function": current_func, "line": func_start_line})
                    in_async = False
                    current_func = None
        
        return {"has_handling": len(unhandled) == 0, "unhandled": unhandled}
    
    def count_diff_changes(self, diff_text: str) -> dict:
        """
        Count additions and deletions in a diff.
        
        Args:
            diff_text: Unified diff
            
        Returns:
            {additions, deletions, net_change}
        """
        parsed = self.parse_diff(diff_text)
        return {
            "additions": parsed["additions"],
            "deletions": parsed["deletions"],
            "net_change": parsed["additions"] - parsed["deletions"],
        }
    
    def read_file_content(self, file_path: str) -> dict:
        """
        Read current file content from services.
        
        Args:
            file_path: Relative path
            
        Returns:
            {content, exists}
        """
        full_path = self._services_path / file_path
        
        if not full_path.exists():
            return {"exists": False, "content": None}
        
        try:
            content = full_path.read_text(encoding='utf-8')
            return {"exists": True, "content": content, "lines": len(content.splitlines())}
        except Exception as e:
            return {"exists": True, "error": str(e)}
    
    def get_contract_from_plan(self, plan_json: str, contract_name: str) -> dict:
        """
        Get a contract definition from the plan.
        
        Args:
            plan_json: Plan as JSON string
            contract_name: Name of contract to retrieve
            
        Returns:
            Contract details or error
        """
        try:
            plan = json.loads(plan_json) if isinstance(plan_json, str) else plan_json
            contracts = plan.get('contracts', {})
            
            if contract_name in contracts:
                return {"found": True, "contract": contracts[contract_name]}
            else:
                return {"found": False, "available": list(contracts.keys())}
        except Exception as e:
            return {"error": str(e)}
    
    def get_task_from_plan(self, plan_json: str, task_id: str) -> dict:
        """
        Get a task specification from the plan.
        
        Args:
            plan_json: Plan as JSON string
            task_id: Task ID to retrieve (e.g., "task-1" or "1")
            
        Returns:
            Task details including file, service, action, changes, contracts
        """
        try:
            plan = json.loads(plan_json) if isinstance(plan_json, str) else plan_json
            
            # First try to get from tasks dict directly
            tasks = plan.get('tasks', {})
            
            # Normalize task_id
            if not task_id.startswith('task-'):
                task_id = f"task-{task_id}"
            
            # Check tasks dict first
            if task_id in tasks:
                task = tasks[task_id]
                return {
                    "found": True,
                    "task": {
                        "id": task_id,
                        "file": task.get('file'),
                        "service": task.get('service'),
                        "action": task.get('action'),
                        "description": task.get('description'),
                        "changes": task.get('changes', []),
                        "uses_contracts": task.get('uses_contracts', []),
                        "defines_contracts": task.get('defines_contracts', []),
                        "dependencies": task.get('depends_on', []),
                    }
                }
            
            # Also search execution phases
            execution = plan.get('execution', [])
            for phase in execution:
                phase_tasks = phase.get('tasks', [])
                if task_id in phase_tasks:
                    # Task ID found in phase, but details are in tasks dict
                    if task_id in tasks:
                        task = tasks[task_id]
                        return {
                            "found": True,
                            "task": {
                                "id": task_id,
                                "file": task.get('file'),
                                "service": task.get('service'),
                                "action": task.get('action'),
                                "description": task.get('description'),
                                "changes": task.get('changes', []),
                                "uses_contracts": task.get('uses_contracts', []),
                                "defines_contracts": task.get('defines_contracts', []),
                                "dependencies": task.get('depends_on', []),
                            }
                        }
            
            # Task not found - list available tasks
            return {"found": False, "available": list(tasks.keys())}
        except Exception as e:
            return {"error": str(e)}


# =============================================================================
# MODULE-LEVEL TOOL FUNCTIONS (for ADK)
# =============================================================================

_tools: Optional[VerifierTools] = None


def parse_diff(diff_text: str) -> dict:
    """Parse a unified diff into structured data."""
    return _tools.parse_diff(diff_text)


def validate_diff_syntax(diff_text: str) -> dict:
    """Check if diff format is valid."""
    return _tools.validate_diff_syntax(diff_text)


def apply_diff_to_content(original_content: str, diff_text: str) -> dict:
    """Apply a diff to content and return result."""
    return _tools.apply_diff_to_content(original_content, diff_text)


def check_js_syntax(code: str) -> dict:
    """Check JavaScript syntax using Node.js."""
    return _tools.check_js_syntax(code)


def run_eslint(code: str, filename: str = "temp.js") -> dict:
    """Run ESLint on code."""
    return _tools.run_eslint(code, filename)


def find_undefined_references(code: str) -> dict:
    """Find variables that are used but not defined."""
    return _tools.find_undefined_references(code)


def check_imports_resolve(code: str, base_file: str) -> dict:
    """Check if all imports in code can resolve."""
    return _tools.check_imports_resolve(code, base_file)


def compare_signature(code: str, contract_signature: str) -> dict:
    """Compare a function in code to its contract signature."""
    return _tools.compare_signature(code, contract_signature)


def extract_functions(code: str) -> dict:
    """Extract all function definitions from code."""
    return _tools.extract_functions(code)


def check_error_handling(code: str) -> dict:
    """Check if async functions have proper error handling."""
    return _tools.check_error_handling(code)


def count_diff_changes(diff_text: str) -> dict:
    """Count additions and deletions in a diff."""
    return _tools.count_diff_changes(diff_text)


def read_file_content(file_path: str) -> dict:
    """Read current file content from services."""
    return _tools.read_file_content(file_path)


def get_contract_from_plan(plan_json: str, contract_name: str) -> dict:
    """Get a contract definition from the plan."""
    return _tools.get_contract_from_plan(plan_json, contract_name)


def get_task_from_plan(plan_json: str, task_id: str) -> dict:
    """Get a task specification from the plan."""
    return _tools.get_task_from_plan(plan_json, task_id)


# =============================================================================
# VERIFIER AGENT
# =============================================================================

class VerifierAgent:
    """
    Verifier Agent - intelligently verifies generated diffs.
    
    Unlike pure Python verification, this agent can:
    - Reason about code correctness
    - Detect subtle bugs
    - Understand intent and context
    - Provide actionable suggestions
    
    Tools available:
    - parse_diff: Parse unified diff structure
    - validate_diff_syntax: Check diff format
    - apply_diff_to_content: Apply diff and get result
    - check_js_syntax: Verify JavaScript syntax
    - run_eslint: Run linter
    - find_undefined_references: Find undefined variables
    - check_imports_resolve: Verify imports
    - compare_signature: Compare to contract
    - extract_functions: List functions in code
    - check_error_handling: Verify error handling
    - count_diff_changes: Count changes
    - read_file_content: Read original files
    - get_contract_from_plan: Get contract details
    """
    
    def __init__(self, services_path: str):
        """
        Args:
            services_path: Path to the services directory
        """
        global _tools
        
        self._services_path = Path(services_path)
        _tools = VerifierTools(services_path)
        
        # Use pro model for verification (same as Design Agent)
        # gemini-2.5-flash returns empty responses with tools
        from modules.llm_registry import get_adk_model
        self._model = get_adk_model("gemini-3.1-pro-preview-customtools")
        self._agent = self._create_agent()
        self._session_service = InMemorySessionService()
        self._session = None
        self._runner = None
    
    def _create_agent(self) -> Agent:
        """Create the ADK agent with tools."""
        return Agent(
            model=self._model,
            name="forge_verifier_agent",
            instruction=VERIFIER_AGENT_SYSTEM_PROMPT,
            description="Verifies generated code changes",
            tools=[
                parse_diff,
                validate_diff_syntax,
                apply_diff_to_content,
                check_js_syntax,
                run_eslint,
                find_undefined_references,
                check_imports_resolve,
                compare_signature,
                extract_functions,
                check_error_handling,
                count_diff_changes,
                read_file_content,
                get_contract_from_plan,
                get_task_from_plan,
            ],
        )
    
    async def _ensure_session(self):
        """Create a FRESH session for each verification (avoid state issues)."""
        # Always create fresh session to avoid state contamination
        self._session = await self._session_service.create_session(
            app_name="forge_verifier",
            user_id="developer"
        )
        self._runner = Runner(
            agent=self._agent,
            app_name="forge_verifier",
            session_service=self._session_service
        )
    
    async def verify(
        self, 
        plan: Plan, 
        diffs: list[AgentOutput]
    ) -> VerificationResult:
        """
        Verify all generated diffs.
        
        Args:
            plan: The execution plan
            diffs: Generated diffs from implementation
            
        Returns:
            VerificationResult with issues and summary
        """
        logger.info("🔬 Verifier Agent starting diff verification...")
        logger.info(f"   └─ Diffs to verify: {len(diffs)}")
        logger.info(f"   └─ Tasks in plan: {len(plan.tasks)}")
        
        successful = [d for d in diffs if d.status == "success"]
        failed = [d for d in diffs if d.status != "success"]
        logger.info(f"   └─ Successful: {len(successful)}, Failed: {len(failed)}")
        
        # Fast path: If all diffs failed, no need for LLM verification
        if len(successful) == 0:
            logger.info("   └─ All tasks failed, skipping LLM verification")
            return self._fallback_verification(plan, diffs)
        
        # ========================================
        # HARNESS VERIFICATION (Deterministic)
        # ========================================
        harness_result = await self._run_harness_verification(plan, diffs)
        
        if not harness_result.passed:
            logger.warning(f"   └─ Harness FAILED: {harness_result.error_count} errors, {harness_result.warning_count} warnings")
            # Convert harness result to VerificationResult
            return self._convert_harness_result(harness_result)
        
        logger.info(f"   └─ Harness PASSED ({harness_result.warning_count} warnings)")
        
        # Fast path: For simple cases (2 or fewer small diffs), harness is enough
        total_diff_chars = sum(len(d.diff or '') for d in diffs)
        if len(diffs) <= 2 and total_diff_chars < 2000:
            logger.info(f"   └─ Simple case ({len(diffs)} diffs, {total_diff_chars} chars), using harness result")
            return self._convert_harness_result(harness_result, include_warnings=True)
        
        await self._ensure_session()
        
        # Build context - use compact JSON to save tokens
        plan_json = json.dumps(plan.to_dict(), separators=(',', ':'))
        
        diffs_text = ""
        for output in diffs:
            diffs_text += f"\n### Task: {output.task_id}\n"
            diffs_text += f"File: {output.file}\n"
            diffs_text += f"Status: {output.status}\n"
            if output.diff:
                diffs_text += f"```diff\n{output.diff}\n```\n"
            if output.error_message:
                diffs_text += f"Error: {output.error_message}\n"
        
        # Simplified prompt - focus on the essentials
        prompt = f"""Verify these generated diffs against the plan.

## PLAN (compact)
```json
{plan_json[:10000]}
```

## GENERATED DIFFS
{diffs_text[:6000]}

## VERIFICATION

For each diff, check:
1. File path matches the task specification
2. Diff syntax is valid (has --- +++ @@ markers)
3. Changes match what the task asked for
4. No syntax errors in the resulting code

Return JSON:
```json
{{
    "passed": true/false,
    "issues": [
        {{"file": "path", "task_id": "id", "severity": "error|warning", "issue": "description", "suggestion": "fix"}}
    ],
    "summary": "Brief assessment"
}}
```

If everything looks correct, return {{"passed": true, "issues": [], "summary": "All diffs verified successfully"}}
"""
        
        content = types.Content(
            role='user',
            parts=[types.Part(text=prompt)]
        )
        
        response_text = ""
        event_count = 0
        all_texts = []  # Collect all text parts for debugging
        try:
            logger.info("   └─ Calling Verifier LLM...")
            async for event in self._runner.run_async(
                user_id="developer",
                session_id=self._session.id,
                new_message=content
            ):
                event_count += 1
                # Log event details for debugging
                has_content = hasattr(event, 'content') and event.content and event.content.parts
                is_final = event.is_final_response()
                
                # Check for tool calls
                has_tool_calls = False
                if has_content:
                    for part in event.content.parts:
                        if hasattr(part, 'function_call') and part.function_call:
                            has_tool_calls = True
                            logger.debug(f"   └─ Event {event_count}: tool_call={part.function_call.name}")
                
                logger.debug(f"   └─ Event {event_count}: has_content={has_content}, is_final={is_final}, tool_call={has_tool_calls}")
                
                # Capture text from ANY event that has text
                if has_content:
                    for part in event.content.parts:
                        if hasattr(part, 'text') and part.text:
                            all_texts.append(part.text)
                            logger.debug(f"   └─ Got text ({len(part.text)} chars)")
                
                # Use final response text preferentially
                if is_final and has_content:
                    for part in event.content.parts:
                        if hasattr(part, 'text') and part.text:
                            response_text = part.text  # Use final response
            
            # If no final response text, use accumulated texts
            if not response_text and all_texts:
                response_text = all_texts[-1]  # Use last text
                logger.info(f"   └─ Using accumulated text (no final response)")
            
            logger.info(f"   └─ Total events: {event_count}, response chars: {len(response_text)}, all_texts: {len(all_texts)}")
            
            # Check if we got a response
            if not response_text.strip():
                logger.warning("Verifier LLM returned empty response, using fallback verification")
                return self._fallback_verification(plan, diffs)
            
            # Parse response
            json_match = re.search(r'```json\s*([\s\S]*?)\s*```', response_text)
            if json_match:
                result = json.loads(json_match.group(1))
            else:
                result = json.loads(response_text)
            
            # Convert to VerificationResult
            issues = []
            for issue in result.get('issues', []):
                issues.append(VerificationIssue(
                    file=issue.get('file', 'unknown'),
                    severity=issue.get('severity', 'warning'),
                    issue=issue.get('issue', ''),
                    line=issue.get('line'),
                    suggestion=issue.get('suggestion'),
                    task_id=issue.get('task_id'),
                    category=issue.get('category'),
                    expected=issue.get('expected'),
                    actual=issue.get('actual'),
                    fix_instruction=issue.get('fix_instruction'),
                ))
            
            # Log verification results
            passed = result.get('passed', False)
            num_errors = len([i for i in issues if i.severity == 'error'])
            num_warnings = len([i for i in issues if i.severity == 'warning'])
            
            if passed:
                logger.info(f"Verifier PASSED ({num_warnings} warnings)")
            else:
                logger.warning(f"Verifier FAILED: {num_errors} errors, {num_warnings} warnings")
                for issue in issues[:5]:  # Log first 5 issues
                    category = f"[{issue.category}]" if issue.category else ""
                    logger.warning(f"   - {category} {issue.file}: {issue.issue[:80]}")
            
            logger.debug(f"   Summary: {result.get('summary', '')[:150]}")
            
            return VerificationResult(
                passed=passed,
                issues=issues,
                tool_results={},
                llm_results={"summary": result.get('summary', '')},
            )
            
        except Exception as e:
            logger.error(f"Verifier failed: {e}")
            logger.info("   Using fallback verification")
            return self._fallback_verification(plan, diffs)
    
    def _fallback_verification(self, plan: Plan, diffs: list[AgentOutput]) -> VerificationResult:
        """
        Fallback deterministic verification when LLM fails.
        Performs basic checks on diffs without LLM reasoning.
        """
        logger.info("   Running fallback deterministic verification...")
        issues = []
        
        for output in diffs:
            if output.status != "success":
                issues.append(VerificationIssue(
                    file=output.file,
                    severity="error",
                    issue=f"Task {output.task_id} failed: {output.error_message or 'Unknown error'}",
                    task_id=output.task_id,
                    category="implementation_failed",
                ))
                continue
            
            if not output.diff:
                issues.append(VerificationIssue(
                    file=output.file,
                    severity="error",
                    issue=f"Task {output.task_id} produced no diff",
                    task_id=output.task_id,
                    category="no_diff",
                ))
                continue
            
            # Basic diff validation
            parsed = _tools.parse_diff(output.diff)
            if not parsed.get('hunks'):
                issues.append(VerificationIssue(
                    file=output.file,
                    severity="warning",
                    issue=f"Task {output.task_id} diff has no hunks (may be empty)",
                    task_id=output.task_id,
                    category="empty_diff",
                ))
            
            # Check if diff can be applied (for MODIFY tasks)
            task = plan.tasks.get(output.task_id)
            if task and task.action == "MODIFY":
                original = _tools.read_file_content(output.file)
                if original.get('exists'):
                    apply_result = _tools.apply_diff_to_content(original['content'], output.diff)
                    if not apply_result.get('success'):
                        issues.append(VerificationIssue(
                            file=output.file,
                            severity="error",
                            issue=f"Diff cannot be applied: {apply_result.get('error', 'unknown')}",
                            task_id=output.task_id,
                            category="diff_application_failed",
                            fix_instruction="Regenerate diff with correct context lines",
                        ))
        
        passed = not any(i.severity == "error" for i in issues)
        logger.info(f"Fallback verification: {'PASSED' if passed else 'FAILED'} ({len(issues)} issues)")
        
        return VerificationResult(
            passed=passed,
            issues=issues,
            tool_results={},
            llm_results={"summary": f"Fallback verification: {len(issues)} issues found"},
        )
    
    async def _run_harness_verification(
        self, plan: Plan, diffs: list[AgentOutput]
    ) -> HarnessResult:
        """
        Run the deterministic harness verification.
        
        This runs before LLM verification and catches:
        - Syntax errors
        - Import resolution issues
        - Security vulnerabilities
        - Contract mismatches
        - Negative constraint violations
        - Potential hallucinations
        """
        logger.info("   └─ Running harness verification...")
        
        # Convert AgentOutputs to FileDiffs
        file_diffs = []
        for output in diffs:
            if output.status != "success" or not output.diff:
                continue
            
            # Get original file content
            original_content = ""
            task = plan.tasks.get(output.task_id)
            if task and task.action == "MODIFY":
                result = _tools.read_file_content(output.file)
                if result.get('exists'):
                    original_content = result.get('content', '')
            
            # Extract modified content from diff
            modified_content = self._apply_diff_to_get_modified(
                original_content, output.diff
            )
            
            # Extract service from file path
            service_id = self._extract_service_from_path(output.file)
            
            file_diffs.append(FileDiff(
                file_path=output.file,
                original_content=original_content,
                modified_content=modified_content,
                service_id=service_id,
                task_id=output.task_id,
            ))
        
        if not file_diffs:
            logger.info("   └─ No valid diffs to verify with harness")
            return HarnessResult(passed=True, violations=[], checks_run=[])
        
        # Get services path
        services_path = str(self._services_path.parent) if self._services_path else "../services"
        
        # Run the harness gate
        gate = DeterministicGate(
            services_path=services_path,
            config=GateConfig(
                fail_fast=True,
                skip_hallucination=False,
                skip_security=False,
            )
        )
        
        # Get first service ID (most diffs will be same service)
        service_id = file_diffs[0].service_id if file_diffs else "unknown"
        
        result = await gate.run(
            service_id=service_id,
            diffs=file_diffs,
            plan=plan.to_dict() if plan else {},
        )
        
        logger.info(f"   └─ Harness checks run: {', '.join(result.checks_run)}")
        logger.info(f"   └─ Harness result: {result.error_count} errors, {result.warning_count} warnings")
        
        return result
    
    def _apply_diff_to_get_modified(self, original: str, diff: str) -> str:
        """Apply diff to original content to get modified content."""
        try:
            result = _tools.apply_diff_to_content(original, diff)
            if result.get('success'):
                return result.get('result', '')
        except Exception:
            pass
        
        # Fallback: extract + lines from diff
        lines = []
        for line in diff.split('\n'):
            if line.startswith('+') and not line.startswith('+++'):
                lines.append(line[1:])
            elif not line.startswith('-') and not line.startswith('@@'):
                if line.startswith(' '):
                    lines.append(line[1:])
                elif not line.startswith('---'):
                    lines.append(line)
        return '\n'.join(lines)
    
    def _extract_service_from_path(self, file_path: str) -> str:
        """Extract service name from file path."""
        parts = file_path.replace('\\', '/').split('/')
        for part in parts:
            if part.endswith('-service') or part in [
                'gateway-service', 'audit-service', 'payment-processor',
                'account-service', 'fx-service', 'ledger-service',
                'validation-service', 'payment-ui'
            ]:
                return part
        return parts[0] if parts else "unknown"
    
    def _convert_harness_result(
        self, harness_result: HarnessResult, include_warnings: bool = True
    ) -> VerificationResult:
        """Convert HarnessResult to VerificationResult."""
        issues = []
        
        for v in harness_result.violations:
            if v.severity == ViolationSeverity.INFO and not include_warnings:
                continue
            
            issues.append(VerificationIssue(
                file=v.file_path,
                severity=v.severity.value,
                issue=v.description,
                line=v.line_number,
                suggestion=v.fix_hint,
                task_id=v.details.get('task_id') if v.details else None,
                category=v.check.value,
            ))
        
        summary_parts = [f"Harness verification: {harness_result.error_count} errors"]
        if harness_result.warning_count > 0:
            summary_parts.append(f"{harness_result.warning_count} warnings")
        summary_parts.append(f"Checks: {', '.join(harness_result.checks_run)}")
        
        return VerificationResult(
            passed=harness_result.passed,
            issues=issues,
            tool_results={"harness": harness_result.to_dict()},
            llm_results={"summary": " | ".join(summary_parts)},
        )
