"""
Logging configuration for Code Generation module.

Provides structured logging for:
- Design Agent activities
- Implementation Agent activities  
- Verification steps
- Orchestrator pipeline stages
- Tool usage
"""

import logging
import sys
from typing import Optional
from datetime import datetime

# Create module-specific loggers
design_logger = logging.getLogger("forge.codegen.design")
impl_logger = logging.getLogger("forge.codegen.implementation")
verify_logger = logging.getLogger("forge.codegen.verification")
orchestrator_logger = logging.getLogger("forge.codegen.orchestrator")
coordinator_logger = logging.getLogger("forge.codegen.coordinator")


class CodeGenFormatter(logging.Formatter):
    """Custom formatter with color coding for different log levels."""
    
    COLORS = {
        'DEBUG': '\033[36m',    # Cyan
        'INFO': '\033[32m',     # Green
        'WARNING': '\033[33m',  # Yellow
        'ERROR': '\033[31m',    # Red
        'CRITICAL': '\033[35m', # Magenta
    }
    RESET = '\033[0m'
    
    ICONS = {
        'DEBUG': '🔍',
        'INFO': '📋',
        'WARNING': '⚠️',
        'ERROR': '❌',
        'CRITICAL': '🚨',
    }
    
    def format(self, record):
        # Add timestamp
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        
        # Get color and icon
        color = self.COLORS.get(record.levelname, '')
        icon = self.ICONS.get(record.levelname, '')
        
        # Extract logger suffix (design, implementation, etc.)
        logger_suffix = record.name.split('.')[-1].upper()
        
        # Format the message
        formatted = (
            f"{color}[{timestamp}] {icon} [{logger_suffix}] "
            f"{record.getMessage()}{self.RESET}"
        )
        
        # Add exception info if present
        if record.exc_info:
            formatted += f"\n{self.formatException(record.exc_info)}"
            
        return formatted


def setup_logging(level: str = "INFO"):
    """
    Configure logging for the codegen module.
    
    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR)
    """
    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(CodeGenFormatter())
    
    # Set up root codegen logger
    codegen_root = logging.getLogger("forge.codegen")
    codegen_root.setLevel(getattr(logging, level.upper()))
    codegen_root.addHandler(console_handler)
    
    # Prevent propagation to avoid duplicate logs
    codegen_root.propagate = False
    

def log_tool_call(logger: logging.Logger, tool_name: str, args: dict, result: Optional[str] = None):
    """Log a tool call with arguments and result."""
    args_str = ", ".join(f"{k}={repr(v)[:50]}" for k, v in args.items())
    logger.info(f"🔧 TOOL: {tool_name}({args_str})")
    if result:
        result_preview = result[:200] + "..." if len(result) > 200 else result
        logger.debug(f"   └─ Result: {result_preview}")


def log_llm_call(logger: logging.Logger, model: str, prompt_preview: str, response_preview: Optional[str] = None):
    """Log an LLM call with model and prompt/response preview."""
    logger.info(f"🤖 LLM: {model}")
    logger.debug(f"   └─ Prompt: {prompt_preview[:100]}...")
    if response_preview:
        logger.debug(f"   └─ Response: {response_preview[:100]}...")


def log_stage_change(logger: logging.Logger, old_stage: str, new_stage: str):
    """Log a pipeline stage change."""
    logger.info(f"📍 STAGE: {old_stage} → {new_stage}")


def log_task_start(logger: logging.Logger, task_id: str, file: str, action: str):
    """Log the start of a task."""
    logger.info(f"▶️ TASK START: {task_id} ({action} {file})")


def log_task_complete(logger: logging.Logger, task_id: str, status: str, duration_ms: Optional[int] = None):
    """Log task completion."""
    duration_str = f" in {duration_ms}ms" if duration_ms else ""
    if status == "success":
        logger.info(f"✅ TASK COMPLETE: {task_id} - {status}{duration_str}")
    else:
        logger.error(f"❌ TASK FAILED: {task_id} - {status}{duration_str}")


def log_diff_preview(logger: logging.Logger, task_id: str, diff: str):
    """Log a preview of generated diff."""
    lines = diff.split('\n')
    additions = sum(1 for l in lines if l.startswith('+') and not l.startswith('+++'))
    deletions = sum(1 for l in lines if l.startswith('-') and not l.startswith('---'))
    logger.info(f"📝 DIFF: {task_id} (+{additions}/-{deletions} lines)")
    logger.debug(f"   └─ Preview: {diff[:300]}...")


# Initialize logging when module is imported
setup_logging("DEBUG")


__all__ = [
    "design_logger",
    "impl_logger", 
    "verify_logger",
    "orchestrator_logger",
    "coordinator_logger",
    "setup_logging",
    "log_tool_call",
    "log_llm_call",
    "log_stage_change",
    "log_task_start",
    "log_task_complete",
    "log_diff_preview",
]
