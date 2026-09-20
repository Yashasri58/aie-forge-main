"""
LLM Router with LiteLLM Auto Routing.

Uses LiteLLM's complexity router for automatic model selection based on:
- Heuristic scoring (token count, code presence, reasoning markers, etc.)
- Keyword rules (escalate to higher tiers for specific terms)
- Optional LLM classifier for more accurate classification

This provides AUTOMATIC model selection at runtime - no manual complexity
assessment needed.

Tiers:
- SIMPLE: Quick tasks, greetings, simple questions → gemini-2.5-flash-lite
- MEDIUM: Standard implementation, refactoring → gemini-2.5-flash  
- COMPLEX: Multi-file changes, debugging → gemini-2.5-flash (with thinking)
- REASONING: Architecture design, complex planning → gemini-2.5-pro
"""

import os
from enum import Enum
from typing import Optional, Any
from dataclasses import dataclass


# =============================================================================
# CONFIGURATION
# =============================================================================

class ModelTier(str, Enum):
    """Model capability tiers matching LiteLLM's complexity router."""
    SIMPLE = "SIMPLE"
    MEDIUM = "MEDIUM"
    COMPLEX = "COMPLEX"
    REASONING = "REASONING"


@dataclass
class RouterConfig:
    """Configuration for the auto router."""
    
    # Tier to model mapping (Gemini models)
    tiers: dict[str, str] = None
    
    # Default model if routing fails
    default_model: str = "gemini-2.5-flash"
    
    # Keyword rules for escalation
    keyword_rules: list[dict] = None
    
    # Whether to use LLM classifier instead of heuristic
    use_llm_classifier: bool = False
    classifier_model: str = "gemini-2.5-flash-lite"
    classifier_timeout_ms: int = 2000
    
    # Session affinity (keep same model for conversation)
    session_affinity: bool = True
    session_affinity_ttl_seconds: int = 3600
    
    # Custom technical keywords to add
    custom_technical_keywords: list[str] = None
    
    def __post_init__(self):
        if self.tiers is None:
            # Use pools for tiers to enable fallbacks
            self.tiers = {
                "SIMPLE": "gemini-2.5-flash-lite",
                "MEDIUM": "gemini-2.5-flash",
                "COMPLEX": "gemini-2.5-flash",
                # For REASONING: fallback to flash if pro is unavailable
                "REASONING": ["gemini-2.5-pro", "gemini-2.5-flash"],
            }
        
        if self.keyword_rules is None:
            self.keyword_rules = [
                # Simple tasks
                {"keywords": ["hi", "hello", "thanks", "ok", "yes", "no"], "tier": "SIMPLE"},
                
                # Reasoning tasks (architecture, design)
                {"keywords": [
                    "architecture", "design", "refactor", "restructure",
                    "plan", "strategy", "approach", "tradeoff", "trade-off",
                    "pros and cons", "compare", "analyze", "evaluate"
                ], "tier": "REASONING"},
                
                # Complex tasks (multi-step, debugging)
                {"keywords": [
                    "debug", "fix", "error", "bug", "issue", "problem",
                    "multiple files", "across services", "integration",
                    "step by step", "walk through"
                ], "tier": "COMPLEX"},
            ]
        
        if self.custom_technical_keywords is None:
            self.custom_technical_keywords = [
                # Forge-specific terms
                "kuzu", "graph", "cypher", "impact analysis",
                "code generation", "diff", "unified diff",
                # General technical terms
                "kubernetes", "docker", "microservices", "api",
                "database", "sql", "nosql", "redis", "kafka",
                "async", "concurrent", "parallel", "distributed"
            ]


# Default configuration
DEFAULT_CONFIG = RouterConfig()


# =============================================================================
# LITELLM ROUTER SETUP
# =============================================================================

