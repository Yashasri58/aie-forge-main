"""
Base Agent Class using Google ADK.

All pipeline agents use Google ADK for LLM calls.
"""

from abc import ABC, abstractmethod
from typing import Optional
import json
import re
import time
import logging
from datetime import datetime

from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

# Module-level logger for all agents
_agent_log = logging.getLogger("forge.agents")


# ═══════════════════════════════════════════════════════════════════════════════
# LOGGING UTILITIES
# ═══════════════════════════════════════════════════════════════════════════════

class AgentLogger:
    """Colorful logging for agent activities."""
    
    COLORS = {
        'reset': '\033[0m',
        'bold': '\033[1m',
        'red': '\033[91m',
        'green': '\033[92m',
        'yellow': '\033[93m',
        'blue': '\033[94m',
        'magenta': '\033[95m',
        'cyan': '\033[96m',
        'white': '\033[97m',
        'gray': '\033[90m',
    }
    
    AGENT_COLORS = {
        'context_gatherer': 'cyan',
        'impact_agent': 'green',
        'verification_agent': 'magenta',
        'orchestrator': 'yellow',
    }
    
    @classmethod
    def _color(cls, text: str, color: str) -> str:
        return f"{cls.COLORS.get(color, '')}{text}{cls.COLORS['reset']}"
    
    @classmethod
    def _timestamp(cls) -> str:
        return datetime.now().strftime("%H:%M:%S.%f")[:-3]
    
    @classmethod
    def _box(cls, title: str, content: str, color: str = 'white', width: int = 80) -> str:
        """Create a box around content."""
        lines = []
        border = cls._color("═" * width, color)
        lines.append(border)
        lines.append(cls._color(f"║ {title}", color))
        lines.append(cls._color("╟" + "─" * (width - 1), color))
        
        for line in content.split('\n'):
            # Truncate long lines
            if len(line) > width - 4:
                line = line[:width - 7] + "..."
            lines.append(cls._color("║ ", color) + line)
        
        lines.append(border)
        return '\n'.join(lines)
    
    @classmethod
    def agent_start(cls, agent_name: str, prompt: str):
        """Log agent starting."""
        color = cls.AGENT_COLORS.get(agent_name, 'white')
        ts = cls._timestamp()
        
        print()
        print(cls._color(f"{'═' * 80}", color))
        print(cls._color(f"║ [{ts}] 🤖 AGENT: {agent_name.upper()}", color))
        print(cls._color(f"{'═' * 80}", color))
        print(cls._color("║ PROMPT:", color))
        
        # Print prompt (truncated if too long)
        prompt_lines = prompt.split('\n')
        for i, line in enumerate(prompt_lines[:10]):
            if len(line) > 76:
                line = line[:73] + "..."
            print(cls._color(f"║   {line}", 'gray'))
        if len(prompt_lines) > 10:
            print(cls._color(f"║   ... ({len(prompt_lines) - 10} more lines)", 'gray'))
        print(cls._color(f"{'─' * 80}", color))
    
    @classmethod
    def tool_call(cls, agent_name: str, tool_name: str, args: dict):
        """Log tool being called."""
        color = cls.AGENT_COLORS.get(agent_name, 'white')
        ts = cls._timestamp()
        
        print(cls._color(f"║ [{ts}] 🔧 TOOL CALL: {tool_name}", 'yellow'))
        print(cls._color(f"║   INPUT:", 'gray'))
        
        # Pretty print args
        args_str = json.dumps(args, indent=2, default=str)
        for line in args_str.split('\n')[:15]:
            if len(line) > 74:
                line = line[:71] + "..."
            print(cls._color(f"║     {line}", 'gray'))
        if len(args_str.split('\n')) > 15:
            print(cls._color(f"║     ... (truncated)", 'gray'))
    
    @classmethod
    def tool_result(cls, agent_name: str, tool_name: str, result: str, duration_ms: float):
        """Log tool result."""
        color = cls.AGENT_COLORS.get(agent_name, 'white')
        ts = cls._timestamp()
        
        print(cls._color(f"║ [{ts}] ✅ TOOL RESULT: {tool_name} ({duration_ms:.0f}ms)", 'green'))
        print(cls._color(f"║   OUTPUT:", 'gray'))
        
        # Truncate result
        result_str = str(result)
        result_lines = result_str.split('\n')
        for line in result_lines[:10]:
            if len(line) > 74:
                line = line[:71] + "..."
            print(cls._color(f"║     {line}", 'gray'))
        if len(result_lines) > 10:
            print(cls._color(f"║     ... ({len(result_lines) - 10} more lines)", 'gray'))
    
    @classmethod
    def tool_error(cls, agent_name: str, tool_name: str, error: str):
        """Log tool error."""
        ts = cls._timestamp()
        print(cls._color(f"║ [{ts}] ❌ TOOL ERROR: {tool_name}", 'red'))
        print(cls._color(f"║   {error}", 'red'))
    
    @classmethod
    def agent_response(cls, agent_name: str, response: str, duration_ms: float):
        """Log agent final response."""
        color = cls.AGENT_COLORS.get(agent_name, 'white')
        ts = cls._timestamp()
        
        print(cls._color(f"{'─' * 80}", color))
        print(cls._color(f"║ [{ts}] 📤 RESPONSE ({duration_ms:.0f}ms):", color))
        
        # Print response (truncated)
        response_lines = response.split('\n')
        for line in response_lines[:20]:
            if len(line) > 76:
                line = line[:73] + "..."
            print(cls._color(f"║   {line}", 'white'))
        if len(response_lines) > 20:
            print(cls._color(f"║   ... ({len(response_lines) - 20} more lines)", 'gray'))
        
        print(cls._color(f"{'═' * 80}", color))
        print()
    
    @classmethod
    def stage_change(cls, stage: str, details: str = ""):
        """Log pipeline stage change."""
        ts = cls._timestamp()
        print()
        print(cls._color(f"┌{'─' * 78}┐", 'yellow'))
        print(cls._color(f"│ [{ts}] 📍 STAGE: {stage.upper():<62}│", 'yellow'))
        if details:
            print(cls._color(f"│    {details:<72}│", 'gray'))
        print(cls._color(f"└{'─' * 78}┘", 'yellow'))
    
    @classmethod
    def iteration(cls, iteration: int, max_iter: int, phase: str):
        """Log iteration in verification loop."""
        ts = cls._timestamp()
        print()
        print(cls._color(f"  🔄 Iteration {iteration}/{max_iter}: {phase}", 'cyan'))


