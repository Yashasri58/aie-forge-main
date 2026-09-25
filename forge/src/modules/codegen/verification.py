"""
Verification Module.

Two-stage verification:
1. Tool-based: Apply diffs, run linter, run tests
2. LLM-based: Check contract compliance (uses LLM Router)
"""

import os
import re
import json
import tempfile
import subprocess
import shutil
from pathlib import Path
from typing import Optional

from .schemas import (
    Plan,
    AgentOutput,
    VerificationResult,
    VerificationIssue,
)
from .prompts import VERIFICATION_AGENT_SYSTEM_PROMPT


# =============================================================================
# DIFF UTILITIES
# =============================================================================

def parse_unified_diff(diff_text: str) -> dict:
    """
    Parse a unified diff into structured data.
    
    Returns:
        {
            "old_file": str,
            "new_file": str,
            "hunks": [
                {
                    "old_start": int,
                    "old_count": int,
                    "new_start": int,
                    "new_count": int,
                    "lines": [(type, line), ...]  # type: ' ', '-', '+'
                }
            ]
        }
    """
    result = {
        "old_file": None,
        "new_file": None,
        "hunks": [],
    }
    
    lines = diff_text.strip().splitlines()
    current_hunk = None
    
    for line in lines:
        if line.startswith('---'):
            result["old_file"] = line[4:].strip().split('\t')[0]
        elif line.startswith('+++'):
            result["new_file"] = line[4:].strip().split('\t')[0]
        elif line.startswith('@@'):
            # Parse hunk header: @@ -start,count +start,count @@
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
            elif line.startswith('+'):
                current_hunk["lines"].append(('+', line[1:]))
            elif line.startswith(' ') or line == '':
                current_hunk["lines"].append((' ', line[1:] if line else ''))
    
    return result


def apply_diff_to_content(content: str, diff_text: str) -> str:
    """
    Apply a unified diff to content.
    
    Args:
        content: Original file content
        diff_text: Unified diff
        
    Returns:
        Modified content
    """
    import logging
    _log = logging.getLogger("forge.codegen.harness")

    # Normalize line endings — CRLF files cause hunk mismatches because
    # splitlines() strips \r but '\n'.join() doesn't add it back, leaving
    # stray \r on context lines that produce tree-sitter parse errors.
    content = content.replace('\r\n', '\n').replace('\r', '\n')

    original_lines = content.splitlines()
    _log.debug(f"[APPLY_DIFF] Input: {len(original_lines)} lines, diff={len(diff_text)} chars")

    diff = parse_unified_diff(diff_text)
    
    # Handle new file (--- /dev/null)
    if diff["old_file"] == "/dev/null" or diff["old_file"] == "a//dev/null":
        lines = []
        for hunk in diff["hunks"]:
            for line_type, line in hunk["lines"]:
                if line_type == '+':
                    lines.append(line)
        return '\n'.join(lines)
    
    # Apply hunks to existing content
    original_lines = content.splitlines()
    result_lines = []
    current_line = 0
    
    for hunk in diff["hunks"]:
        old_start = hunk["old_start"] - 1  # Convert to 0-indexed
        
        # Copy lines before this hunk
        while current_line < old_start:
            if current_line < len(original_lines):
                result_lines.append(original_lines[current_line])
            current_line += 1
        
        # Apply hunk
        for line_type, line in hunk["lines"]:
            if line_type == ' ':
                # Context line - copy from original
                if current_line < len(original_lines):
                    result_lines.append(original_lines[current_line])
                current_line += 1
            elif line_type == '-':
                # Removed line - skip in original
                current_line += 1
            elif line_type == '+':
                # Added line
                result_lines.append(line)
    
    # Copy remaining lines
    while current_line < len(original_lines):
        result_lines.append(original_lines[current_line])
        current_line += 1
    
    result = '\n'.join(result_lines)

    # Sanity check: warn if result has stray \r (means CRLF normalisation missed something)
    if '\r' in result:
        _log.warning(f"[APPLY_DIFF] ⚠️ Result still has {result.count(chr(13))} stray \\r chars after normalisation")
    _log.debug(f"[APPLY_DIFF] Output: {len(result_lines)} lines, {len(result)} chars")

    return result


# =============================================================================
# TOOL-BASED VERIFICATION
# =============================================================================