def create_litellm_router(config: RouterConfig = None) -> Any:
    """
    Create a LiteLLM Router with auto-routing enabled.
    
    Args:
        config: Router configuration (uses defaults if None)
        
    Returns:
        LiteLLM Router instance
    """
    from litellm import Router
    
    if config is None:
        config = DEFAULT_CONFIG
    
    # Build model list
    model_list = []
    added_models = set()
    
    # Collect all unique models from tiers
    for tier, model_value in config.tiers.items():
        # Handle both single model and list of models
        models = model_value if isinstance(model_value, list) else [model_value]
        for model_name in models:
            if model_name not in added_models:
                model_list.append({
                    "model_name": model_name,
                    "litellm_params": {
                        "model": f"gemini/{model_name}",
                        "api_key": os.environ.get("GOOGLE_API_KEY"),
                    }
                })
                added_models.add(model_name)
    
    # Build complexity router config
    complexity_config = {
        "tiers": config.tiers,
        "keyword_tier_rules": config.keyword_rules,
        "custom_technical_keywords": config.custom_technical_keywords,
        "session_affinity": config.session_affinity,
        "session_affinity_ttl_seconds": config.session_affinity_ttl_seconds,
    }
    
    # Add LLM classifier if enabled
    if config.use_llm_classifier:
        complexity_config["classifier_type"] = "llm"
        complexity_config["classifier_llm_config"] = {
            "model": config.classifier_model,
            "timeout_ms": config.classifier_timeout_ms,
        }
    
    # Add auto router entry
    model_list.append({
        "model_name": "auto-router",
        "litellm_params": {
            "model": "auto_router/complexity_router",
            "complexity_router_config": complexity_config,
            "complexity_router_default_model": config.default_model,
        }
    })
    
    # Create router
    router = Router(model_list=model_list)
    
    return router


# =============================================================================
# SIMPLIFIED API FOR FORGE
# =============================================================================

class ForgeRouter:
    """
    Simplified router for Forge code generation.
    
    Wraps LiteLLM's complexity router with Forge-specific defaults.
    
    Usage:
        router = ForgeRouter()
        
        # Auto-routed based on message complexity
        response = await router.complete(messages=[
            {"role": "user", "content": "Create an architecture for..."}
        ])
        # → Automatically uses gemini-2.5-pro (REASONING tier)
        
        response = await router.complete(messages=[
            {"role": "user", "content": "Fix this typo"}
        ])
        # → Automatically uses gemini-2.5-flash-lite (SIMPLE tier)
    """
    
    _instance: Optional["ForgeRouter"] = None
    
    @classmethod
    def get_instance(cls) -> "ForgeRouter":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def __init__(self, config: RouterConfig = None):
        """
        Initialize the router.
        
        Args:
            config: Router configuration
        """
        self.config = config or DEFAULT_CONFIG
        self._router = None
        self._initialized = False
    
    def _ensure_initialized(self):
        """Lazily initialize the LiteLLM router."""
        if not self._initialized:
            try:
                self._router = create_litellm_router(self.config)
                self._initialized = True
            except ImportError:
                # LiteLLM not installed, fall back to direct calls
                self._router = None
                self._initialized = True
    
    async def complete(
        self,
        messages: list[dict],
        model: str = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs
    ) -> dict:
        """
        Complete a conversation with automatic model routing.
        
        Args:
            messages: Conversation messages
            model: Override model (bypasses auto-routing if set)
            temperature: Sampling temperature
            max_tokens: Max output tokens
            **kwargs: Additional arguments passed to LiteLLM
            
        Returns:
            Completion response
        """
        self._ensure_initialized()
        
        # Use specified model or auto-router
        target_model = model or "auto-router"
        
        if self._router:
            # Use LiteLLM router
            response = await self._router.acompletion(
                model=target_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs
            )
            return response
        else:
            # Fallback: direct Google API call
            return await self._fallback_complete(
                messages, temperature, max_tokens, **kwargs
            )
    
    async def _fallback_complete(
        self,
        messages: list[dict],
        temperature: float,
        max_tokens: int,
        **kwargs
    ) -> dict:
        """Fallback completion without LiteLLM."""
        import google.generativeai as genai
        
        genai.configure(api_key=os.environ.get("GOOGLE_API_KEY"))
        
        # Simple heuristic for model selection
        model_name = self._simple_route(messages)
        
        model = genai.GenerativeModel(model_name)
        
        # Convert messages to Gemini format
        contents = []
        for msg in messages:
            role = "user" if msg["role"] == "user" else "model"
            contents.append({"role": role, "parts": [msg["content"]]})
        
        response = model.generate_content(
            contents,
            generation_config={
                "temperature": temperature,
                "max_output_tokens": max_tokens,
            }
        )
        
        return {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": response.text,
                }
            }],
            "model": model_name,
        }
    
    def _simple_route(self, messages: list[dict]) -> str:
        """Simple heuristic routing without LiteLLM."""
        # Get last user message
        last_user = next(
            (m["content"] for m in reversed(messages) if m["role"] == "user"),
            ""
        ).lower()
        
        # Check keywords
        reasoning_keywords = [
            "architecture", "design", "plan", "strategy",
            "analyze", "evaluate", "compare", "tradeoff"
        ]
        complex_keywords = [
            "debug", "fix", "error", "multiple", "integration",
            "step by step", "walk through"
        ]
        simple_keywords = ["hi", "hello", "thanks", "ok", "yes", "no"]
        
        if any(kw in last_user for kw in simple_keywords) and len(last_user) < 50:
            return "gemini-2.5-flash-lite"
        
        if any(kw in last_user for kw in reasoning_keywords):
            return "gemini-2.5-pro"
        
        if any(kw in last_user for kw in complex_keywords):
            return "gemini-2.5-flash"
        
        # Default
        return "gemini-2.5-flash"


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def get_router() -> ForgeRouter:
    """Get the singleton ForgeRouter instance."""
    return ForgeRouter.get_instance()