# ═══════════════════════════════════════════════════════════════════════════════
# BASE AGENT
# ═══════════════════════════════════════════════════════════════════════════════

class BaseADKAgent(ABC):
    """
    Base class for pipeline agents using Google ADK.
    
    Each agent has:
    - A name and instruction
    - Optional tools (functions the agent can call)
    - A run() method using ADK Runner
    """
    
    name: str = "base_agent"
    model: str = "gemini-2.5-flash"
    instruction: str = "You are a helpful assistant."
    
    def __init__(self):
        self.agent: Optional[Agent] = None
        self.runner: Optional[Runner] = None
        self.session_service = InMemorySessionService()
        self.session = None
        self.logger = AgentLogger
    
    @abstractmethod
    def _get_tools(self) -> list:
        """Return list of tool functions for this agent."""
        pass
    
    def _create_agent(self) -> Agent:
        """Create the ADK agent."""
        return Agent(
            model=self.model,
            name=self.name,
            instruction=self.instruction,
            tools=self._get_tools(),
        )
    
    async def _ensure_session(self):
        """Ensure we have an active session."""
        if self.agent is None:
            self.agent = self._create_agent()
        
        if self.session is None:
            self.session = await self.session_service.create_session(
                app_name=self.name,
                user_id="pipeline"
            )
            self.runner = Runner(
                agent=self.agent,
                app_name=self.name,
                session_service=self.session_service
            )
    
    async def run(self, prompt: str) -> str:
        """
        Run the agent with a prompt.
        
        Args:
            prompt: User prompt
            
        Returns:
            Agent response text
        """
        await self._ensure_session()
        
        # Log agent start
        start_time = time.time()
        self.logger.agent_start(self.name, prompt)
        _agent_log.info(f"[{self.name.upper()}] >> LLM CALL start | model={self.model} | prompt={len(prompt)} chars")
        _agent_log.debug(f"[{self.name.upper()}]    prompt preview: {prompt[:200].replace(chr(10), ' ')!r}")
        
        content = types.Content(
            role='user',
            parts=[types.Part(text=prompt)]
        )
        
        tool_call_count = 0
        response_text = ""
        async for event in self.runner.run_async(
            user_id="pipeline",
            session_id=self.session.id,
            new_message=content
        ):
            # Log tool calls if present
            if hasattr(event, 'tool_calls') and event.tool_calls:
                for tc in event.tool_calls:
                    tool_call_count += 1
                    tool_start = time.time()
                    self.logger.tool_call(self.name, tc.name, tc.args or {})
                    _agent_log.info(f"[{self.name.upper()}]    TOOL #{tool_call_count}: {tc.name}({json.dumps(tc.args or {}, default=str)[:120]})")
            
            # Log tool results
            if hasattr(event, 'tool_results') and event.tool_results:
                for tr in event.tool_results:
                    result_str = str(tr.result)[:500] if hasattr(tr, 'result') else str(tr)[:500]
                    tool_name = tr.name if hasattr(tr, 'name') else 'unknown'
                    self.logger.tool_result(
                        self.name, 
                        tool_name,
                        result_str,
                        0  # Duration not available here
                    )
                    _agent_log.debug(f"[{self.name.upper()}]    TOOL RESULT: {tool_name} → {result_str[:120]}")
            
            if event.is_final_response() and event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:
                        response_text += part.text
        
        # Log final response
        duration_ms = (time.time() - start_time) * 1000
        self.logger.agent_response(self.name, response_text, duration_ms)
        _agent_log.info(f"[{self.name.upper()}] << LLM CALL done | {duration_ms:.0f}ms | {tool_call_count} tool calls | response={len(response_text)} chars")
        _agent_log.debug(f"[{self.name.upper()}]    response preview: {response_text[:200].replace(chr(10), ' ')!r}")
        
        return response_text
    
    def reset_session(self):
        """Reset the session for a new conversation."""
        self.session = None
    
    @staticmethod
    def parse_json(text: str) -> dict:
        """Extract JSON from response text."""
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        
        # Look for JSON in code blocks
        patterns = [
            r'```json\s*([\s\S]*?)\s*```',
            r'```\s*([\s\S]*?)\s*```',
            r'\{[\s\S]*\}',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    json_str = match.group(1) if '```' in pattern else match.group(0)
                    return json.loads(json_str)
                except (json.JSONDecodeError, IndexError):
                    continue
        
        return {}