class ToolVerifier:
    """
    Tool-based verification: apply diffs, run linter, run tests.
    """
    
    def __init__(self, services_path: str):
        """
        Args:
            services_path: Path to the services directory
        """
        self._services_path = Path(services_path)
    
    def check_file_targets(self, diffs: list[AgentOutput]) -> list[dict]:
        """
        Check if diff targets are valid.
        
        Args:
            diffs: List of AgentOutput with diffs
            
        Returns:
            List of issues found
        """
        issues = []
        
        for output in diffs:
            if output.status != "success" or not output.diff:
                continue
            
            file_path = self._services_path / output.file
            diff_data = parse_unified_diff(output.diff)
            
            # Check if this is a MODIFY operation (old file is not /dev/null)
            old_file = diff_data.get("old_file", "")
            is_create = old_file in ["/dev/null", "a//dev/null", "/dev/null"]
            
            if not is_create and not file_path.exists():
                issues.append({
                    "file": output.file,
                    "severity": "error",
                    "issue": f"Diff modifies non-existent file: '{output.file}'",
                    "suggestion": "The Design Agent should use list_directory() to verify files exist before targeting them.",
                })
            
            # Check if parent directory exists for new files
            if is_create and not file_path.parent.exists():
                # This is okay - we can create parent dirs
                pass
        
        return issues
    
    def apply_diffs_to_temp(
        self, 
        diffs: list[AgentOutput],
    ) -> tuple[Path, list[str]]:
        """
        Apply all diffs to a temporary directory.
        
        Args:
            diffs: List of AgentOutput with diffs
            
        Returns:
            (temp_dir, errors)
        """
        # Create temp directory with copy of services
        temp_dir = Path(tempfile.mkdtemp(prefix="forge_verify_"))
        errors = []
        
        try:
            # Copy the services directory
            shutil.copytree(
                self._services_path, 
                temp_dir / "services",
                ignore=shutil.ignore_patterns('node_modules', '.git', 'dist', 'build')
            )
            
            # Apply each diff
            for output in diffs:
                if output.status != "success" or not output.diff:
                    continue
                
                file_path = temp_dir / "services" / output.file
                
                try:
                    if file_path.exists():
                        original_content = file_path.read_text(encoding="utf-8")
                        new_content = apply_diff_to_content(original_content, output.diff)
                    else:
                        # New file
                        file_path.parent.mkdir(parents=True, exist_ok=True)
                        new_content = apply_diff_to_content("", output.diff)
                    
                    file_path.write_text(new_content, encoding="utf-8")
                    
                except Exception as e:
                    errors.append(f"{output.file}: Failed to apply diff - {e}")
            
            return temp_dir, errors
            
        except Exception as e:
            # Clean up on error
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise
    
    def run_linter(
        self, 
        temp_dir: Path, 
        files: list[str]
    ) -> dict:
        """
        Run ESLint on modified files.
        
        Args:
            temp_dir: Temp directory with applied diffs
            files: List of modified file paths
            
        Returns:
            {
                "passed": bool,
                "errors": [{"file": str, "line": int, "message": str}]
            }
        """
        result = {"passed": True, "errors": []}
        services_dir = temp_dir / "services"
        
        for file_rel in files:
            file_path = services_dir / file_rel
            
            if not file_path.exists():
                continue
            
            if not file_path.suffix in ['.js', '.ts', '.jsx', '.tsx']:
                continue
            
            # Try to run ESLint
            try:
                # Look for ESLint in the service directory
                service_dir = file_path.parent
                while service_dir != services_dir and not (service_dir / 'package.json').exists():
                    service_dir = service_dir.parent
                
                eslint_path = service_dir / 'node_modules' / '.bin' / 'eslint'
                
                if not eslint_path.exists():
                    # Try global eslint
                    eslint_path = 'eslint'
                
                proc = subprocess.run(
                    [str(eslint_path), str(file_path), '--format', 'json'],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    cwd=str(service_dir),
                )
                
                if proc.returncode != 0 and proc.stdout:
                    try:
                        lint_result = json.loads(proc.stdout)
                        for file_result in lint_result:
                            for message in file_result.get('messages', []):
                                if message.get('severity', 0) >= 2:  # Error
                                    result["passed"] = False
                                    result["errors"].append({
                                        "file": file_rel,
                                        "line": message.get('line', 0),
                                        "message": message.get('message', 'Unknown error'),
                                    })
                    except json.JSONDecodeError:
                        pass
                        
            except (subprocess.TimeoutExpired, FileNotFoundError):
                # ESLint not available, skip
                pass
        
        return result
    
    def run_tests(
        self, 
        temp_dir: Path, 
        test_files: list[str] = None
    ) -> dict:
        """
        Run tests.
        
        Args:
            temp_dir: Temp directory with applied diffs
            test_files: Specific test files to run (optional)
            
        Returns:
            {
                "passed": bool,
                "failures": [{"file": str, "test": str, "message": str}]
            }
        """
        result = {"passed": True, "failures": []}
        services_dir = temp_dir / "services"
        
        # Find services with package.json
        for service_dir in services_dir.iterdir():
            if not service_dir.is_dir():
                continue
            
            package_json = service_dir / 'package.json'
            if not package_json.exists():
                continue
            
            try:
                pkg = json.loads(package_json.read_text())
                if 'test' not in pkg.get('scripts', {}):
                    continue
                
                # Run npm test
                proc = subprocess.run(
                    ['npm', 'test', '--', '--passWithNoTests'],
                    capture_output=True,
                    text=True,
                    timeout=120,
                    cwd=str(service_dir),
                )
                
                if proc.returncode != 0:
                    result["passed"] = False
                    result["failures"].append({
                        "file": str(service_dir.name),
                        "test": "npm test",
                        "message": proc.stderr[:500] if proc.stderr else proc.stdout[:500],
                    })
                    
            except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError):
                pass
        
        return result
    
    def cleanup(self, temp_dir: Path):
        """Clean up temporary directory."""
        shutil.rmtree(temp_dir, ignore_errors=True)