async def complete(messages: list[dict], **kwargs) -> dict:
    """
    Complete with automatic model routing.
    
    Convenience function for quick access.
    """
    router = get_router()
    return await router.complete(messages, **kwargs)


# =============================================================================
# MODEL SELECTION HELPERS (for ADK agents)
# =============================================================================

def select_model(
    task_type: str = None,
    tier: ModelTier = None,
) -> str:
    """
    Select a Gemini model for a task type.
    
    This is for ADK agents that need a model string at creation time.
    For runtime auto-routing, use ForgeRouter instead.
    
    Args:
        task_type: Type of task
        tier: Explicit tier
        
    Returns:
        Model name string
    """
    if tier:
        return DEFAULT_CONFIG.tiers.get(tier.value, DEFAULT_CONFIG.default_model)
    
    task_to_tier = {
        # Reasoning tier
        "design": ModelTier.REASONING,
        "architecture": ModelTier.REASONING,
        "plan_creation": ModelTier.REASONING,
        
        # Complex tier
        "implementation": ModelTier.COMPLEX,
        "diff_generation": ModelTier.COMPLEX,
        "refactoring": ModelTier.COMPLEX,
        
        # Medium tier
        "verification": ModelTier.MEDIUM,
        "code_generation": ModelTier.MEDIUM,
        
        # Simple tier
        "exploration": ModelTier.SIMPLE,
        "search": ModelTier.SIMPLE,
        "formatting": ModelTier.SIMPLE,
    }
    
    tier = task_to_tier.get(task_type, ModelTier.MEDIUM)
    return DEFAULT_CONFIG.tiers.get(tier.value, DEFAULT_CONFIG.default_model)


def get_model_for_agent(agent_type: str) -> str:
    """
    Get the recommended model for a specific agent type.
    
    Args:
        agent_type: One of "design", "implementation", "verification"
        
    Returns:
        Model name string
    """
    mapping = {
        "design": "gemini-2.5-pro",
        "implementation": "gemini-2.5-flash",
        "verification": "gemini-2.5-flash",
        "exploration": "gemini-2.5-flash-lite",
    }
    return mapping.get(agent_type, "gemini-2.5-flash")


# =============================================================================
# EXPORTS
# =============================================================================

# For backwards compatibility
MODELS = DEFAULT_CONFIG.tiers
GEMINI_MODELS = DEFAULT_CONFIG.tiers
DEFAULT_MODELS = {
    ModelTier.SIMPLE: "gemini-2.5-flash-lite",
    ModelTier.MEDIUM: "gemini-2.5-flash",
    ModelTier.COMPLEX: "gemini-2.5-flash",
    ModelTier.REASONING: "gemini-2.5-pro",
}

# Keep TaskComplexity as alias for ModelTier
TaskComplexity = ModelTier

__all__ = [
    # Router
    "ForgeRouter",
    "RouterConfig",
    "create_litellm_router",
    "get_router",
    "complete",
    # Model selection (for ADK)
    "ModelTier",
    "TaskComplexity",
    "select_model",
    "get_model_for_agent",
    # Config
    "MODELS",
    "GEMINI_MODELS",
    "DEFAULT_MODELS",
    "DEFAULT_CONFIG",
]
