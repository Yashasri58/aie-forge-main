"""
Code Generation Module.

Multi-agent system for generating code changes based on impact analysis.

Architecture:
    ┌─────────────────────────────────────────────────────────────┐
    │  Impact Report (approved)                                    │
    │                          ↓                                   │
    │  ┌─────────────────────────────────────────────────────┐    │
    │  │  DESIGN AGENT (The Brain)                           │    │
    │  │  - Has tools: read_file, grep, query_code_graph     │    │
    │  │  - Explores codebase, finds patterns                │    │
    │  │  - Outputs: plan.json (the ultimatum)               │    │
    │  └─────────────────────────────────────────────────────┘    │
    │                          ↓                                   │
    │  ┌─────────────────────────────────────────────────────┐    │
    │  │  COORDINATOR (Simple Code)                          │    │
    │  │  - Validates plan.json                              │    │
    │  │  - Creates task files for each agent                │    │
    │  │  - Manages execution phases                         │    │
    │  └─────────────────────────────────────────────────────┘    │
    │                          ↓                                   │
    │  ┌─────────────────────────────────────────────────────┐    │
    │  │  IMPLEMENTATION AGENTS (The Hands) - Parallel       │    │
    │  │  - Each agent gets one task file                    │    │
    │  │  - Outputs: unified diff                            │    │
    │  └─────────────────────────────────────────────────────┘    │
    │                          ↓                                   │
    │  ┌─────────────────────────────────────────────────────┐    │
    │  │  VERIFICATION                                       │    │
    │  │  - Tool-based: lint, tests                          │    │
    │  │  - LLM-based: contract compliance                   │    │
    │  └─────────────────────────────────────────────────────┘    │
    │                          ↓                                   │
    │  User Approval                                               │
    └─────────────────────────────────────────────────────────────┘

Usage:
    from modules.codegen import CodeGenOrchestrator
    
    orchestrator = CodeGenOrchestrator(graph_store, services_path)
    result = await orchestrator.generate(impact_report)
    
    # result.plan - The plan.json
    # result.diffs - All generated diffs
    # result.verification - Verification results
"""

from .schemas import (
    Plan,
    PlanAnalysis,
    PlanDesign,
    Contract,
    ExecutionPhase,
    Task,
    TaskChange,
    TaskFile,
    AgentOutput,
    VerificationResult,
    CodeGenResult,
    CodeGenStage,
    CodeGenState,
)

from .design_agent import DesignAgent
from .implementation_agent import ImplementationAgent
from .verification import Verifier
from .coordinator import Coordinator
from .orchestrator import CodeGenOrchestrator
from .llm_router import (
    # Router classes
    ForgeRouter,
    RouterConfig,
    create_litellm_router,
    get_router,
    complete,
    # Model selection (for ADK agents)
    ModelTier,
    TaskComplexity,
    select_model,
    get_model_for_agent,
    # Config
    MODELS,
    GEMINI_MODELS,
    DEFAULT_MODELS,
    DEFAULT_CONFIG,
)
from .logging_config import (
    setup_logging as setup_codegen_logging,
    design_logger,
    impl_logger,
    verify_logger,
    orchestrator_logger,
    coordinator_logger,
)

__all__ = [
    # Schemas
    "Plan",
    "PlanAnalysis",
    "PlanDesign",
    "Contract",
    "ExecutionPhase",
    "Task",
    "TaskChange",
    "TaskFile",
    "AgentOutput",
    "VerificationResult",
    "CodeGenResult",
    "CodeGenStage",
    "CodeGenState",
    # Agents
    "DesignAgent",
    "ImplementationAgent",
    "Verifier",
    "Coordinator",
    "CodeGenOrchestrator",
    # LLM Router
    "ForgeRouter",
    "RouterConfig",
    "create_litellm_router",
    "get_router",
    "complete",
    "ModelTier",
    "TaskComplexity",
    "select_model",
    "get_model_for_agent",
    "MODELS",
    "GEMINI_MODELS",
    "DEFAULT_MODELS",
    "DEFAULT_CONFIG",
    # Logging
    "setup_codegen_logging",
    "design_logger",
    "impl_logger",
    "verify_logger",
    "orchestrator_logger",
    "coordinator_logger",
]