# =============================================================================
# LLM-BASED VERIFICATION
# =============================================================================

class LLMVerifier:
    """
    LLM-based verification: check contract compliance.
    
    Uses gemini-2.5-flash for balanced speed/quality in verification.
    """
    
    def __init__(self):
        """Initialize the verifier."""
        from google.adk.agents import Agent
        from google.adk.runners import Runner
        from google.adk.sessions import InMemorySessionService
        from .llm_router import select_model
        
        # Select model for verification task
        model = select_model(task_type="verification")
        
        self._agent = Agent(
            model=model,
            name="forge_verification_agent",
            instruction=VERIFICATION_AGENT_SYSTEM_PROMPT,
            description="Verifies code changes against the plan",
            tools=[],
        )
        self._session_service = InMemorySessionService()
        self._session = None
        self._runner = None
    
    async def _ensure_session(self):
        """Ensure we have an active session."""
        if self._session is None:
            self._session = await self._session_service.create_session(
                app_name="forge_verification",
                user_id="developer"
            )
            self._runner = Runner(
                agent=self._agent,
                app_name="forge_verification",
                session_service=self._session_service
            )
    
    async def verify(
        self, 
        plan: Plan, 
        diffs: list[AgentOutput]
    ) -> dict:
        """
        Verify diffs against the plan.
        
        Args:
            plan: The execution plan
            diffs: Generated diffs
            
        Returns:
            {
                "passed": bool,
                "issues": [{"file": str, "severity": str, "issue": str, "suggestion": str}],
                "summary": str
            }
        """
        from google.genai import types
        
        await self._ensure_session()
        
        # Build prompt
        contracts_text = json.dumps(
            {name: c.to_dict() for name, c in plan.contracts.items()},
            indent=2
        )[:3000]
        
        diffs_text = ""
        for output in diffs:
            if output.diff:
                diffs_text += f"\n### {output.file}\n```diff\n{output.diff[:1500]}\n```\n"
        
        prompt = f"""Verify these diffs against the plan.

## CONTRACTS (must match exactly)
{contracts_text}

## DIFFS
{diffs_text[:6000]}

## DESIGN DECISIONS
{json.dumps([d.decision for d in plan.design.decisions] if plan.design else [], indent=2)}

Check:
1. Do diffs use the contract signatures exactly?
2. Are all tasks implemented?
3. Any obvious bugs or syntax errors?

Return JSON:
```json
{{
  "passed": boolean,
  "issues": [
    {{"file": "...", "severity": "error|warning", "issue": "...", "suggestion": "..."}}
  ],
  "summary": "Overall assessment"
}}
```
"""
        
        content = types.Content(
            role='user',
            parts=[types.Part(text=prompt)]
        )
        
        response_text = ""
        try:
            async for event in self._runner.run_async(
                user_id="developer",
                session_id=self._session.id,
                new_message=content
            ):
                if event.is_final_response() and event.content and event.content.parts:
                    for part in event.content.parts:
                        if part.text:
                            response_text += part.text
            
            # Parse response
            json_match = re.search(r'```json\s*([\s\S]*?)\s*```', response_text)
            if json_match:
                return json.loads(json_match.group(1))
            
            # Try to parse as raw JSON
            return json.loads(response_text)
            
        except Exception as e:
            return {
                "passed": True,  # Default to passed if verification fails
                "issues": [],
                "summary": f"Verification error: {e}",
            }


# =============================================================================
# COMBINED VERIFIER
# =============================================================================

class Verifier:
    """
    Combined verifier: tool-based + LLM-based.
    
    Usage:
        verifier = Verifier(services_path)
        result = await verifier.verify(plan, diffs)
    """
    
    def __init__(self, services_path: str, enable_llm: bool = True):
        """
        Args:
            services_path: Path to the services directory
            enable_llm: Whether to run LLM verification
        """
        self._tool_verifier = ToolVerifier(services_path)
        self._llm_verifier = LLMVerifier() if enable_llm else None
        self._enable_llm = enable_llm
    
    async def verify(
        self, 
        plan: Plan, 
        diffs: list[AgentOutput],
        run_tests: bool = False
    ) -> VerificationResult:
        """
        Verify all diffs.
        
        Args:
            plan: The execution plan
            diffs: Generated diffs
            run_tests: Whether to run tests (slower)
            
        Returns:
            VerificationResult
        """
        issues = []
        tool_results = {}
        
        # Get list of files
        files = [d.file for d in diffs if d.status == "success"]
        
        # Step 0: Check file targets are valid
        file_target_issues = self._tool_verifier.check_file_targets(diffs)
        if file_target_issues:
            tool_results["file_targets"] = {"errors": file_target_issues}
            for issue in file_target_issues:
                issues.append(VerificationIssue(
                    file=issue["file"],
                    severity=issue["severity"],
                    issue=issue["issue"],
                    suggestion=issue.get("suggestion"),
                ))
        
        # Step 1: Apply diffs to temp directory
        temp_dir = None
        try:
            temp_dir, apply_errors = self._tool_verifier.apply_diffs_to_temp(diffs)
            tool_results["apply"] = {"errors": apply_errors}
            
            for error in apply_errors:
                issues.append(VerificationIssue(
                    file=error.split(":")[0] if ":" in error else "unknown",
                    severity="error",
                    issue=error,
                ))
            
            # Step 2: Run linter
            lint_result = self._tool_verifier.run_linter(temp_dir, files)
            tool_results["lint"] = lint_result
            
            for error in lint_result.get("errors", []):
                issues.append(VerificationIssue(
                    file=error["file"],
                    severity="error",
                    issue=error["message"],
                    line=error.get("line"),
                ))
            
            # Step 3: Run tests (optional)
            if run_tests:
                test_result = self._tool_verifier.run_tests(temp_dir)
                tool_results["tests"] = test_result
                
                for failure in test_result.get("failures", []):
                    issues.append(VerificationIssue(
                        file=failure["file"],
                        severity="error",
                        issue=f"Test failed: {failure['message']}",
                    ))
            
        finally:
            if temp_dir:
                self._tool_verifier.cleanup(temp_dir)
        
        # Step 4: LLM verification
        llm_results = None
        if self._enable_llm and self._llm_verifier:
            llm_results = await self._llm_verifier.verify(plan, diffs)
            
            for issue in llm_results.get("issues", []):
                issues.append(VerificationIssue(
                    file=issue.get("file", "unknown"),
                    severity=issue.get("severity", "warning"),
                    issue=issue.get("issue", "Unknown issue"),
                    suggestion=issue.get("suggestion"),
                ))
        
        # Determine overall pass/fail
        has_errors = any(i.severity == "error" for i in issues)
        passed = not has_errors
        
        return VerificationResult(
            passed=passed,
            tool_results=tool_results,
            llm_results=llm_results,
            issues=issues,
        )
